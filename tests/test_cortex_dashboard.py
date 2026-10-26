"""
Tests for Next Cortex Anti-Gravity Dashboard, Credits Monitor,
Real-Time Visualization Skill, Hierarchy Layout, and SQLite Data Rendering.
"""
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.request
import urllib.error

import hud_server as hud


class NextCortexDashboardUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_job_ledger.db")

        # Initialize SQLite test database with jobs and terminal events
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE jobs (
                    job_id TEXT PRIMARY KEY,
                    scope_id TEXT,
                    job_type TEXT,
                    state TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE hud_terminal_events (
                    event_id TEXT PRIMARY KEY,
                    job_id TEXT,
                    state TEXT,
                    recorded_at TEXT
                )
            """)
            conn.execute("""
                INSERT INTO jobs VALUES
                ('job-test-01', 'vetpowered-cnc', 'reconciliation', 'completed', 1, '2026-10-25T10:00:00Z', '2026-10-25T10:00:01Z'),
                ('job-test-02', 'cambridge-specialty', 'risk_extraction', 'running', 1, '2026-10-25T10:05:00Z', '2026-10-25T10:05:02Z'),
                ('job-test-03', 'adversarial-batch-01', 'reconciliation', 'quarantined', 2, '2026-10-25T10:10:00Z', '2026-10-25T10:10:03Z')
            """)
            conn.execute("""
                INSERT INTO hud_terminal_events VALUES
                ('evt-term-01', 'job-test-01', 'completed', '2026-10-25T10:00:01Z'),
                ('evt-term-02', 'job-test-03', 'quarantined', '2026-10-25T10:10:03Z')
            """)
            conn.commit()

        self._orig_db_fn = hud.get_db_path
        hud.get_db_path = lambda: self.db_path

    def tearDown(self):
        hud.get_db_path = self._orig_db_fn
        try:
            import shutil
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_cortex_credits_monitoring(self):
        credits_info = hud.get_cortex_credits()
        self.assertEqual(credits_info["total_budget"], 100000)
        self.assertGreater(credits_info["credits_remaining"], 0)
        self.assertGreater(credits_info["credits_consumed"], 0)
        self.assertIn("usage_percent", credits_info)
        self.assertIn("reset_countdown_seconds", credits_info)
        self.assertIn("qwen3:4b", credits_info["active_model"])
        self.assertIn(credits_info["quota_status"], ("HEALTHY", "WARNING", "CRITICAL"))

    def test_cortex_automated_tasks(self):
        tasks_data = hud.get_cortex_automated_tasks()
        self.assertIn("auto_accept_enabled", tasks_data)
        self.assertIsInstance(tasks_data["tasks"], list)
        self.assertIn("total_automated_tasks", tasks_data)

    def test_sqlite_ledger_reading(self):
        ledger = hud.get_sqlite_ledger_data()
        self.assertIn("tables", ledger)
        self.assertIn("jobs", ledger["tables"])
        self.assertEqual(ledger["tables"]["jobs"]["row_count"], 3)
        self.assertEqual(len(ledger["jobs"]), 3)
        self.assertEqual(len(ledger["terminal_events"]), 2)

        job_ids = [j["job_id"] for j in ledger["jobs"]]
        self.assertIn("job-test-01", job_ids)
        self.assertIn("job-test-02", job_ids)
        self.assertIn("job-test-03", job_ids)

    def test_cortex_hierarchy_layout_graph(self):
        hierarchy = hud.get_cortex_hierarchy()
        self.assertIn("nodes", hierarchy)
        self.assertIn("links", hierarchy)
        self.assertIn("layers", hierarchy)

        # Check multi-layer node presence
        node_types = {n["type"] for n in hierarchy["nodes"]}
        self.assertIn("root", node_types)
        self.assertIn("scope", node_types)
        self.assertIn("job", node_types)
        self.assertIn("diode", node_types)

        # Check layers array
        self.assertEqual(len(hierarchy["layers"]), 4)

        # Verify links connect valid sources and targets
        node_ids = {n["id"] for n in hierarchy["nodes"]}
        for link in hierarchy["links"]:
            self.assertIn(link["source"], node_ids)
            self.assertIn(link["target"], node_ids)

    def test_cortex_streaming_series(self):
        pt = hud.record_cortex_streaming_point()
        self.assertIn("ts", pt)
        self.assertIn("credits_remaining", pt)
        self.assertIn("burn_rate", pt)
        self.assertIn("jobs_active", pt)
        self.assertIn("jobs_completed", pt)

        series = hud.get_cortex_streaming_series()
        self.assertIsInstance(series, list)
        self.assertGreaterEqual(len(series), 1)
        self.assertLessEqual(len(series), 60)


class NextCortexDashboardHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        cls.server = hud.HUDHTTPServer(("127.0.0.1", 0), hud.HUDRequestHandler)
        cls.server_port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _get(self, path: str):
        req = urllib.request.Request(f"http://127.0.0.1:{self.server_port}{path}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, resp.headers, data

    def _post(self, path: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.server_port}{path}",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, resp.headers, data

    def test_http_cortex_credits(self):
        status, headers, data = self._get("/api/cortex/credits")
        self.assertEqual(status, 200)
        self.assertEqual(data["total_budget"], 100000)
        self.assertIn("credits_remaining", data)
        self.assertIn("usage_percent", data)

    def test_http_cortex_tasks(self):
        status, headers, data = self._get("/api/cortex/tasks")
        self.assertEqual(status, 200)
        self.assertIn("auto_accept_enabled", data)
        self.assertIn("tasks", data)

    def test_http_cortex_auto_accept_toggle(self):
        status, headers, data = self._post("/api/cortex/auto-accept", {"enabled": True})
        self.assertEqual(status, 200)
        self.assertTrue(data["auto_accept_enabled"])

        status, headers, data = self._post("/api/cortex/auto-accept", {"enabled": False})
        self.assertEqual(status, 200)
        self.assertFalse(data["auto_accept_enabled"])

        # Reset to True
        self._post("/api/cortex/auto-accept", {"enabled": True})

    def test_http_cortex_hierarchy(self):
        status, headers, data = self._get("/api/cortex/hierarchy")
        self.assertEqual(status, 200)
        self.assertIn("nodes", data)
        self.assertIn("links", data)
        self.assertIn("layers", data)

    def test_http_cortex_streaming_series(self):
        status, headers, data = self._get("/api/cortex/streaming-series")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["series"], list)

    def test_http_sqlite_ledger(self):
        status, headers, data = self._get("/api/sqlite/ledger")
        self.assertEqual(status, 200)
        self.assertIn("tables", data)
        self.assertIn("jobs", data)


if __name__ == "__main__":
    unittest.main()
