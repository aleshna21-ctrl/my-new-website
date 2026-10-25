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


if __name__ == "__main__":
    unittest.main()
