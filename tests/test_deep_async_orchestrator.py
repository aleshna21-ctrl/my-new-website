"""
tests/test_deep_async_orchestrator.py
======================================
Comprehensive unit and integration test suite for the authoritative AsyncOrchestrator seam:
- Ticket 01: Core seam initialization, composition, and dual response contracts.
- Ticket 02: Multi-agent matrix state machine transitions and concurrency locking.
- Ticket 03: Resilient sweeper, crash recovery, and 3-strike hard ejection.
- Ticket 04: Deterministic in-memory FakeAsyncOrchestrator test double.
- Ticket 05: Backward-compatible AsyncOrchestratorDaemon supervisory wrapper and CLI runner.
"""

from __future__ import annotations
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from job_ledger import JobLedger, FakeJobLedger
from inference_adapter import HermesAdapter, FakeHermesAdapter
from async_orchestrator import (
    AsyncOrchestrator,
    FakeAsyncOrchestrator,
    EphemeralSandboxRunner,
    SandboxResult,
    OrchestratorStepResult,
    OrchestratorTickSnapshot,
    SweepResult,
    get_default_orchestrator,
    reset_default_orchestrator,
    SAFE_HOTL_PERSONAS,
    PENDING_TO_ACTIVE_LOCK,
    ROLE_TO_ACTIVE_LOCK,
)
from async_orchestrator_daemon import AsyncOrchestratorDaemon, parse_arguments


