#!/usr/bin/env python3
"""
tests/test_routing_verification.py
==================================
Unit tests verifying the test_routing_pipeline.py standalone workflow:
1. Injects task into [ INBOX ] assigned strictly to aios-systems-architect.
2. Background daemon state transition [ INBOX ] -> running -> [ DONE ].
3. Staging buffer population (table and filesystem).
4. Air-gap isolation verification.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path to import root test_routing_pipeline
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import test_routing_pipeline
from test_routing_pipeline import (
    inject_routing_task,
    query_job_state,
    verify_staging_buffer,
    verify_air_gap_isolation,
    background_daemon_worker,
    run_routing_verification,
)


class TestRoutingPipelineVerification(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_inject_task_inbox_assigned_to_architect(self):
        """Verifies task is injected in [ INBOX ] state and assigned to aios-systems-architect."""
        job_id = "test-route-inject-01"
        injected = inject_routing_task(
            db_path=self.db_path,
            job_id=job_id,
            assigned_agent="aios-systems-architect",
            instruction="Write a Python script that prints 'Routing Test Successful'",
        )
        self.assertTrue(injected)

        state = query_job_state(self.db_path, job_id)
        self.assertEqual(state, "[ INBOX ]")

        # Verify assigned agent in jobs table
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT scope_id, payload FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            self.assertEqual(row["scope_id"], "aios-systems-architect")
            payload = json.loads(row["payload"])
            self.assertEqual(payload["assigned_agent"], "aios-systems-architect")
            self.assertIn("Routing Test Successful", payload["instruction"])
        finally:
            conn.close()

    def test_background_worker_routes_to_staging_buffer_and_marks_done(self):
        """Verifies background worker moves job to [ DONE ] and populates staging_buffer."""
        job_id = "test-route-worker-02"
        inject_routing_task(self.db_path, job_id)

        # Run background worker with minimal delay for unit testing
        background_daemon_worker(self.db_path, job_id, delay_sec=0.01)

        # Check job reached [ DONE ]
        state = query_job_state(self.db_path, job_id)
        self.assertEqual(state, "[ DONE ]")

        # Check staging buffer
        staged_ok, payload = verify_staging_buffer(self.db_path, job_id)
        self.assertTrue(staged_ok)
        self.assertIn("print('Routing Test Successful')", payload)

    def test_air_gap_isolation_pass_when_clean(self):
        """Verifies air-gap check passes when outbox is completely clean."""
        job_id = "test-route-clean-03"
        isolation_ok = verify_air_gap_isolation(job_id)
        self.assertTrue(isolation_ok)

    def test_air_gap_isolation_fails_on_leak(self):
        """Verifies air-gap check detects routing breach if payload leaks into client outbox."""
        job_id = "test-route-leak-04"
        from test_routing_pipeline import CLIENT_OUTBOX_DIR
        CLIENT_OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        leak_file = CLIENT_OUTBOX_DIR / f"leak_{job_id}.txt"
        leak_file.write_text("Routing Test Successful leak", encoding="utf-8")

        try:
            isolation_ok = verify_air_gap_isolation(job_id)
            self.assertFalse(isolation_ok)
        finally:
            if leak_file.exists():
                leak_file.unlink()

    def test_end_to_end_verification_pipeline(self):
        """Verifies the complete run_routing_verification routine succeeds."""
        success = run_routing_verification(custom_db=self.db_path)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
