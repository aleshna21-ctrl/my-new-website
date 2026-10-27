#!/usr/bin/env python3
"""
tests/test_async_orchestrator_daemon.py
=======================================
Unit test suite verifying the AsyncOrchestratorDaemon:
1. Isolated Polling: Queries job_ledger.db specifically for '[ INBOX ]' tasks.
2. Message Translation: Formats task payload into standard text-based LLM prompt.
3. Asynchronous Execution: Handles network execution, responses, and timeouts.
4. State Management: Transitions row to '[ STAGED / REVIEW ]' and appends output.
5. Zero Interference: Ensures existing routes, tables, and other job states are untouched.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

from async_orchestrator_daemon import AsyncOrchestratorDaemon


class TestAsyncOrchestratorDaemon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"
        self._init_mock_ledger()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _init_mock_ledger(self):
        conn = sqlite3.connect(str(self.db_path))
        try:
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
            # Insert mixed states
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, attempt_count, created_at, updated_at)
                VALUES
                ('job-completed-01', 'scope-a', 'reconciliation', 'completed', 1, '2026-10-26T10:00:00Z', '2026-10-26T10:01:00Z'),
                ('job-running-02', 'scope-b', 'risk_extraction', 'running', 1, '2026-10-26T10:02:00Z', '2026-10-26T10:03:00Z'),
                ('job-inbox-03', 'cambridge-specialty', 'reconciliation', '[ INBOX ]', 0, '2026-10-26T10:05:00Z', '2026-10-26T10:05:00Z'),
                ('job-inbox-04', 'apex-thermal', 'discrepancy_triage', '[ INBOX ]', 0, '2026-10-26T10:06:00Z', '2026-10-26T10:06:00Z')
            """)
            conn.commit()
        finally:
            conn.close()

    def test_schema_evolution_non_destructive(self):
        """Verifies ensure_schema safely adds payload and model_output columns."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path)
        with daemon.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(jobs)")
            cols = [col[1] for col in cur.fetchall()]
            self.assertIn("payload", cols)
            self.assertIn("model_output", cols)

    def test_isolated_polling_queries_only_inbox(self):
        """Verifies only tasks in '[ INBOX ]' state are returned."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path)
        tasks = daemon.poll_inbox_tasks()

        self.assertEqual(len(tasks), 2)
        job_ids = [t["job_id"] for t in tasks]
        self.assertIn("job-inbox-03", job_ids)
        self.assertIn("job-inbox-04", job_ids)
        self.assertNotIn("job-completed-01", job_ids)
        self.assertNotIn("job-running-02", job_ids)

        for task in tasks:
            self.assertEqual(task["state"], "[ INBOX ]")

    def test_message_translation_formats_standard_prompt(self):
        """Verifies task is translated into standard 'Analyze the following client data: ...' format."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path)
        test_payload = {
            "client_name": "Apex Thermal Solutions",
            "vertical": "Commercial Refrigeration/HVAC",
            "bottlenecks": ["OEM compressor core credits", "ServiceTitan work orders"],
            "discrepancy_amount": "$4,250.00"
        }

        task = {
            "job_id": "job-inbox-04",
            "scope_id": "apex-thermal",
            "job_type": "discrepancy_triage",
            "payload": json.dumps(test_payload)
        }

        prompt = daemon.translate_task_to_prompt(task)
        self.assertTrue(prompt.startswith("Analyze the following client data:"))
        self.assertIn("Apex Thermal Solutions", prompt)
        self.assertIn("Commercial Refrigeration/HVAC", prompt)
        self.assertIn("OEM compressor core credits", prompt)
        self.assertIn("Identify operational context, target ERP/accounting systems", prompt)

    def test_state_management_transitions_to_done_and_appends_output(self):
        """Verifies state updates to '[ DONE ]' and model output is appended."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path)
        job_id = "job-inbox-03"
        model_output = "Identified reconciliation drag in JobBOSS month-end close. Recommend 3-way PO match."

        success = daemon.update_to_done(job_id, model_output, from_state="[ INBOX ]")
        self.assertTrue(success)

        with daemon.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT state, model_output, attempt_count FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["state"], "[ DONE ]")
            self.assertIn("Identified reconciliation drag in JobBOSS", row["model_output"])
            self.assertIn("[Ollama Analysis Staged", row["model_output"])
            self.assertEqual(row["attempt_count"], 1)

    def test_timeout_handling_graceful(self):
        """Verifies timeout errors are caught and recorded without crashing."""
        daemon = AsyncOrchestratorDaemon(
            db_path=self.db_path,
            endpoint="http://127.0.0.1:8080/v1/chat/completions",
            timeout_sec=0.01,
            allow_simulation=False
        )

        with patch("urllib.request.OpenerDirector.open", side_effect=TimeoutError("Connection timed out")):
            success, error_msg, kind = daemon.send_prompt_to_llm("Analyze test data")
            self.assertFalse(success)
            self.assertEqual(kind, "timeout")
            self.assertIn("timed out", error_msg.lower())

    def test_timeout_with_simulation_fallback(self):
        """Verifies timeout with allow_simulation returns simulated analysis output."""
        daemon = AsyncOrchestratorDaemon(
            db_path=self.db_path,
            timeout_sec=0.01,
            allow_simulation=True
        )

        with patch("urllib.request.OpenerDirector.open", side_effect=TimeoutError("Connection timed out")):
            success, response_text, kind = daemon.send_prompt_to_llm("Analyze test data")
            self.assertTrue(success)
            self.assertIsNone(kind)
            self.assertIn("SIMULATED OLLAMA FALLBACK", response_text)

    def test_end_to_end_poll_and_process_once(self):
        """Verifies full cycle: poll '[ INBOX ]' -> translate -> simulate LLM -> update '[ DONE ]'."""
        daemon = AsyncOrchestratorDaemon(
            db_path=self.db_path,
            allow_simulation=True
        )

        results = daemon.poll_and_process_once()
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["success"] for r in results))

        # Check that both jobs are now [ DONE ]
        with daemon.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT job_id, state, model_output FROM jobs WHERE job_id IN ('job-inbox-03', 'job-inbox-04')")
            rows = cur.fetchall()
            for row in rows:
                self.assertEqual(row["state"], "[ DONE ]")
                self.assertTrue(len(row["model_output"]) > 0)

        # Check zero-interference on completed and running jobs
        with daemon.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT job_id, state FROM jobs WHERE job_id IN ('job-completed-01', 'job-running-02')")
            untouched_rows = {r["job_id"]: r["state"] for r in cur.fetchall()}
            self.assertEqual(untouched_rows["job-completed-01"], "completed")
            self.assertEqual(untouched_rows["job-running-02"], "running")

    def test_zero_interference_with_empty_inbox(self):
        """Verifies daemon does nothing when no [ INBOX ] jobs exist."""
        # Clean all [ INBOX ] jobs
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM jobs WHERE state = '[ INBOX ]'")
            conn.commit()
        finally:
            conn.close()

        daemon = AsyncOrchestratorDaemon(db_path=self.db_path)
        tasks = daemon.poll_inbox_tasks()
        self.assertEqual(len(tasks), 0)

        results = daemon.poll_and_process_once()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