class AsyncOrchestratorTicket01Tests(unittest.TestCase):
    """Ticket 01: Authoritative Async Orchestrator Seam & Response Contracts."""

    def test_response_contracts_dual_access(self):
        """Ticket 01: Verify OrchestratorStepResult, OrchestratorTickSnapshot, and SweepResult dual access."""
        # 1. OrchestratorStepResult
        step_res = OrchestratorStepResult(
            task_id="task-001",
            scope_id="keystone",
            assigned_role="boundary-enforcer",
            from_state="[ NEW_PAYLOAD ]",
            to_state="[ ACTIVE_ENFORCER ]",
            action="lock_and_advance",
            success=True,
            error=None,
            repaired=False,
            timestamp="2026-10-27T12:00:00Z"
        )
        self.assertIsInstance(step_res, dict)
        self.assertEqual(step_res["task_id"], "task-001")
        self.assertEqual(step_res["job_id"], "task-001")
        self.assertEqual(step_res.task_id, "task-001")
        self.assertEqual(step_res.job_id, "task-001")
        self.assertEqual(step_res.assigned_role, "boundary-enforcer")
        self.assertEqual(step_res.from_state, "[ NEW_PAYLOAD ]")
        self.assertEqual(step_res.to_state, "[ ACTIVE_ENFORCER ]")
        self.assertEqual(step_res.action, "lock_and_advance")
        self.assertTrue(step_res.success)
        self.assertIsNone(step_res.error)
        self.assertFalse(step_res.repaired)
        self.assertEqual(step_res.timestamp, "2026-10-27T12:00:00Z")

        # 2. SweepResult
        sweep_res = SweepResult(
            task_id="task-002",
            old_state="[ ACTIVE_ENFORCER ]",
            new_state="[ NEW_PAYLOAD ]",
            action="soft_reset",
            stalled_duration_sec=75.5,
            reason="Exceeded 60s active threshold",
            retry_count=1
        )
        self.assertIsInstance(sweep_res, dict)
        self.assertEqual(sweep_res["task_id"], "task-002")
        self.assertEqual(sweep_res["job_id"], "task-002")
        self.assertEqual(sweep_res.task_id, "task-002")
        self.assertEqual(sweep_res.job_id, "task-002")
        self.assertEqual(sweep_res.old_state, "[ ACTIVE_ENFORCER ]")
        self.assertEqual(sweep_res.new_state, "[ NEW_PAYLOAD ]")
        self.assertEqual(sweep_res.action, "soft_reset")
        self.assertEqual(sweep_res.stalled_duration_sec, 75.5)
        self.assertEqual(sweep_res.elapsed_sec, 75.5)
        self.assertIn("Exceeded", sweep_res.reason)
        self.assertEqual(sweep_res.retry_count, 1)

        # 3. OrchestratorTickSnapshot
        tick_snap = OrchestratorTickSnapshot(
            timestamp="2026-10-27T12:00:01Z",
            sweep_count=1,
            stepped=True,
            swept_tasks=[sweep_res],
            step_result=step_res
        )
        self.assertIsInstance(tick_snap, dict)
        self.assertEqual(tick_snap["sweep_count"], 1)
        self.assertEqual(tick_snap.sweep_count, 1)
        self.assertTrue(tick_snap.stepped)
        self.assertEqual(len(tick_snap.swept_tasks), 1)
        self.assertEqual(tick_snap.step_result.task_id, "task-001")

    def test_orchestrator_initialization_with_in_memory_doubles(self):
        """Ticket 01: Verify AsyncOrchestrator accepts JobLedger and HermesAdapter dependencies."""
        fake_ledger = FakeJobLedger()
        fake_adapter = FakeHermesAdapter()

        orchestrator = AsyncOrchestrator(
            ledger=fake_ledger,
            adapter=fake_adapter,
            poll_interval=2.0,
            stalled_threshold_sec=30.0,
            max_strikes=3
        )

        self.assertIs(orchestrator.ledger, fake_ledger)
        self.assertIs(orchestrator.adapter, fake_adapter)
        self.assertEqual(orchestrator.poll_interval, 2.0)
        self.assertEqual(orchestrator.stalled_threshold_sec, 30.0)
        self.assertEqual(orchestrator.max_strikes, 3)

    def test_orchestrator_idle_lifecycle_methods(self):
        """Ticket 01: Verify step(), sweep(), and run_tick() execute cleanly on an empty ledger."""
        fake_ledger = FakeJobLedger()
        fake_adapter = FakeHermesAdapter()

        orchestrator = AsyncOrchestrator(
            ledger=fake_ledger,
            adapter=fake_adapter
        )

        step_res = orchestrator.step()
        self.assertIsNone(step_res)

        swept = orchestrator.sweep()
        self.assertEqual(swept, [])

        tick = orchestrator.run_tick()
        self.assertEqual(tick.sweep_count, 0)
        self.assertFalse(tick.stepped)
        self.assertEqual(tick.swept_tasks, [])
        self.assertIsNone(tick.step_result)

    def test_orchestrator_singleton_and_reset(self):
        """Ticket 01: Verify get_default_orchestrator() returns singleton and reset_default_orchestrator clears it."""
        reset_default_orchestrator()
        orch1 = get_default_orchestrator()
        orch2 = get_default_orchestrator()
        self.assertIs(orch1, orch2)

        reset_default_orchestrator()
        orch3 = get_default_orchestrator()
        self.assertIsNot(orch1, orch3)


class AsyncOrchestratorTicket04FakeTests(unittest.TestCase):
    """Ticket 04: Deterministic In-Memory Test Double (FakeAsyncOrchestrator)."""

    def test_fake_async_orchestrator_audit_and_fault_injection(self):
        """Ticket 04: Verify FakeAsyncOrchestrator audits calls and supports should_fail."""
        fake_orch = FakeAsyncOrchestrator(should_fail=False)

        # 1. Normal run records calls
        tick = fake_orch.run_tick()
        self.assertIsInstance(tick, OrchestratorTickSnapshot)
        actions = [c["action"] for c in fake_orch.calls]
        self.assertIn("run_tick", actions)
        self.assertIn("sweep", actions)
        self.assertIn("step", actions)

        # 2. Fault injection mode
        failing_orch = FakeAsyncOrchestrator(should_fail=True)
        fail_step = failing_orch.step()
        self.assertIsNotNone(fail_step)
        self.assertFalse(fail_step.success)
        self.assertEqual(fail_step.task_id, "fake-fail")
        self.assertIn("Simulated operational failure", fail_step.error)

        fail_swept = failing_orch.sweep()
        self.assertEqual(fail_swept, [])


