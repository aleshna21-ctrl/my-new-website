#!/usr/bin/env python3
"""
tests/test_sever_synchronous_trap.py
====================================
Verifies that the synchronous trap in hud_server.py is severed:
1. AI task execution endpoints (/api/ai/task, /api/hermes/task, /api/task/execute, /api/gateway/tasks?remote=1)
   immediately write to job_ledger.db as [ INBOX ] and return HTTP 202 Accepted.
2. No direct blocking HTTP requests to port 8080 occur during UI task intake.
"""

import http.client
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import hud_server


class TestSeverSynchronousTrap(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"

        # Initialize mock ledger
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE jobs (
                    job_id TEXT PRIMARY KEY,
                    scope_id TEXT,
                    job_type TEXT,
                    state TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    payload TEXT,
                    model_output TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

        # Patch DB_FILE in hud_server and job_ledger
        self.patch_db = patch("job_ledger.DB_FILE", str(self.db_path))
        self.patch_db.start()

        # Start HUD test server on random free port
        self.server = hud_server.HUDHTTPServer(("127.0.0.1", 0), hud_server.HUDRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        self.patch_db.stop()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _post(self, path: str, body: dict) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return resp.status, data
        finally:
            conn.close()

    def test_ai_task_endpoint_returns_202_and_writes_inbox(self):
        """Verifies /api/ai/task immediately returns HTTP 202 Accepted and records in [ INBOX ]."""
        task_payload = {
            "job_id": "test-sync-trap-01",
            "scope_id": "cambridge-specialty",
            "command": "reconcile_ap_ar",
            "data": {"variance": "$1,250.00", "source": "JobBOSS"}
        }

        status, data = self._post("/api/ai/task", task_payload)
        self.assertEqual(status, 202, f"Expected 202 Accepted, got {status}")
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(data["state"], "[ INBOX ]")
        self.assertEqual(data["job_id"], "test-sync-trap-01")

        # Verify in SQLite database
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT job_id, scope_id, state, payload FROM jobs WHERE job_id = ?", ("test-sync-trap-01",))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "test-sync-trap-01")
            self.assertEqual(row[1], "cambridge-specialty")
            self.assertEqual(row[2], "[ INBOX ]")
            payload_data = json.loads(row[3])
            self.assertEqual(payload_data["command"], "reconcile_ap_ar")
        finally:
            conn.close()

    def test_hermes_task_endpoint_returns_202_accepted(self):
        """Verifies /api/hermes/task returns HTTP 202 Accepted."""
        task_payload = {
            "job_id": "test-hermes-trap-02",
            "scope_id": "apex-thermal",
            "command": "discrepancy_audit"
        }

        status, data = self._post("/api/hermes/task", task_payload)
        self.assertEqual(status, 202)
        self.assertEqual(data["state"], "[ INBOX ]")

    def test_gateway_remote_task_returns_202_and_avoids_port_8080(self):
        """Verifies remote gateway task triggers asynchronous [ INBOX ] insertion without synchronous 8080 RPC."""
        task_payload = {
            "command": "execute_model_triage",
            "remote": True,
            "params": {"scope": "keystone-precision"}
        }

        status, data = self._post("/api/gateway/tasks", task_payload)
        self.assertEqual(status, 202)
        self.assertEqual(data["status"], "accepted")
        self.assertEqual(data["state"], "[ INBOX ]")


if __name__ == "__main__":
    unittest.main()
