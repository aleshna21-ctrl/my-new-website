"""
tests/test_hermes_gateway.py - Comprehensive Unit & Integration Tests for Two-Way Hermes <-> AIOS Gateway.

Covers:
1. HMAC-SHA256 signature calculation & verification.
2. Replay defense (reused nonces rejected).
3. Clock-skew defense (expired timestamps rejected).
4. Payload tampering detection (signature mismatch).
5. JSON-RPC 2.0 Task command dispatch & execution history.
6. Bidirectional Kanban board management via gateway RPC.
7. Cron job registry listing, updating, manual triggering, and deletion.
8. HTTP endpoint testing on ephemeral server.
"""
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hud import gateway
from hud import os_dashboard as osd


class HermesGatewaySecurityTests(unittest.TestCase):
    def setUp(self):
        self.secret = "test-secret-key-12345"
        self.nonce_cache = gateway.NonceReplayCache(ttl_seconds=10.0)

    def test_hmac_signature_generation_and_verification_success(self):
        method = "POST"
        path = "/gateway/v1/rpc"
        body = b'{"jsonrpc":"2.0","method":"hermes.ping","id":1}'
        ts = str(int(time.time()))
        nonce = "nonce-test-001"

        sig = gateway.compute_signature(self.secret, method, path, body, ts, nonce)
        headers = {
            "X-Gateway-Timestamp": ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig
        }

        ok, reason = gateway.verify_gateway_request(headers, method, path, body,
                                                    secret=self.secret, nonce_cache=self.nonce_cache)
        self.assertTrue(ok)
        self.assertIn("HMAC-SHA256", reason)

    def test_replay_attack_with_duplicate_nonce_is_blocked(self):
        method = "POST"
        path = "/gateway/v1/rpc"
        body = b'{"action":"run"}'
        ts = str(int(time.time()))
        nonce = "nonce-single-use-abc"

        sig = gateway.compute_signature(self.secret, method, path, body, ts, nonce)
        headers = {
            "X-Gateway-Timestamp": ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig
        }

        # First request must succeed
        ok, _ = gateway.verify_gateway_request(headers, method, path, body,
                                              secret=self.secret, nonce_cache=self.nonce_cache)
        self.assertTrue(ok)

        # Second request with the same nonce must be rejected as a replay attack
        with self.assertRaises(gateway.GatewayAuthError) as ctx:
            gateway.verify_gateway_request(headers, method, path, body,
                                          secret=self.secret, nonce_cache=self.nonce_cache)
        self.assertIn("Replay attack detected", str(ctx.exception))

    def test_expired_timestamp_is_blocked(self):
        method = "POST"
        path = "/gateway/v1/rpc"
        body = b'{"action":"run"}'
        old_ts = str(int(time.time()) - 350)  # 350 seconds ago (> 300s threshold)
        nonce = "nonce-old-123"

        sig = gateway.compute_signature(self.secret, method, path, body, old_ts, nonce)
        headers = {
            "X-Gateway-Timestamp": old_ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig
        }

        with self.assertRaises(gateway.GatewayAuthError) as ctx:
            gateway.verify_gateway_request(headers, method, path, body,
                                          secret=self.secret, nonce_cache=self.nonce_cache)
        self.assertIn("Clock skew threshold exceeded", str(ctx.exception))

    def test_tampered_payload_causes_signature_mismatch(self):
        method = "POST"
        path = "/gateway/v1/rpc"
        original_body = b'{"amount":"10.00"}'
        tampered_body = b'{"amount":"10000.00"}'
        ts = str(int(time.time()))
        nonce = "nonce-tamper-check"

        sig = gateway.compute_signature(self.secret, method, path, original_body, ts, nonce)
        headers = {
            "X-Gateway-Timestamp": ts,
            "X-Gateway-Nonce": nonce,
            "X-Gateway-Signature": sig
        }

        with self.assertRaises(gateway.GatewayAuthError) as ctx:
            gateway.verify_gateway_request(headers, method, path, tampered_body,
                                          secret=self.secret, nonce_cache=self.nonce_cache)
        self.assertIn("Signature mismatch", str(ctx.exception))

    def test_bearer_token_fallback(self):
        headers = {"Authorization": f"Bearer {self.secret}"}
        ok, reason = gateway.verify_gateway_request(headers, "POST", "/gateway/v1/rpc", b"{}",
                                                    secret=self.secret, nonce_cache=self.nonce_cache)
        self.assertTrue(ok)
        self.assertIn("Bearer", reason)


class HermesGatewayRPCTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cron_path = Path(self.tmp.name) / "cron_registry.json"
        self.task_path = Path(self.tmp.name) / "gateway_tasks.json"
        self.board_path = Path(self.tmp.name) / "os_board.json"

        # Initialize mock board
        osd.load_board(self.board_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rpc_ping_handshake(self):
        res = gateway.execute_gateway_rpc("hermes.ping", {})
        self.assertIn("result", res)
        self.assertTrue(res["result"]["authenticated"])
        self.assertIn("JSON-RPC 2.0", res["result"]["protocol"])

    def test_rpc_task_execute_and_history(self):
        # 1. Ping command
        res = gateway.execute_gateway_rpc("hermes.task.execute", {"command": "ping"})
        self.assertIn("result", res)
        self.assertEqual(res["result"]["status"], "completed")

        # 2. Invariant audit command
        res_audit = gateway.execute_gateway_rpc("hermes.task.execute", {"command": "audit_invariants"})
        self.assertIn("result", res_audit)
        self.assertIn("invariant", res_audit["result"]["result"])

        # 3. Task list
        res_list = gateway.execute_gateway_rpc("hermes.task.list", {"limit": 10})
        self.assertIn("tasks", res_list["result"])
        self.assertGreaterEqual(len(res_list["result"]["tasks"]), 2)

    def test_rpc_kanban_board_management(self):
        # 1. Fetch board
        res_get = gateway.execute_gateway_rpc("hermes.board.get", {})
        self.assertIn("board", res_get["result"])

        # 2. Add task via gateway mutate
        add_op = {
            "op": "task.add",
            "title": "Gateway integration verification",
            "priority": 1,
            "vital": True
        }
        res_mut = gateway.execute_gateway_rpc("hermes.board.mutate", add_op)
        self.assertEqual(res_mut["result"]["status"], "ok")

        # 3. Synchronize incoming tasks from Hermes
        sync_payload = {
            "tasks": [
                {"title": "Hermes Autonomous Discovery Task", "priority": 2, "vital": False}
            ]
        }
        res_sync = gateway.execute_gateway_rpc("hermes.board.sync", sync_payload)
        self.assertEqual(res_sync["result"]["status"], "ok")
        self.assertGreaterEqual(res_sync["result"]["synced_count"], 1)

    def test_rpc_cron_job_lifecycle(self):
        # 1. List crons
        crons = gateway.load_cron_registry(self.cron_path)
        self.assertGreaterEqual(len(crons), 4)

        # 2. Update cron job
        upd = gateway.update_cron_job("cron-backup-daily", {"expression": "0 4 * * *", "enabled": False}, path=self.cron_path)
        self.assertEqual(upd["expression"], "0 4 * * *")
        self.assertFalse(upd["enabled"])

        # 3. Trigger cron job manually
        trig = gateway.trigger_cron_job("cron-ledger-invariant", path=self.cron_path)
        self.assertEqual(trig["status"], "success")
        self.assertIn("triggered_at", trig)

        # 4. Add new custom cron
        new_cron = gateway.update_cron_job("cron-custom-test", {
            "name": "Custom Test Cron",
            "expression": "*/1 * * * *",
            "target_method": "hermes.task.execute",
            "params": {"command": "ping"}
        }, path=self.cron_path)
        self.assertEqual(new_cron["name"], "Custom Test Cron")

        # 5. Delete custom cron
        del_ok = gateway.delete_cron_job("cron-custom-test", path=self.cron_path)
        self.assertTrue(del_ok)


class HTTPGatewayIntegrationTests(unittest.TestCase):
    """Boot ephemeral HTTP servers and test two-way communication."""
    @classmethod
    def setUpClass(cls):
        import threading
        import hud_server
        import hermes_8080_server

        # Start ephemeral HUD server
        cls.hud_srv = hud_server.HUDHTTPServer(("127.0.0.1", 0), hud_server.HUDRequestHandler)
        cls.hud_port = cls.hud_srv.server_address[1]
        cls.hud_thread = threading.Thread(target=cls.hud_srv.serve_forever, daemon=True)
        cls.hud_thread.start()

        # Start ephemeral Hermes server
        cls.hermes_srv = hermes_8080_server.ThreadedHTTPServer(("127.0.0.1", 0), hermes_8080_server.HermesModelHandler)
        cls.hermes_port = cls.hermes_srv.server_address[1]
        cls.hermes_thread = threading.Thread(target=cls.hermes_srv.serve_forever, daemon=True)
        cls.hermes_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.hud_srv.shutdown()
        cls.hud_srv.server_close()
        cls.hermes_srv.shutdown()
        cls.hermes_srv.server_close()

    def test_hermes_health_endpoint(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.hermes_port}/gateway/v1/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["protocol"], "JSON-RPC 2.0 / REST Webhook")

    def test_signed_rpc_call_to_hermes_and_unauthorized_rejection(self):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.hermes_port}/gateway/v1/rpc"

        # 1. Unauthenticated request must receive 401 Unauthorized
        req_unauth = urllib.request.Request(url, data=b'{"method":"hermes.ping"}', method="POST")
        req_unauth.add_header("Content-Type", "application/json")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_unauth, timeout=3)
        self.assertEqual(ctx.exception.code, 401)

        # 2. Properly signed request must succeed
        res = gateway.send_signed_rpc(url, "hermes.ping", {})
        self.assertEqual(res.get("status"), "ok")
        self.assertTrue(res.get("result", {}).get("authenticated"))

        # 3. Signed task command execution
        res_task = gateway.send_signed_rpc(url, "hermes.task.execute", {"command": "ping"})
        self.assertEqual(res_task.get("status"), "ok")
        self.assertEqual(res_task.get("result", {}).get("status"), "completed")

    def test_hud_gateway_endpoints_and_status(self):
        import urllib.request
        # 1. GET /api/gateway/status
        status_url = f"http://127.0.0.1:{self.hud_port}/api/gateway/status"
        with urllib.request.urlopen(status_url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            st = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(st["status"], "ok")
            self.assertIn("crons_total", st)

        # 2. POST /api/gateway/tasks
        tasks_url = f"http://127.0.0.1:{self.hud_port}/api/gateway/tasks"
        body = json.dumps({"command": "ping"}).encode("utf-8")
        req = urllib.request.Request(tasks_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res["status"], "ok")

        # 3. Inbound signed webhook from Hermes to HUD /api/gateway/hermes
        inbound_url = f"http://127.0.0.1:{self.hud_port}/api/gateway/hermes"
        webhook_res = gateway.send_signed_rpc(inbound_url, "hermes.ping", {})
        self.assertEqual(webhook_res.get("status"), "ok")
        self.assertTrue(webhook_res.get("result", {}).get("authenticated"))

        # 4. GET /api/gateway/feedback
        fb_url = f"http://127.0.0.1:{self.hud_port}/api/gateway/feedback"
        with urllib.request.urlopen(fb_url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            fb_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(fb_data["status"], "ok")
            self.assertIn("sequence_id", fb_data)
            self.assertIn("feedback", fb_data)

    def test_http_ack_headers_and_anti_buffering(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.hermes_port}/gateway/v1/rpc"
        res = gateway.send_signed_rpc(url, "hermes.task.execute", {"command": "ping"}, idempotency_key="idemp-http-test-01")
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("ack", res)
        self.assertEqual(res["ack"]["status"], "ACK")
        self.assertTrue(res["ack"]["synced"])
        self.assertIn("round_trip_ms", res)
        self.assertGreater(res["round_trip_ms"], 0.0)

        # Direct HTTP header verification
        req_body = json.dumps({"jsonrpc": "2.0", "id": "direct-head", "method": "hermes.ping", "params": {}}).encode("utf-8")
        headers = gateway.create_signed_headers("POST", "/gateway/v1/rpc", req_body)
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("X-Accel-Buffering"), "no")
            self.assertIn("no-store", resp.headers.get("Cache-Control", ""))
            self.assertTrue(resp.headers.get("X-Gateway-Ack") is not None)
            self.assertTrue(resp.headers.get("X-Gateway-Seq") is not None)
            self.assertTrue(resp.headers.get("X-Gateway-RTT") is not None)


class HermesGatewayAckAndSyncUnitTests(unittest.TestCase):
    """Specific unit tests for sequence tracker, idempotency, feedback loop, and ACK receipts."""
    def setUp(self):
        self.tracker = gateway.SyncSequenceTracker(initial_seq=10)
        self.idemp = gateway.IdempotencyRegistry(ttl_seconds=60.0)
        self.loop = gateway.GatewayFeedbackLoop(buffer_size=10)

    def test_sync_sequence_tracker_advances_monotonically_and_tracks_history(self):
        self.assertEqual(self.tracker.current_seq(), 10)
        s1 = self.tracker.advance("task", "run_audit", {"target": "invariants"})
        self.assertEqual(s1, 11)
        s2 = self.tracker.advance("board", "mutate_add", {"title": "Task A"})
        self.assertEqual(s2, 12)
        self.assertEqual(self.tracker.current_seq(), 12)

        history = self.tracker.get_history(since_seq=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["sequence_id"], 11)
        self.assertEqual(history[0]["scope"], "task")
        self.assertEqual(history[1]["sequence_id"], 12)
        self.assertEqual(history[1]["scope"], "board")

    def test_idempotency_registry_caching_and_replay(self):
        test_key = "idemp-unit-key-42"
        self.assertIsNone(self.idemp.get(test_key))

        mock_payload = {"ack_id": "ack-12345", "status": "ACK", "sequence_id": 15}
        self.idemp.set(test_key, mock_payload)

        cached = self.idemp.get(test_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["ack_id"], "ack-12345")

        # Test in execute_gateway_rpc
        gateway.GLOBAL_IDEMPOTENCY_REGISTRY.set("idemp-rpc-test", {"result": "cached-ok", "ack": {"status": "ACK"}})
        replay_res = gateway.execute_gateway_rpc("hermes.ping", {"idempotency_key": "idemp-rpc-test"})
        self.assertTrue(replay_res.get("idempotent_replay"))
        self.assertEqual(replay_res["result"], {"result": "cached-ok", "ack": {"status": "ACK"}})

    def test_gateway_feedback_loop_rtt_metrics(self):
        # Empty loop
        empty_metrics = self.loop.get_metrics()
        self.assertEqual(empty_metrics["sync_health"], "STANDBY")
        self.assertEqual(empty_metrics["sample_count"], 0)

        # Record samples
        for rtt in [5.0, 10.0, 12.0, 8.0, 15.0]:
            self.loop.record_probe(rtt, success=True)

        m = self.loop.get_metrics()
        self.assertEqual(m["sample_count"], 5)
        self.assertEqual(m["latest_rtt_ms"], 15.0)
        self.assertEqual(m["min_rtt_ms"], 5.0)
        self.assertEqual(m["max_rtt_ms"], 15.0)
        self.assertEqual(m["sync_health"], "OPTIMAL_REALTIME")

        # Buffer overflow test
        for i in range(20):
            self.loop.record_probe(float(i), success=True)
        m_over = self.loop.get_metrics()
        self.assertEqual(m_over["sample_count"], 10)  # capped at buffer_size 10

    def test_strict_ack_receipt_structure(self):
        receipt = gateway.make_ack_receipt(
            status="ACK",
            scope="task",
            op="execute",
            result={"status": "completed"},
            idempotency_key="idemp-receipt-test",
            rtt_ms=4.2
        )
        self.assertTrue(receipt["ack_id"].startswith("ack-"))
        self.assertEqual(receipt["status"], "ACK")
        self.assertTrue(receipt["synced"])
        self.assertEqual(receipt["round_trip_ms"], 4.2)
        self.assertIn("sequence_id", receipt)
        self.assertEqual(receipt["idempotency_key"], "idemp-receipt-test")

    def test_sync_status_and_worker_ack_rpc(self):
        # 1. hermes.gateway.sync_status
        sync_res = gateway.execute_gateway_rpc("hermes.gateway.sync_status", {})
        self.assertIn("result", sync_res)
        self.assertIn("sequence_id", sync_res["result"])
        self.assertIn("feedback", sync_res["result"])
        self.assertIn("history", sync_res["result"])
        self.assertIn("ack", sync_res)

        # 2. hermes.gateway.ack
        ack_res = gateway.execute_gateway_rpc("hermes.gateway.ack", {
            "ack_id": "ack-worker-999",
            "task_id": "task-test-1",
            "state": "completed"
        })
        self.assertEqual(ack_res["result"]["status"], "ok")
        self.assertTrue(ack_res["result"]["acknowledged"])
        self.assertEqual(ack_res["result"]["ack_id"], "ack-worker-999")


if __name__ == "__main__":
    unittest.main()
