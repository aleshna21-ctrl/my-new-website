"""
tests/test_deep_aios_gateway.py - Unit & Integration Tests for Deep AIOS Gateway Seam.

Covers:
1. Dual-access response contracts: GatewayResult, CronJobSnapshot, TaskExecutionSnapshot.
2. Encapsulated instance state: NonceReplayCache, SyncSequenceTracker, GatewayFeedbackLoop, IdempotencyRegistry.
3. Canonical signing, HMAC verification, and constant-time comparison.
4. Pluggable command and method registration.
5. Zero dependency isolation from hud.os_dashboard and host scripts.
"""

import unittest
import time
from aios_gateway import (
    AIOSGateway, FakeAIOSGateway, GatewayResult, CronJobSnapshot, TaskExecutionSnapshot,
    NonceReplayCache, SyncSequenceTracker, GatewayFeedbackLoop, IdempotencyRegistry,
    compute_signature, verify_signature, create_signed_headers, compute_body_sha256,
    DiskGatewayStorage, InMemoryGatewayStorage, UrllibTransport, InMemoryTransport,
    DEFAULT_CRON_JOBS
)


class TestDeepAIOSGatewaySeam(unittest.TestCase):
    def setUp(self):
        self.secret = "test-deep-gateway-secret-42"
        self.gateway = AIOSGateway(secret=self.secret)

    def test_gateway_result_dual_access_and_unwrapping(self):
        raw = {
            "status": "ok",
            "result": {"answer": 42},
            "error": None,
            "ack": {"ack_id": "ack-12345", "status": "ACK"},
            "sequence_id": 99,
            "authenticated": True,
            "protocol": "JSON-RPC 2.0 / REST Webhook",
            "service": "aios-gateway"
        }
        res = GatewayResult(raw)

        # Dictionary access
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["sequence_id"], 99)
        self.assertEqual(res["result"]["answer"], 42)

        # Typed property access
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.sequence_id, 99)
        self.assertEqual(res.ack_id, "ack-12345")
        self.assertTrue(res.authenticated)
        self.assertTrue(res.is_ok())
        self.assertEqual(res.unwrap(), {"answer": 42})

        # Error handling unwrapping
        err_res = GatewayResult({"status": "error", "error": {"code": -32000, "message": "Signature fail"}})
        self.assertFalse(err_res.is_ok())
        with self.assertRaises(RuntimeError) as ctx:
            err_res.unwrap()
        self.assertIn("Signature fail", str(ctx.exception))

    def test_cron_job_and_task_snapshots(self):
        cron_raw = {
            "id": "cron-test-01",
            "name": "Audit Task",
            "expression": "*/5 * * * *",
            "description": "Runs audits",
            "target_method": "hermes.task.execute",
            "params": {"cmd": "audit"},
            "enabled": True,
            "last_outcome": "success",
            "created_at": "2026-10-27T00:00:00Z",
            "sequence_id": 12
        }
        cron = CronJobSnapshot(cron_raw)
        self.assertEqual(cron.id, "cron-test-01")
        self.assertEqual(cron.expression, "*/5 * * * *")
        self.assertTrue(cron.enabled)
        self.assertEqual(cron.sequence_id, 12)
        self.assertEqual(cron["name"], "Audit Task")

        task_raw = {
            "task_id": "task-abc-123",
            "command": "ping",
            "status": "completed",
            "result": {"msg": "pong"},
            "duration_ms": 14.5,
            "executed_at": "2026-10-27T00:00:00Z",
            "sequence_id": 13,
            "requires_operator_signoff": False
        }
        task = TaskExecutionSnapshot(task_raw)
        self.assertEqual(task.task_id, "task-abc-123")
        self.assertEqual(task.duration_ms, 14.5)
        self.assertFalse(task.requires_operator_signoff)
        self.assertEqual(task["status"], "completed")

    def test_encapsulated_state_isolation(self):
        gw1 = AIOSGateway(secret="secret-1")
        gw2 = AIOSGateway(secret="secret-2")

        # Verify nonce caches are distinct
        self.assertTrue(gw1.nonce_cache.check_and_record("nonce-A"))
        self.assertFalse(gw1.nonce_cache.check_and_record("nonce-A"))
        self.assertTrue(gw2.nonce_cache.check_and_record("nonce-A"))  # gw2 isolated

        # Verify sequence trackers are distinct
        self.assertEqual(gw1.sync_tracker.current_seq(), 1)
        self.assertEqual(gw2.sync_tracker.current_seq(), 1)
        gw1.sync_tracker.advance("cron", "test")
        self.assertEqual(gw1.sync_tracker.current_seq(), 2)
        self.assertEqual(gw2.sync_tracker.current_seq(), 1)

    def test_canonical_signing_and_verification(self):
        method = "POST"
        path = "/gateway/v1/rpc"
        body = b'{"jsonrpc":"2.0","method":"hermes.ping","id":1}'
        ts = str(int(time.time()))
        nonce = "nonce-test-123"

        sig = compute_signature(self.secret, method, path, body, ts, nonce)
        self.assertTrue(verify_signature(self.secret, method, path, body, ts, nonce, sig))

        # Tampered payload fails
        tampered_body = b'{"jsonrpc":"2.0","method":"hermes.ping","id":2}'
        self.assertFalse(verify_signature(self.secret, method, path, tampered_body, ts, nonce, sig))

        # Tampered secret fails
        self.assertFalse(verify_signature("wrong-secret", method, path, body, ts, nonce, sig))

    def test_create_signed_headers_generation(self):
        body = b'{"action":"test"}'
        headers = create_signed_headers("POST", "/test", body, secret=self.secret, idempotency_key="idemp-99")
        self.assertIn("X-Gateway-Timestamp", headers)
        self.assertIn("X-Gateway-Nonce", headers)
        self.assertIn("X-Gateway-Signature", headers)
        self.assertEqual(headers["X-Idempotency-Key"], "idemp-99")
        self.assertEqual(headers["Authorization"], f"Bearer {self.secret}")

        # Signature in headers verifies
        self.assertTrue(verify_signature(
            self.secret, "POST", "/test", body,
            headers["X-Gateway-Timestamp"],
            headers["X-Gateway-Nonce"],
            headers["X-Gateway-Signature"]
        ))

    def test_custom_command_and_method_registration(self):
        gw = AIOSGateway()
        called = []

        def custom_cmd(params):
            called.append(params)
            return {"echo": params.get("val", 0)}

        gw.register_command("custom_echo", custom_cmd)
        self.assertIn("custom_echo", gw._command_handlers)
        res = gw._command_handlers["custom_echo"]({"val": 99})
        self.assertEqual(res["echo"], 99)
        self.assertEqual(called, [{"val": 99}])

    def test_health_telemetry_reporting(self):
        h = self.gateway.health()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["service"], "aios-gateway-host")
        self.assertIn("replay_cache_size", h)
        self.assertIn("feedback", h)

    def test_in_memory_gateway_storage_operations(self):
        storage = InMemoryGatewayStorage()
        crons = storage.load_crons()
        self.assertEqual(len(crons), len(DEFAULT_CRON_JOBS))

        # Save and re-load crons
        crons.append({"id": "custom-cron", "name": "Custom", "expression": "* * * * *"})
        storage.save_crons(crons)
        loaded = storage.load_crons()
        self.assertEqual(len(loaded), len(DEFAULT_CRON_JOBS) + 1)
        self.assertEqual(loaded[-1]["id"], "custom-cron")

        # Record and load tasks
        self.assertEqual(len(storage.load_tasks()), 0)
        storage.record_task({"task_id": "t-1", "command": "ping", "status": "completed"})
        storage.record_task({"task_id": "t-2", "command": "status", "status": "completed"})
        tasks = storage.load_tasks(limit=10)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["task_id"], "t-1")
        self.assertEqual(tasks[1]["task_id"], "t-2")

        # Clear
        storage.clear()
        self.assertEqual(len(storage.load_tasks()), 0)
        self.assertEqual(len(storage.load_crons()), len(DEFAULT_CRON_JOBS))

    def test_disk_gateway_storage_operations_in_tempdir(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = DiskGatewayStorage(data_dir=tmpdir)
            self.assertFalse(storage.cron_path.exists())
            self.assertFalse(storage.task_path.exists())

            # Load creates default crons
            crons = storage.load_crons()
            self.assertTrue(storage.cron_path.exists())
            self.assertEqual(len(crons), len(DEFAULT_CRON_JOBS))

            # Atomic save crons
            crons[0]["name"] = "Modified Daily Backup"
            storage.save_crons(crons)
            reloaded = storage.load_crons()
            self.assertEqual(reloaded[0]["name"], "Modified Daily Backup")

            # Record task
            storage.record_task({"task_id": "t-disk-1", "command": "audit", "status": "success"})
            self.assertTrue(storage.task_path.exists())
            tasks = storage.load_tasks()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0]["task_id"], "t-disk-1")

    def test_in_memory_transport_recording_and_matching(self):
        transport = InMemoryTransport(default_status=200, default_body={"status": "ok", "default": True})

        # Register custom route
        transport.register_response(
            "/custom/rpc",
            status=201,
            headers={"X-Custom": "header-val"},
            body={"jsonrpc": "2.0", "result": {"ack": True}}
        )

        # Matched call
        status, headers, body = transport.send("http://localhost:8080/custom/rpc", method="POST", body=b"test-payload")
        self.assertEqual(status, 201)
        self.assertEqual(headers["X-Custom"], "header-val")
        self.assertIn(b'"ack": true', body.lower())

        # Unmatched fallback call
        f_status, f_headers, f_body = transport.send("http://localhost:8080/other", method="GET")
        self.assertEqual(f_status, 200)
        self.assertIn(b'"default": true', f_body.lower())

        # Check recorded requests
        self.assertEqual(len(transport.sent_requests), 2)
        self.assertEqual(transport.sent_requests[0]["url"], "http://localhost:8080/custom/rpc")
        self.assertEqual(transport.sent_requests[0]["method"], "POST")
        self.assertEqual(transport.sent_requests[0]["body"], b"test-payload")

        # Clear
        transport.clear()
        self.assertEqual(len(transport.sent_requests), 0)

    def test_gateway_with_in_memory_adapters(self):
        storage = InMemoryGatewayStorage()
        transport = InMemoryTransport()
        gw = AIOSGateway(secret="in-memory-sec", storage=storage, transport=transport)

        self.assertIs(gw.storage, storage)
        self.assertIs(gw.transport, transport)
        self.assertEqual(len(gw.storage.load_crons()), len(DEFAULT_CRON_JOBS))

    def test_handle_inbound_authorized_and_dispatched(self):
        storage = InMemoryGatewayStorage()
        gw = AIOSGateway(secret=self.secret, storage=storage)

        path = "/gateway/v1/rpc"
        body = b'{"jsonrpc":"2.0","id":"test-1","method":"hermes.ping","params":{}}'
        ts = str(int(time.time()))
        nonce = "nonce-inbound-001"
        sig = compute_signature(self.secret, "POST", path, body, ts, nonce)

        headers = {
            "X-Gateway-Timestamp": ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig
        }

        res = gw.handle_inbound("POST", path, headers, raw_body=body)
        self.assertTrue(res.is_ok())
        self.assertTrue(res.authenticated)
        self.assertEqual(res["id"], "test-1")
        self.assertIn("service", res.result)
        self.assertIn("feedback", res.result)
        self.assertIsNotNone(res.ack)

    def test_handle_inbound_security_rejections(self):
        gw = AIOSGateway(secret=self.secret, clock_skew_seconds=10.0)
        path = "/gateway/v1/rpc"
        body = b'{"method":"ping"}'

        # 1. Missing header
        res1 = gw.handle_inbound("POST", path, {}, raw_body=body)
        self.assertFalse(res1.is_ok())
        self.assertEqual(res1.error["code"], 401)
        self.assertIn("Missing required", res1.error["message"])

        # 2. Clock skew
        old_ts = str(int(time.time()) - 50)
        nonce = "nonce-skew-1"
        sig = compute_signature(self.secret, "POST", path, body, old_ts, nonce)
        res2 = gw.handle_inbound("POST", path, {
            "X-Gateway-Timestamp": old_ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig
        }, raw_body=body)
        self.assertFalse(res2.is_ok())
        self.assertEqual(res2.error["code"], 401)
        self.assertIn("Clock skew", res2.error["message"])

        # 3. Signature mismatch
        now_ts = str(int(time.time()))
        res3 = gw.handle_inbound("POST", path, {
            "X-Gateway-Timestamp": now_ts,
            "X-Gateway-Nonce": "nonce-tamper-1",
            "X-Gateway-Signature": "invalid-sig"
        }, raw_body=body)
        self.assertFalse(res3.is_ok())
        self.assertEqual(res3.error["code"], 401)
        self.assertIn("Signature mismatch", res3.error["message"])

        # 4. Replay attack
        valid_nonce = "nonce-replay-001"
        valid_sig = compute_signature(self.secret, "POST", path, body, now_ts, valid_nonce)
        valid_headers = {
            "X-Gateway-Timestamp": now_ts,
            "X-Gateway-Nonce": valid_nonce,
            "X-Gateway-Signature": valid_sig
        }
        first_call = gw.handle_inbound("POST", path, valid_headers, raw_body=body)
        self.assertTrue(first_call.is_ok())

        second_call = gw.handle_inbound("POST", path, valid_headers, raw_body=body)
        self.assertFalse(second_call.is_ok())
        self.assertEqual(second_call.error["code"], 401)
        self.assertIn("Replay attack", second_call.error["message"])

    def test_handle_inbound_bearer_token_authorization(self):
        gw = AIOSGateway(secret=self.secret)
        body = b'{"method":"ping"}'
        res = gw.handle_inbound("POST", "/api/rpc", {
            "Authorization": f"Bearer {self.secret}"
        }, raw_body=body)
        self.assertTrue(res.is_ok())
        self.assertTrue(res.authenticated)

    def test_handle_inbound_idempotency_cache(self):
        gw = AIOSGateway(secret=self.secret)
        path = "/rpc"
        body = b'{"method":"hermes.ping"}'
        ts = str(int(time.time()))
        nonce = "nonce-idemp-1"
        sig = compute_signature(self.secret, "POST", path, body, ts, nonce)

        headers = {
            "X-Gateway-Timestamp": ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig,
            "X-Idempotency-Key": "key-unique-77"
        }
        res1 = gw.handle_inbound("POST", path, headers, raw_body=body)
        self.assertTrue(res1.is_ok())

        # Second call with new nonce but same idempotency key hits cache
        ts2 = str(int(time.time()))
        nonce2 = "nonce-idemp-2"
        sig2 = compute_signature(self.secret, "POST", path, body, ts2, nonce2)
        headers2 = {
            "X-Gateway-Timestamp": ts2,
            "X-Gateway-Nonce": nonce2,
            "X-Gateway-Signature": sig2,
            "X-Idempotency-Key": "key-unique-77"
        }
        res2 = gw.handle_inbound("POST", path, headers2, raw_body=body)
        self.assertTrue(res2.is_ok())
        self.assertEqual(res1.sequence_id, res2.sequence_id)

    def test_send_rpc_outbound_with_in_memory_transport(self):
        transport = InMemoryTransport()
        transport.register_response(
            "/peer/rpc",
            status=200,
            headers={"X-Gateway-Ack": "ack-peer-1", "X-Gateway-Seq": "42"},
            body={"jsonrpc": "2.0", "result": {"peer_status": "ONLINE"}}
        )
        gw = AIOSGateway(secret=self.secret, transport=transport)

        res = gw.send_rpc("http://127.0.0.1:8080/peer/rpc", "peer.health", {"detail": True})
        self.assertTrue(res.is_ok())
        self.assertEqual(res.result["peer_status"], "ONLINE")
        self.assertEqual(res.sequence_id, 42)
        self.assertEqual(res.ack["ack_id"], "ack-peer-1")
        self.assertGreaterEqual(res["round_trip_ms"], 0.0)

        # Inspect recorded outbound request
        self.assertEqual(len(transport.sent_requests), 1)
        sent = transport.sent_requests[0]
        self.assertIn("X-Gateway-Signature", sent["headers"])
        self.assertIn("X-Gateway-Nonce", sent["headers"])

    def test_cron_management_lifecycle(self):
        storage = InMemoryGatewayStorage()
        gw = AIOSGateway(secret=self.secret, storage=storage)

        # List crons
        crons = gw.list_crons()
        self.assertEqual(len(crons), len(DEFAULT_CRON_JOBS))

        # Update / Create cron
        new_cron = gw.update_cron("cron-test-sweep", {
            "name": "Test Sweeper",
            "expression": "*/1 * * * *",
            "target_method": "hermes.ping",
            "params": {}
        })
        self.assertEqual(new_cron.id, "cron-test-sweep")
        self.assertIsNotNone(new_cron.sequence_id)

        # Trigger cron
        trig = gw.trigger_cron("cron-test-sweep")
        self.assertTrue(trig.is_ok())
        self.assertEqual(trig.result["status"], "success")

        # Verify last outcome updated
        reloaded = [c for c in gw.list_crons() if c.id == "cron-test-sweep"][0]
        self.assertIn("success", reloaded.last_outcome)
        self.assertIsNotNone(reloaded.last_run_utc)

        # Delete cron
        deleted = gw.delete_cron("cron-test-sweep")
        self.assertTrue(deleted)
        self.assertEqual(len([c for c in gw.list_crons() if c.id == "cron-test-sweep"]), 0)

    def test_task_command_execution_lifecycle(self):
        storage = InMemoryGatewayStorage()
        gw = AIOSGateway(secret=self.secret, storage=storage)

        # Execute safe default command
        task = gw.execute_task_command("ping", {})
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.result["message"], "pong")
        self.assertIsNotNone(task.ack)

        # Verify task is recorded in storage
        tasks = gw.list_tasks(limit=10)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_id, task.task_id)


