#!/usr/bin/env python3
"""
tests/test_hardened_state_machine.py
====================================
Comprehensive test suite verifying the hardened multi-path state machine in
async_orchestrator_daemon.py:

1. Concurrency Lock:
   - Enforces strict 1-active-LLM-agent limit.
   - Verifies no other row is in an [ ACTIVE_* ] state before pulling new tasks.
2. Atomic Transitions:
   - Uses SQLite BEGIN IMMEDIATE to lock rows atomically into [ ACTIVE_* ] states.
3. The Matrix - Ingestion & Extraction:
   - [ NEW_PAYLOAD ] -> boundary-enforcer -> [ PAYLOAD_CLEAN ] -> structural-extractor -> logic-synthesizer.
4. The Matrix - Dynamic Branching:
   - logic-synthesizer branches to [ NEEDS_CODE ] or [ NEEDS_CONTENT ].
5. The Matrix - Sandbox Path:
   - [ NEEDS_CODE ] -> systems-engineer -> [ BLUEPRINT_READY ] -> code-fabricator -> sandbox execution -> [ DONE ].
   - Crash tracebacks route to resilience-warden with 3-strike escalation to [ NEEDS_REVIEW ].
6. The Matrix - Content Path:
   - [ NEEDS_CONTENT ] -> content-drafter -> [ DRAFT_READY ] -> boundary-enforcer -> execution-dispatcher -> [ DONE ].
7. Resilient Sweeper:
   - trend-monitor detects tasks stalled in [ ACTIVE_* ] for >60s.
   - resilience-warden executes soft reset (attempts 1 & 2).
   - 3rd failed reset escalates task to [ NEEDS_REVIEW ].
8. Dual-Environment Routing:
   - General deliverables route to staging_buffer; sensitive data routes to offline-restricted directory.
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

# Ensure hud-interface root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from async_orchestrator_daemon import (
    AsyncOrchestratorDaemon,
    EphemeralSandboxRunner,
    SandboxResult,
    SAFE_HOTL_PERSONAS,
    PENDING_TO_ACTIVE_LOCK,
    ROLE_TO_ACTIVE_LOCK,
)


class TestHardenedStateMachine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"
        self._init_database()
        self.daemon = AsyncOrchestratorDaemon(
            db_path=self.db_path,
            allow_simulation=True,
            timeout_sec=5.0,
            sweep_interval_sec=300.0,
        )

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
                    assigned_role TEXT DEFAULT 'boundary-enforcer',
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

    def test_concurrency_lock_enforces_single_active_agent(self):
        """Requirement 1: Enforce strict 1-active-LLM-agent limit to protect local VRAM."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            # Insert one active task holding the concurrency lock
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-active-lock', 'scope-test', 'task', '[ ACTIVE_ENFORCER ]', 'In progress', 'boundary-enforcer', ?, ?)
            """, (now, now))
            # Insert a second pending task
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-pending-02', 'scope-test', 'task', '[ NEW_PAYLOAD ]', 'Waiting in queue', 'boundary-enforcer', ?, ?)
            """, (now, now))
            conn.commit()

        # 1. Verify lock check detects active agent
        with self.daemon.get_connection() as conn:
            lock_holder = self.daemon.check_concurrency_lock(conn)
            self.assertIsNotNone(lock_holder)
            self.assertIn("job-active-lock", lock_holder)
            self.assertIn("[ ACTIVE_ENFORCER ]", lock_holder)

        # 2. Verify poll_and_lock_next_task refuses to pull the pending task
        locked_task = self.daemon.poll_and_lock_next_task()
        self.assertIsNone(locked_task, "Concurrency lock must prevent pulling new tasks while one is ACTIVE")

        # 3. Simulate completion of the active task
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("UPDATE jobs SET state = '[ DONE ]' WHERE job_id = 'job-active-lock'")
            conn.commit()

        # 4. Verify concurrency lock is released and second task is acquired
        new_locked_task = self.daemon.poll_and_lock_next_task()
        self.assertIsNotNone(new_locked_task)
        self.assertEqual(new_locked_task["job_id"], "job-pending-02")
        self.assertEqual(new_locked_task["state"], "[ ACTIVE_ENFORCER ]")

    def test_atomic_transition_locks_row(self):
        """Requirement 2: Atomic transition with SQLite BEGIN IMMEDIATE locks rows instantly."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-atomic-01', 'scope-test', 'task', '[ NEW_PAYLOAD ]', 'Test atomic lock', 'boundary-enforcer', ?, ?)
            """, (now, now))
            conn.commit()

        locked = self.daemon.poll_and_lock_next_task()
        self.assertIsNotNone(locked)
        self.assertEqual(locked["job_id"], "job-atomic-01")
        self.assertEqual(locked["state"], "[ ACTIVE_ENFORCER ]")
        self.assertEqual(locked["previous_state"], "[ NEW_PAYLOAD ]")

        # Confirm state in database is [ ACTIVE_ENFORCER ]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-atomic-01'").fetchone()
            self.assertEqual(row["state"], "[ ACTIVE_ENFORCER ]")
            self.assertEqual(row["assigned_role"], "boundary-enforcer")

    def test_ingestion_and_extraction_pipeline(self):
        """Requirement 3 (Ingestion): [ NEW_PAYLOAD ] -> boundary-enforcer -> [ PAYLOAD_CLEAN ] -> structural-extractor -> [ SYNTHESIS_PENDING ]."""
        now = datetime.now(timezone.utc).isoformat()
        test_payload = json.dumps({"client": "Keystone Precision", "text": "Reconciliation batch 101"})
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-ingest-01', 'keystone', 'batch', '[ NEW_PAYLOAD ]', ?, 'boundary-enforcer', ?, ?)
            """, (test_payload, now, now))
            conn.commit()

        # Step 1: Lock to [ ACTIVE_ENFORCER ] and run boundary-enforcer
        step1 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step1)
        self.assertEqual(step1["job_id"], "job-ingest-01")
        self.assertTrue(step1["success"])

        # Check DB: state must now be [ PAYLOAD_CLEAN ] with assigned_role = 'structural-extractor'
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-ingest-01'").fetchone()
            self.assertEqual(row["state"], "[ PAYLOAD_CLEAN ]")
            self.assertEqual(row["assigned_role"], "structural-extractor")

        # Step 2: Lock to [ ACTIVE_EXTRACTOR ] and run structural-extractor
        step2 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step2)
        self.assertTrue(step2["success"])

        # Check DB: state must now be [ SYNTHESIS_PENDING ] with assigned_role = 'logic-synthesizer'
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-ingest-01'").fetchone()
            self.assertEqual(row["state"], "[ SYNTHESIS_PENDING ]")
            self.assertEqual(row["assigned_role"], "logic-synthesizer")

    def test_dynamic_branching_to_code_path(self):
        """Requirement 3 (Dynamic Branching): Synthesizer outputs [ NEEDS_CODE ] for algorithmic tasks."""
        now = datetime.now(timezone.utc).isoformat()
        code_payload = json.dumps({"task": "Write and execute a Python script to calculate batch variance"})
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-branch-code', 'scope-test', 'code_task', '[ SYNTHESIS_PENDING ]', ?, 'logic-synthesizer', ?, ?)
            """, (code_payload, now, now))
            conn.commit()

        step = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step)
        self.assertTrue(step["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-branch-code'").fetchone()
            self.assertEqual(row["state"], "[ NEEDS_CODE ]")
            self.assertEqual(row["assigned_role"], "systems-engineer")

    def test_dynamic_branching_to_content_path(self):
        """Requirement 3 (Dynamic Branching): Synthesizer outputs [ NEEDS_CONTENT ] for documentation tasks."""
        now = datetime.now(timezone.utc).isoformat()
        content_payload = json.dumps({"task": "Draft a publication report and executive summary for client"})
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-branch-content', 'scope-test', 'content_task', '[ SYNTHESIS_PENDING ]', ?, 'logic-synthesizer', ?, ?)
            """, (content_payload, now, now))
            conn.commit()

        step = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step)
        self.assertTrue(step["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-branch-content'").fetchone()
            self.assertEqual(row["state"], "[ NEEDS_CONTENT ]")
            self.assertEqual(row["assigned_role"], "content-drafter")

    def test_sandbox_path_full_success(self):
        """Requirement 3 (Sandbox Path): [ NEEDS_CODE ] -> systems-engineer -> [ BLUEPRINT_READY ] -> code-fabricator -> [ DONE ]."""
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"task": "Implement system check utility in Python"})
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-sandbox-success', 'scope-test', 'code_task', '[ NEEDS_CODE ]', ?, 'systems-engineer', ?, ?)
            """, (payload, now, now))
            conn.commit()

        # Step 1: systems-engineer designs blueprint -> [ BLUEPRINT_READY ]
        step1 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step1)
        self.assertTrue(step1["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-sandbox-success'").fetchone()
            self.assertEqual(row["state"], "[ BLUEPRINT_READY ]")
            self.assertEqual(row["assigned_role"], "code-fabricator")

        # Step 2: code-fabricator generates code and runs in ephemeral sandbox -> [ DONE ]
        step2 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step2)
        self.assertTrue(step2["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, model_output FROM jobs WHERE job_id = 'job-sandbox-success'").fetchone()
            self.assertEqual(row["state"], "[ DONE ]")
            self.assertIn("Ephemeral Sandbox Verified", row["model_output"])

    def test_sandbox_path_crash_and_resilience_ejection(self):
        """Requirement 3 (Sandbox Path): Traceback routes to resilience-warden; 3 strikes escalate to [ NEEDS_REVIEW ]."""
        now = datetime.now(timezone.utc).isoformat()
        fatal_payload = json.dumps({"task": "Write and execute a Python script that divides 1 by 0"})
        with sqlite3.connect(str(self.db_path)) as conn:
            # Seed job in [ BLUEPRINT_READY ] with retry_count = 2 (strike 2)
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES ('job-sandbox-fatal', 'scope-test', 'code_task', '[ BLUEPRINT_READY ]', ?, 'code-fabricator', 2, ?, ?)
            """, (fatal_payload, now, now))
            conn.commit()

        # Execution triggers fatal division -> 3rd strike -> hard ejection to [ NEEDS_REVIEW ]
        step = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, retry_count, model_output FROM jobs WHERE job_id = 'job-sandbox-fatal'").fetchone()
            self.assertEqual(row["state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(row["retry_count"], 3)
            self.assertIn("HARD EJECTION", row["model_output"])

        # Confirm telemetry logged
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            telem = conn.execute("SELECT event_type FROM telemetry_log WHERE job_id = 'job-sandbox-fatal' ORDER BY created_at DESC LIMIT 1").fetchone()
            self.assertEqual(telem["event_type"], "HARD_EJECTION_3_STRIKES")

    def test_content_path_full_execution(self):
        """Requirement 3 (Content Path): [ NEEDS_CONTENT ] -> content-drafter -> [ DRAFT_READY ] -> boundary-enforcer -> [ DRAFT_VERIFIED ] -> execution-dispatcher -> [ DONE ]."""
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"task": "Draft customer outreach document for Apex Thermal"})
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-content-flow', 'apex-thermal', 'content_task', '[ NEEDS_CONTENT ]', ?, 'content-drafter', ?, ?)
            """, (payload, now, now))
            conn.commit()

        # Step 1: content-drafter generates draft -> [ DRAFT_READY ]
        step1 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step1)
        self.assertTrue(step1["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-content-flow'").fetchone()
            self.assertEqual(row["state"], "[ DRAFT_READY ]")
            self.assertEqual(row["assigned_role"], "boundary-enforcer")

        # Step 2: boundary-enforcer verifies draft -> [ DRAFT_VERIFIED ]
        step2 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step2)
        self.assertTrue(step2["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-content-flow'").fetchone()
            self.assertEqual(row["state"], "[ DRAFT_VERIFIED ]")
            self.assertEqual(row["assigned_role"], "execution-dispatcher")

        # Step 3: execution-dispatcher finalizes deliverable -> [ DONE ]
        step3 = self.daemon.step_state_machine_once()
        self.assertIsNotNone(step3)
        self.assertTrue(step3["success"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state FROM jobs WHERE job_id = 'job-content-flow'").fetchone()
            self.assertEqual(row["state"], "[ DONE ]")

    def test_resilient_sweeper_soft_reset_and_ejection(self):
        """Requirement 4: trend-monitor finds tasks stalled >60s, routes to resilience-warden; 3rd reset escalates to [ NEEDS_REVIEW ]."""
        now_dt = datetime.now(timezone.utc)
        # 120 seconds ago (stalled > 60s)
        stalled_time = (now_dt - timedelta(seconds=120)).isoformat()

        # Seed 1: Task stalled in [ ACTIVE_ENFORCER ] with retry_count = 0 (attempt 1)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES ('job-stall-reset', 'scope-test', 'task', '[ ACTIVE_ENFORCER ]', 'Stalled job payload', 'boundary-enforcer', 0, ?, ?)
            """, (stalled_time, stalled_time))
            # Seed 2: Task stalled in [ ACTIVE_FABRICATOR ] with retry_count = 2 (attempt 3)
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES ('job-stall-eject', 'scope-test', 'task', '[ ACTIVE_FABRICATOR ]', 'Crash loop payload', 'code-fabricator', 2, ?, ?)
            """, (stalled_time, stalled_time))
            conn.commit()

        # Run sweeper
        swept = self.daemon.sweep_stalled_tasks(stalled_threshold_sec=60.0)
        self.assertEqual(len(swept), 2)

        # 1. Verify job-stall-reset was soft-reset to [ NEW_PAYLOAD ] with retry_count = 1
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row1 = conn.execute("SELECT state, retry_count FROM jobs WHERE job_id = 'job-stall-reset'").fetchone()
            self.assertEqual(row1["state"], "[ NEW_PAYLOAD ]")
            self.assertEqual(row1["retry_count"], 1)

        # 2. Verify job-stall-eject reached 3 strikes and escalated to [ NEEDS_REVIEW ]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row2 = conn.execute("SELECT state, retry_count, payload FROM jobs WHERE job_id = 'job-stall-eject'").fetchone()
            self.assertEqual(row2["state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(row2["retry_count"], 3)
            self.assertIn("RESILIENT SWEEPER HARD EJECTION", row2["payload"])

    def test_dual_environment_routing_general_vs_sensitive(self):
        """Requirement 1/Plugin: General tasks route to staging_buffer, sensitive to offline-restricted."""
        now = datetime.now(timezone.utc).isoformat()
        gen_payload = json.dumps({"task": "General marketing summary", "is_sensitive": False})
        sens_payload = json.dumps({"task": "Confidential reconciliation payroll", "is_sensitive": True, "classification": "RESTRICTED"})

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES
                ('job-gen-route', 'scope-gen', 'task', '[ ACTIVE_DISPATCHER ]', ?, 'execution-dispatcher', ?, ?),
                ('job-sens-route', 'scope-sens', 'task', '[ ACTIVE_DISPATCHER ]', ?, 'execution-dispatcher', ?, ?)
            """, (gen_payload, now, now, sens_payload, now, now))
            conn.commit()

        # Dispatch general task
        ok_gen = self.daemon.update_to_done("job-gen-route", "General dispatch output", from_state="[ ACTIVE_DISPATCHER ]")
        self.assertTrue(ok_gen)

        # Dispatch sensitive task
        ok_sens = self.daemon.update_to_done("job-sens-route", "Confidential payroll output", from_state="[ ACTIVE_DISPATCHER ]")
        self.assertTrue(ok_sens)

        # Verify staging buffer table for general task
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            gen_buf = conn.execute("SELECT staged_payload, status FROM staging_buffer WHERE job_id = 'job-gen-route'").fetchone()
            self.assertEqual(gen_buf["status"], "STAGED")
            self.assertEqual(gen_buf["staged_payload"], "General dispatch output")

            # Verify sensitive task is masked in staging buffer table
            sens_buf = conn.execute("SELECT staged_payload, status FROM staging_buffer WHERE job_id = 'job-sens-route'").fetchone()
            self.assertEqual(sens_buf["status"], "OFFLINE_RESTRICTED")
            self.assertIn("OFFLINE RESTRICTED CONTENT", sens_buf["staged_payload"])

        # Verify sensitive file exists strictly in restricted directory
        restricted_file = self.db_path.parent / "restricted" / "job-sens-route.json"
        self.assertTrue(restricted_file.exists())
        with open(restricted_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["classification"], "OFFLINE_RESTRICTED")
            self.assertEqual(data["restricted_payload"], "Confidential payroll output")


if __name__ == "__main__":
    unittest.main()
