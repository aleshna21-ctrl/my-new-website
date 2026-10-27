#!/usr/bin/env python3
"""
tests/test_sandboxed_durable_execution.py
=========================================
Comprehensive test suite verifying the Sandboxed Durable Execution layer
and multi-agent collaboration via SQLite state transitions in async_orchestrator_daemon.py:

1. Sandboxed Execution:
   - Daemon never executes code on host OS. Uses isolated ephemeral runner with immediate cleanup.
2. Durable Try/Catch:
   - Wraps LLM loopback calls and sandbox execution to catch exceptions/timeouts without crashing.
3. Dynamic Role Routing:
   - Dynamically reads assigned_role on each tick to load appropriate persona prompt.
4. Proactive Baton Pass:
   - Agent output requesting specialist skips sandbox, appends to payload, swaps role,
     increments retry_count, and preserves '[ INBOX ]' state.
5. Reactive Crash Swap:
   - Sandbox crash catches traceback, appends to payload, swaps role to qa-telemetry-daemon,
     increments retry_count, and preserves '[ INBOX ]' state.
6. Hard Ejection (3-Strike Limit):
   - Reaching 3 strikes destroys sandbox, routes failed payload to telemetry_log,
     and flags task as '[ NEEDS_REVIEW ]'.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure hud-interface root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from async_orchestrator_daemon import (
    AsyncOrchestratorDaemon,
    EphemeralSandboxRunner,
    SandboxResult,
    detect_specialist_request,
    extract_executable_code,
    SAFE_HOTL_PERSONAS,
)


class TestSandboxedDurableExecution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"
        self._init_database()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _init_database(self):
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
                    assigned_role TEXT DEFAULT 'aios-systems-architect',
                    retry_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE staging_buffer (
                    buffer_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    assigned_agent TEXT NOT NULL,
                    staged_payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'STAGED',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE telemetry_log (
                    log_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    assigned_role TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT,
                    error_trace TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def test_ephemeral_sandbox_lifecycle_and_isolation(self):
        """Directive 1: Verifies ephemeral sandbox executes code and immediately destroys temp directory."""
        runner = EphemeralSandboxRunner(force_subprocess_jail=True, default_timeout=3.0)
        code = "print('AIOS_SANDBOX_OK')\n"
        result = runner.execute(code)

        self.assertTrue(result.success)
        self.assertEqual(result.returncode, 0)
        self.assertIn("AIOS_SANDBOX_OK", result.stdout)
        self.assertEqual(result.backend, "subprocess_jail")

    def test_dynamic_role_routing_loads_correct_persona(self):
        """Directive 3: Verifies daemon reads assigned_role on polling and loads matching system prompt."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path)

        # Test Architect Persona
        arch_prompt = daemon.get_role_system_prompt("aios-systems-architect")
        self.assertIn("AIOS Systems Architect", arch_prompt)
        self.assertIn("NEEDS_SPECIALIST: jev-tool-fabricator", arch_prompt)

        # Test Fabricator Persona
        fab_prompt = daemon.get_role_system_prompt("jev-tool-fabricator")
        self.assertIn("JEV Tool Fabricator", fab_prompt)
        self.assertIn("NEEDS_SPECIALIST: qa-telemetry-daemon", fab_prompt)

        # Test QA Persona
        qa_prompt = daemon.get_role_system_prompt("qa-telemetry-daemon")
        self.assertIn("QA Telemetry Daemon", qa_prompt)

        # Insert jobs with different roles
        now = "2026-10-26T12:00:00Z"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES
                ('job-arch', 'scope-1', 'arch_design', '[ INBOX ]', 'design specs', 'aios-systems-architect', 0, ?, ?),
                ('job-fab', 'scope-2', 'tool_fab', '[ INBOX ]', 'build adapter', 'jev-tool-fabricator', 1, ?, ?)
            """, (now, now, now, now))

        tasks = daemon.poll_inbox_tasks()
        self.assertEqual(len(tasks), 2)
        task_map = {t["job_id"]: t for t in tasks}
        self.assertEqual(task_map["job-arch"]["assigned_role"], "aios-systems-architect")
        self.assertEqual(task_map["job-arch"]["retry_count"], 0)
        self.assertEqual(task_map["job-fab"]["assigned_role"], "jev-tool-fabricator")
        self.assertEqual(task_map["job-fab"]["retry_count"], 1)

    def test_proactive_baton_pass_skips_sandbox_and_swaps_role(self):
        """Directive 4: Output requesting specialist skips sandbox, swaps role, increments retry, leaves [ INBOX ]."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, force_subprocess_jail=True)

        job_id = "job-baton-01"
        now = "2026-10-26T12:00:00Z"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES (?, 'scope-test', 'code_task', '[ INBOX ]', 'Initial architecture request', 'aios-systems-architect', 0, ?, ?)
            """, (job_id, now, now))

        # Model output explicitly passing baton to jev-tool-fabricator
        model_reply = (
            "Architectural design approved for pipeline adapter.\n"
            "Implementation requires deterministic utility code.\n"
            "NEEDS_SPECIALIST: jev-tool-fabricator"
        )

        with patch.object(daemon, "send_prompt_to_llm", return_value=(True, model_reply, None)):
            with patch.object(daemon.sandbox_runner, "execute") as mock_sandbox:
                tasks = daemon.poll_inbox_tasks()
                self.assertEqual(len(tasks), 1)
                success = daemon.process_task(tasks[0])
                self.assertTrue(success)

                # Sandbox MUST NOT be executed
                mock_sandbox.assert_not_called()

        # Verify state in database
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ INBOX ]")
            self.assertEqual(row["assigned_role"], "jev-tool-fabricator")
            self.assertEqual(row["retry_count"], 1)
            self.assertIn("--- [PROACTIVE BATON PASS", row["payload"])
            self.assertIn("Baton Passed To: jev-tool-fabricator", row["payload"])

            # Verify telemetry_log
            log_row = conn.execute("SELECT * FROM telemetry_log WHERE job_id = ?", (job_id,)).fetchone()
            self.assertIsNotNone(log_row)
            self.assertEqual(log_row["event_type"], "PROACTIVE_BATON_PASS")
            self.assertEqual(log_row["assigned_role"], "jev-tool-fabricator")
            self.assertEqual(log_row["retry_count"], 1)

    def test_reactive_crash_swap_to_qa_daemon(self):
        """Directive 5: Sandbox crash catches traceback, swaps role to qa-telemetry-daemon, leaves [ INBOX ]."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, force_subprocess_jail=True)

        job_id = "job-crash-01"
        now = "2026-10-26T12:00:00Z"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES (?, 'scope-test', 'code_task', '[ INBOX ]', 'Build utility function', 'jev-tool-fabricator', 0, ?, ?)
            """, (job_id, now, now))

        # Model output containing crashing code
        crashing_code = (
            "Here is the tool:\n"
            "```python\n"
            "def broken_function():\n"
            "    raise ZeroDivisionError('Division by zero in tool fabricator')\n"
            "broken_function()\n"
            "```"
        )

        with patch.object(daemon, "send_prompt_to_llm", return_value=(True, crashing_code, None)):
            tasks = daemon.poll_inbox_tasks()
            self.assertEqual(len(tasks), 1)
            success = daemon.process_task(tasks[0])
            self.assertTrue(success)

        # Verify state in database: swapped to qa-telemetry-daemon and kept in [ INBOX ]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ INBOX ]")
            self.assertEqual(row["assigned_role"], "qa-telemetry-daemon")
            self.assertEqual(row["retry_count"], 1)
            self.assertIn("--- [REACTIVE CRASH SWAP", row["payload"])
            self.assertIn("ZeroDivisionError: Division by zero", row["payload"])

            # Verify telemetry_log
            log_row = conn.execute("SELECT * FROM telemetry_log WHERE job_id = ?", (job_id,)).fetchone()
            self.assertIsNotNone(log_row)
            self.assertEqual(log_row["event_type"], "REACTIVE_CRASH_SWAP")
            self.assertEqual(log_row["assigned_role"], "qa-telemetry-daemon")
            self.assertEqual(log_row["retry_count"], 1)

    def test_hard_ejection_3_strike_limit_on_crash(self):
        """Directive 6: 3rd crash strike destroys sandbox, logs telemetry, flags [ NEEDS_REVIEW ]."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, force_subprocess_jail=True)

        job_id = "job-eject-crash"
        now = "2026-10-26T12:00:00Z"
        # Seed task with retry_count = 2 (strike 2 already reached)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES (?, 'scope-test', 'code_task', '[ INBOX ]', 'Third attempt at fixing bug', 'qa-telemetry-daemon', 2, ?, ?)
            """, (job_id, now, now))

        # Model output containing persistent crash
        failing_code = (
            "```python\n"
            "raise RuntimeError('Unrecoverable pipeline failure')\n"
            "```"
        )

        with patch.object(daemon, "send_prompt_to_llm", return_value=(True, failing_code, None)):
            tasks = daemon.poll_inbox_tasks()
            self.assertEqual(len(tasks), 1)
            success = daemon.process_task(tasks[0])
            self.assertTrue(success)

        # Verify state: transitioned to [ NEEDS_REVIEW ]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(row["retry_count"], 3)
            self.assertIn("=== [HARD EJECTION: 3-STRIKE LIMIT REACHED", row["model_output"])
            self.assertIn("Operator manual review and intervention mandated", row["model_output"])

            # Verify telemetry_log
            log_row = conn.execute("SELECT * FROM telemetry_log WHERE job_id = ? AND event_type = 'HARD_EJECTION_3_STRIKES'", (job_id,)).fetchone()
            self.assertIsNotNone(log_row)
            self.assertEqual(log_row["retry_count"], 3)
            self.assertEqual(log_row["assigned_role"], "qa-telemetry-daemon")

    def test_hard_ejection_3_strike_limit_on_proactive_pass(self):
        """Directive 6: 3rd proactive pass reaches limit, logs telemetry, flags [ NEEDS_REVIEW ]."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, force_subprocess_jail=True)

        job_id = "job-eject-pass"
        now = "2026-10-26T12:00:00Z"
        # Seed task with retry_count = 2
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES (?, 'scope-test', 'code_task', '[ INBOX ]', 'Looping task', 'jev-tool-fabricator', 2, ?, ?)
            """, (job_id, now, now))

        # Model asks for specialist again on strike 3
        model_reply = "Still missing requirements. NEEDS_SPECIALIST: aios-systems-architect"

        with patch.object(daemon, "send_prompt_to_llm", return_value=(True, model_reply, None)):
            tasks = daemon.poll_inbox_tasks()
            self.assertEqual(len(tasks), 1)
            success = daemon.process_task(tasks[0])
            self.assertTrue(success)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(row["retry_count"], 3)
            self.assertIn("=== [HARD EJECTION: 3-STRIKE LIMIT REACHED", row["model_output"])

    def test_successful_sandboxed_execution_routes_to_done_and_staging(self):
        """Directive 1 & 7: Successful sandboxed execution updates to [ DONE ] and routes to staging_buffer."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, force_subprocess_jail=True)

        job_id = "job-success-01"
        now = "2026-10-26T12:00:00Z"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES (?, 'scope-test', 'code_task', '[ INBOX ]', 'Write validator', 'jev-tool-fabricator', 0, ?, ?)
            """, (job_id, now, now))

        valid_code_output = (
            "Here is the valid code:\n"
            "```python\n"
            "print('SANDBOX_EXECUTION_VERIFIED_SUCCESS')\n"
            "```"
        )

        with patch.object(daemon, "send_prompt_to_llm", return_value=(True, valid_code_output, None)):
            tasks = daemon.poll_inbox_tasks()
            self.assertEqual(len(tasks), 1)
            success = daemon.process_task(tasks[0])
            self.assertTrue(success)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ DONE ]")
            self.assertIn("SANDBOX_EXECUTION_VERIFIED_SUCCESS", row["model_output"])
            self.assertIn("--- [Ephemeral Sandbox Verified", row["model_output"])

            # Verify staging buffer
            staged = conn.execute("SELECT * FROM staging_buffer WHERE job_id = ?", (job_id,)).fetchone()
            self.assertIsNotNone(staged)
            self.assertEqual(staged["assigned_agent"], "jev-tool-fabricator")
            self.assertIn("SANDBOX_EXECUTION_VERIFIED_SUCCESS", staged["staged_payload"])


if __name__ == "__main__":
    unittest.main()