class TestFakeAIOSGateway(unittest.TestCase):
    def setUp(self):
        self.fake = FakeAIOSGateway(secret="fake-secret-999")

    def test_fake_gateway_defaults_and_call_tracking(self):
        # Uses in-memory storage and transport by default
        self.assertIsInstance(self.fake.storage, InMemoryGatewayStorage)
        self.assertIsInstance(self.fake.transport, InMemoryTransport)
        self.assertEqual(len(self.fake.calls), 0)

        # Inbound call tracking (records handle_inbound + execute_rpc)
        res = self.fake.handle_inbound("POST", "/test", {"Authorization": "Bearer fake-secret-999"}, b'{"method":"ping"}')
        self.assertTrue(res.is_ok())
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(self.fake.calls[0]["action"], "handle_inbound")
        self.assertEqual(self.fake.calls[1]["action"], "execute_rpc")

        # Outbound call tracking
        out_res = self.fake.send_rpc("http://mock.hermes:8080/rpc", "hermes.ping", {})
        self.assertTrue(out_res.is_ok())
        self.assertEqual(len(self.fake.calls), 3)
        self.assertEqual(self.fake.calls[2]["action"], "send_rpc")
        self.assertEqual(len(self.fake.sent_requests), 1)

    def test_fake_gateway_canned_mock_responses(self):
        self.fake.register_mock_response("hermes.reasoning.solve", {"solution": "42", "confidence": 0.99})

        # Outbound mock response
        res = self.fake.send_rpc("http://agent:8080/rpc", "hermes.reasoning.solve", {"problem": "life"})
        self.assertTrue(res.is_ok())
        self.assertEqual(res.result["solution"], "42")
        self.assertEqual(res.result["confidence"], 0.99)

        # Inbound execute_rpc mock response
        exec_res = self.fake.execute_rpc("hermes.reasoning.solve", {"problem": "universe"})
        self.assertTrue(exec_res.is_ok())
        self.assertEqual(exec_res.result["solution"], "42")

    def test_fake_gateway_fault_injection(self):
        failing_fake = FakeAIOSGateway(
            should_fail=True,
            fail_error="Simulated upstream network timeout (504)"
        )

        # Inbound failure
        res_in = failing_fake.handle_inbound("POST", "/rpc", {"Authorization": "Bearer fake"}, b'{}')
        self.assertFalse(res_in.is_ok())
        self.assertEqual(res_in.error["code"], 500)
        self.assertIn("Simulated upstream network timeout", res_in.error["message"])

        # Outbound failure
        res_out = failing_fake.send_rpc("http://agent/rpc", "ping", {})
        self.assertFalse(res_out.is_ok())
        self.assertEqual(res_out.error["code"], 500)
        self.assertIn("Simulated upstream network timeout", res_out.error["message"])

    def test_fake_gateway_state_reset(self):
        self.fake.execute_task_command("ping", {})
        self.fake.send_rpc("http://peer/rpc", "ping", {})
        self.assertGreater(len(self.fake.calls), 0)
        self.assertGreater(len(self.fake.sent_requests), 0)
        self.assertGreater(len(self.fake.list_tasks()), 0)

        self.fake.reset()
        self.assertEqual(len(self.fake.calls), 0)
        self.assertEqual(len(self.fake.sent_requests), 0)
        self.assertEqual(len(self.fake.list_tasks()), 0)
        self.assertEqual(self.fake.sync_tracker.current_seq(), 1)


if __name__ == "__main__":
    unittest.main()