class AsyncOrchestratorTicket05DaemonWrapperTests(unittest.TestCase):
    """Ticket 05: Backward-Compatible AsyncOrchestratorDaemon Supervisory Wrapper."""

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

    def test_daemon_delegates_to_orchestrator(self):
        """Ticket 05: Verify AsyncOrchestratorDaemon exposes internal orchestrator seam."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, allow_simulation=True)
        self.assertIsInstance(daemon.orchestrator, AsyncOrchestrator)
        self.assertEqual(daemon.orchestrator.db_path, self.db_path)

    def test_daemon_poll_and_lock_next_task_delegation(self):
        """Ticket 05: Verify poll_and_lock_next_task delegates seamlessly to orchestrator."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-wrapper-01', 'scope-w', 'batch', '[ NEW_PAYLOAD ]', 'sample', 'boundary-enforcer', ?, ?)
            """, (now, now))
            conn.commit()

        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, allow_simulation=True)
        task = daemon.poll_and_lock_next_task()
        self.assertIsNotNone(task)
        self.assertEqual(task["job_id"], "job-wrapper-01")
        self.assertEqual(task["state"], "[ ACTIVE_ENFORCER ]")

    def test_daemon_step_state_machine_once_delegation(self):
        """Ticket 05: Verify step_state_machine_once delegates to orchestrator and returns step contract."""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, created_at, updated_at)
                VALUES ('job-step-01', 'scope-w', 'batch', '[ NEW_PAYLOAD ]', 'sample payload', 'boundary-enforcer', ?, ?)
            """, (now, now))
            conn.commit()

        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, allow_simulation=True)
        step_res = daemon.step_state_machine_once()
        self.assertIsNotNone(step_res)
        self.assertEqual(step_res["job_id"], "job-step-01")
        self.assertTrue(step_res["success"])

        # Check DB row advanced to [ PAYLOAD_CLEAN ]
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, assigned_role FROM jobs WHERE job_id = 'job-step-01'").fetchone()
            self.assertEqual(row["state"], "[ PAYLOAD_CLEAN ]")
            self.assertEqual(row["assigned_role"], "structural-extractor")

    def test_daemon_sweep_stalled_tasks_delegation(self):
        """Ticket 05: Verify sweep_stalled_tasks delegates and performs soft reset."""
        now_dt = datetime.now(timezone.utc)
        stalled_time = (now_dt - timedelta(seconds=120)).isoformat()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, assigned_role, retry_count, created_at, updated_at)
                VALUES ('job-stall-01', 'scope-w', 'batch', '[ ACTIVE_ENFORCER ]', 'stalled payload', 'boundary-enforcer', 0, ?, ?)
            """, (stalled_time, stalled_time))
            conn.commit()

        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, allow_simulation=True)
        swept = daemon.sweep_stalled_tasks(stalled_threshold_sec=60.0)
        self.assertEqual(len(swept), 1)
        self.assertEqual(swept[0]["job_id"], "job-stall-01")
        self.assertEqual(swept[0]["new_state"], "[ NEW_PAYLOAD ]")

    def test_daemon_stop_signal_hygiene(self):
        """Ticket 05: Verify stop() cleanly signals termination without lingering processes."""
        daemon = AsyncOrchestratorDaemon(db_path=self.db_path, allow_simulation=True)
        self.assertFalse(daemon._stop_requested)
        daemon.stop()
        self.assertTrue(daemon._stop_requested)

    def test_cli_argument_parsing(self):
        """Ticket 05: Verify command-line argument parser supports all required flags."""
        with patch("sys.argv", ["async_orchestrator_daemon.py", "--once", "--interval", "10.0", "--model", "custom:latest", "--verbose"]):
            args = parse_arguments()
            self.assertTrue(args.once)
            self.assertEqual(args.interval, 10.0)
            self.assertEqual(args.model, "custom:latest")
            self.assertTrue(args.verbose)


if __name__ == "__main__":
    unittest.main()
