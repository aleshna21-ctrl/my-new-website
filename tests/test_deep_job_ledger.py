"""
tests/test_deep_job_ledger.py
Comprehensive unit tests for Deep Job Ledger Module:
- Encapsulated connection lifecycle & WAL concurrency pragmas
- No process os.chdir side-effects
- Authoritative JobLedger repository seam & LedgerSnapshot contract
- Atomic Metadata Diode outbox persistence
- In-memory FakeJobLedger test double
- Backward-compatible module-level delegation
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import job_ledger


class DeepJobLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test_ledger.db"
        self.outbox_path = self.root / "metadata_outbox.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_and_instantiation_does_not_mutate_working_directory(self):
        """Ticket 01: Ensure job_ledger operations never call os.chdir()."""
        cwd_before = os.getcwd()
        ledger = job_ledger.JobLedger(db_path=self.db_path, outbox_path=self.outbox_path)
        ledger.init_db()
        self.assertEqual(os.getcwd(), cwd_before)

    def test_in_memory_ledger_execution(self):
        """Ticket 01: Support pure :memory: SQLite without touching filesystem."""
        ledger = job_ledger.JobLedger(db_path=":memory:", outbox_path=self.outbox_path)
        ledger.init_db()
        ledger.queue_job("job-mem-01", "scope-mem", "reconciliation")
        job = ledger.get_job("job-mem-01")
        self.assertIsNotNone(job)
        self.assertEqual(job["state"], "queued")
        self.assertEqual(job["job_id"], "job-mem-01")

    def test_concurrency_pragmas_on_file_database(self):
        """Ticket 01: Verify busy_timeout and WAL configuration."""
        ledger = job_ledger.JobLedger(db_path=self.db_path, outbox_path=self.outbox_path)
        ledger.init_db()
        with ledger.connect() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA busy_timeout;")
            timeout_val = cur.fetchone()[0]
            self.assertEqual(timeout_val, 5000)

    def test_authoritative_seam_and_state_transitions(self):
        """Ticket 02: Verify full lifecycle queue -> claim -> validate -> approve -> complete."""
        ledger = job_ledger.JobLedger(db_path=self.db_path, outbox_path=self.outbox_path)
        ledger.init_db()

        # Queue
        ledger.queue_job("job-001", "scope-1", "invoice_check")
        snap1 = ledger.get_snapshot()
        self.assertEqual(snap1.counts["queued"], 1)
        self.assertEqual(snap1["counts"]["queued"], 1)

        # Claim
        claimed = ledger.claim_job()
        self.assertEqual(claimed, "job-001")
        job = ledger.get_job("job-001")
        self.assertEqual(job["state"], "running")

        # Valid transitions
        self.assertTrue(ledger.update_job_state("job-001", "validated"))
        self.assertTrue(ledger.update_job_state("job-001", "approved"))
        self.assertTrue(ledger.update_job_state("job-001", "completed"))

        # Invariant: Terminal state cannot transition to running
        self.assertFalse(ledger.update_job_state("job-001", "running"))

        # Snapshot properties
        snap2 = ledger.get_snapshot()
        self.assertEqual(snap2.counts["completed"], 1)
        self.assertEqual(snap2.completed_count, 1)
        self.assertEqual(snap2.active_count, 0)
        self.assertEqual(snap2.total_count, 1)

    def test_atomic_metadata_diode_persistence(self):
        """Ticket 03: Verify atomic outbox writing on notify state transitions."""
        ledger = job_ledger.JobLedger(db_path=self.db_path, outbox_path=self.outbox_path)
        ledger.init_db()

        ledger.queue_job("job-diode-1", "scope-d", "diode_task")
        ledger.claim_job() # running (not a notify state)
        self.assertFalse(self.outbox_path.exists())

        # validated is a NOTIFY_STATE
        ledger.update_job_state("job-diode-1", "validated")
        self.assertTrue(self.outbox_path.exists())

        # Assert JSON structure and zero temp files
        events = json.loads(self.outbox_path.read_text(encoding="utf-8"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["job_id"], "job-diode-1")
        self.assertEqual(events[0]["to_state"], "validated")
        self.assertTrue(events[0]["requires_review"])

        # No leaked temporary files
        leaked_tmp = list(self.root.glob(".outbox-*.tmp"))
        self.assertEqual(leaked_tmp, [])

    def test_fake_job_ledger_test_substitutability(self):
        """Ticket 04: Verify FakeJobLedger in-memory test double."""
        initial_jobs = [
            {"job_id": "fake-01", "scope_id": "scope-f", "job_type": "fake_type", "state": "queued", "attempt_count": 0}
        ]
        fake = job_ledger.FakeJobLedger(initial_jobs=initial_jobs)

        # Seam queries
        snap = fake.get_snapshot()
        self.assertEqual(snap.counts["queued"], 1)
        self.assertEqual(snap.total_count, 1)

        # Claim & transition
        claimed = fake.claim_job()
        self.assertEqual(claimed, "fake-01")
        self.assertTrue(fake.update_job_state("fake-01", "validated"))

        # Audit calls
        self.assertGreaterEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[-1]["action"], "update_job_state")

        # Failure injection
        failing_fake = job_ledger.FakeJobLedger(should_fail=True)
        with self.assertRaises(RuntimeError):
            failing_fake.claim_job()

    def test_backward_compatible_module_level_delegation(self):
        """Ticket 02: Verify top-level functions delegate to default singleton."""
        # Use an isolated environment override for the default singleton
        os.environ["JOB_LEDGER_DB"] = str(self.db_path)
        os.environ["JOB_LEDGER_OUTBOX"] = str(self.outbox_path)
        job_ledger.reset_default_ledger()

        try:
            job_ledger.init_db()
            job_ledger.queue_job("legacy-job-01", "legacy-scope", "legacy-type")
            claimed = job_ledger.claim_job()
            self.assertEqual(claimed, "legacy-job-01")
            self.assertTrue(job_ledger.update_job_state(claimed, "validated"))
            job = job_ledger.get_job("legacy-job-01")
            self.assertEqual(job["state"], "validated")
        finally:
            os.environ.pop("JOB_LEDGER_DB", None)
            os.environ.pop("JOB_LEDGER_OUTBOX", None)
            job_ledger.reset_default_ledger()


if __name__ == "__main__":
    unittest.main()
