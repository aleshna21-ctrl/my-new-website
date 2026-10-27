"""
tests/test_deep_invoice_quarantine.py
Comprehensive unit tests for Invoice Quarantine Invariant Module:
- Ticket 01: Authoritative Quarantine Seam & StrictStr Invariant Inspection
- Ticket 02: Atomic Fixture Repair, Auto-Recovery & Baseline Reset
- Ticket 03: Deterministic In-Memory Test Double (FakeInvoiceQuarantine)
- Ticket 04: Backward-Compatible Module Delegation & Singleton Wrappers
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

SAMPLE_ADVERSARIAL_CSV = (
    "InvoiceID,Amount ,Date\n"
    "INV-3250-VTFZ,173.51,2026-04-25\n"
    "INV-2772-UOKV,105.78,2026-07-16\n"
    "INV-7401-WQWB,242.75,2026-10-05\n"
    "INV-9783-WNNC,46,2026-02-10\n"
    "INV-2059-IYIG,226.74,2026-03-09\n"
    "INV-5960-WCJS,206.3,2026-05-25\n"
    "INV-8931-WZNB,330.66,2026-06-26\n"
    "INV-3083-MRUI,267.23,2026-04-21\n"
    "INV-2337-OTPK,202.48,2026-01-18\n"
    "INV-7234-GIXD,121.38,2026-09-03\n"
    "INV-2059-IYIG,226.74,2026-03-09\n"
    "INV-4459-QZJZ,-999.995,2026-05-16\n"
)


class InvoiceQuarantineTicket01Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "adversarial_fixture.csv"
        self.csv_path.write_text(SAMPLE_ADVERSARIAL_CSV, encoding="utf-8-sig")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inspect_parses_csv_and_evaluates_zero_loss_invariant(self):
        """Ticket 01: Verify inspection parses CSV and confirms received == accepted + quarantined + duplicates."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        snapshot = quarantine.inspect()

        # Zero-loss invariant check
        self.assertTrue(snapshot.passed)
        self.assertTrue(snapshot["invariant"]["passed"])
        self.assertEqual(snapshot.received_count, 12)
        self.assertEqual(snapshot.accepted_count, 10)
        self.assertEqual(snapshot.quarantined_count, 1)
        self.assertEqual(snapshot.duplicates_count, 1)
        self.assertEqual(
            snapshot.received_count,
            snapshot.accepted_count + snapshot.quarantined_count + snapshot.duplicates_count
        )

    def test_inspect_detects_subpenny_and_negative_strictstr(self):
        """Ticket 01: Verify StrictStr rules flag negative and fractional sub-penny amounts."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        snapshot = quarantine.inspect()

        # Row 12 is INV-4459-QZJZ with amount -999.995 (both negative and sub-penny)
        row12 = [r for r in snapshot.rows if r["row_idx"] == 12][0]
        self.assertEqual(row12["invoice_id"], "INV-4459-QZJZ")
        self.assertEqual(row12["status"], "quarantined")
        self.assertTrue(row12["is_malformed"])
        self.assertIn("Negative StrictStr amount", row12["reason"])

    def test_inspect_detects_duplicates_and_missing_identifiers(self):
        """Ticket 01: Verify duplicate InvoiceIDs are isolated and excluded from accepted."""
        csv_with_missing_and_dup = (
            "InvoiceID,Amount,Date\n"
            "INV-001,100.00,2026-01-01\n"
            "INV-001,100.00,2026-01-02\n"
            ",50.00,2026-01-03\n"
        )
        test_file = self.root / "missing_and_dup.csv"
        test_file.write_text(csv_with_missing_and_dup, encoding="utf-8")

        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=test_file)
        snapshot = quarantine.inspect()

        self.assertEqual(snapshot.received_count, 3)
        self.assertEqual(snapshot.accepted_count, 1)
        self.assertEqual(snapshot.duplicates_count, 1)
        self.assertEqual(snapshot.quarantined_count, 1)
        self.assertTrue(snapshot.passed)

        # Row 2 is duplicate
        row2 = [r for r in snapshot.rows if r["row_idx"] == 2][0]
        self.assertEqual(row2["status"], "duplicate")
        self.assertIn("Duplicate InvoiceID (INV-001)", row2["reason"])

        # Row 3 is missing ID
        row3 = [r for r in snapshot.rows if r["row_idx"] == 3][0]
        self.assertEqual(row3["status"], "quarantined")
        self.assertEqual(row3["invoice_id"], "MISSING")
        self.assertEqual(row3["reason"], "Missing InvoiceID")

    def test_inspection_snapshot_dual_contract_and_json_serializability(self):
        """Ticket 01: Verify QuarantineInspectionSnapshot behaves as dict and has typed properties."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        snapshot = quarantine.inspect()

        # Dictionary access
        self.assertIn("metrics", snapshot)
        self.assertIn("invariant", snapshot)
        self.assertIn("rows", snapshot)
        self.assertEqual(snapshot["fixture"], "adversarial_fixture.csv")

        # Attribute access
        self.assertEqual(snapshot.fixture, "adversarial_fixture.csv")
        self.assertIsInstance(snapshot.metrics, dict)
        self.assertIsInstance(snapshot.invariant, dict)
        self.assertIsInstance(snapshot.rows, list)
        self.assertIsInstance(snapshot.quarantined_samples, list)
        self.assertEqual(len(snapshot.quarantined_samples), 1)

        # JSON serialization
        encoded = json.dumps(snapshot)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["metrics"]["received"], 12)
        self.assertTrue(decoded["invariant"]["passed"])

    def test_inspect_handles_missing_file_gracefully(self):
        """Ticket 01: Missing CSV returns clean zero-state snapshot without throwing."""
        import invoice_quarantine
        non_existent = self.root / "does_not_exist.csv"
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=non_existent)
        snapshot = quarantine.inspect()

        self.assertEqual(snapshot.received_count, 0)
        self.assertEqual(snapshot.accepted_count, 0)
        self.assertEqual(snapshot.quarantined_count, 0)
        self.assertEqual(snapshot.duplicates_count, 0)
        self.assertEqual(snapshot.rows, [])
        self.assertTrue(snapshot.passed)



class InvoiceQuarantineTicket02Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "adversarial_fixture.csv"
        self.sync_path = self.root / "sync" / "adversarial_fixture.csv"
        self.sync_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.write_text(SAMPLE_ADVERSARIAL_CSV, encoding="utf-8-sig")
        self.sync_path.write_text(SAMPLE_ADVERSARIAL_CSV, encoding="utf-8-sig")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manual_row_repair_validates_and_updates_row(self):
        """Ticket 02: Operator manual edit of row 12 amount to 999.99."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(
            csv_path=self.csv_path, sync_paths=[self.sync_path]
        )
        res = quarantine.repair(row_idx=12, amount="999.99")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res.status, "ok")
        self.assertEqual(res["quarantined_count"], 0)
        self.assertEqual(res.quarantined_count, 0)
        self.assertEqual(res["metrics"]["accepted"], 11)
        self.assertTrue(res["invariant"]["passed"])

        # Check updated inspection on primary and synced file
        snap1 = quarantine.inspect()
        row12 = [r for r in snap1.rows if r["row_idx"] == 12][0]
        self.assertEqual(row12["amount"], "999.99")
        self.assertEqual(row12["status"], "accepted")

        # Sync verification
        sync_quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.sync_path)
        snap2 = sync_quarantine.inspect()
        row12_sync = [r for r in snap2.rows if r["row_idx"] == 12][0]
        self.assertEqual(row12_sync["amount"], "999.99")

    def test_manual_row_repair_rejects_invalid_amount(self):
        """Ticket 02: Reject non-numeric or negative amounts with error status."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)

        res1 = quarantine.repair(row_idx=12, amount="not_a_number")
        self.assertEqual(res1["status"], "error")
        self.assertIn("Invalid StrictStr amount", res1["error"])

        res2 = quarantine.repair(row_idx=12, amount="-50.00")
        self.assertEqual(res2["status"], "error")
        self.assertIn("Invalid StrictStr amount", res2["error"])

    def test_auto_recover_single_row(self):
        """Ticket 02: auto_recover=True sanitizes negative sign and truncates sub-penny fraction."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        res = quarantine.repair(row_idx=12, auto_recover=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["quarantined_count"], 0)
        row12 = [r for r in res["rows"] if r["row_idx"] == 12][0]
        self.assertEqual(row12["amount"], "999.99")
        self.assertEqual(row12["status"], "accepted")

    def test_auto_recover_all_rows_deconflicts_duplicates(self):
        """Ticket 02: auto_recover_all=True fixes malformed amounts and appends -REC to duplicates."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        res = quarantine.repair(auto_recover_all=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["quarantined_count"], 0)
        self.assertEqual(res["duplicates_count"], 0)
        self.assertEqual(res["metrics"]["accepted"], 12)
        self.assertTrue(res["invariant"]["passed"])

    def test_reset_restores_baseline_fixture(self):
        """Ticket 02: reset() restores original adversarial fixture."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        quarantine.repair(row_idx=12, amount="100.00")
        mid = quarantine.inspect()
        self.assertEqual(mid.quarantined_count, 0)

        reset_res = quarantine.reset()
        self.assertEqual(reset_res["status"], "ok")
        restored = quarantine.inspect()
        self.assertEqual(restored.quarantined_count, 1)
        row12 = [r for r in restored.rows if r["row_idx"] == 12][0]
        self.assertEqual(row12["amount"], "-999.995")

    def test_atomic_file_replacement_leaves_no_temp_files(self):
        """Ticket 02: Atomic file replacement cleans up temporary files without leaks."""
        import invoice_quarantine
        quarantine = invoice_quarantine.InvoiceQuarantine(csv_path=self.csv_path)
        quarantine.repair(row_idx=12, amount="500.00")
        leaked_tmp = list(self.root.glob(".quarantine-*.tmp"))
        self.assertEqual(leaked_tmp, [])


class InvoiceQuarantineTicket03Tests(unittest.TestCase):
    """Ticket 03: Deterministic In-Memory Test Double (FakeInvoiceQuarantine)."""

    def setUp(self):
        self.sample_rows = [
            {"InvoiceID": "INV-1001", "Amount": "100.50", "Vendor": "Acme", "Status": "Pending"},
            {"InvoiceID": "INV-1002", "Amount": "-45.00", "Vendor": "Beta", "Status": "Pending"},
            {"InvoiceID": "INV-1001", "Amount": "50.00", "Vendor": "Acme", "Status": "Pending"},
        ]

    def test_fake_inspect_seeded_rows_and_audit_trail(self):
        import invoice_quarantine
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=self.sample_rows)
        snap = fake.inspect()

        self.assertEqual(snap.received_count, 3)
        self.assertEqual(snap.accepted_count, 1)
        self.assertEqual(snap.quarantined_count, 1)
        self.assertEqual(snap.duplicates_count, 1)
        self.assertTrue(snap.passed)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["action"], "inspect")

    def test_fake_repair_auto_recover(self):
        import invoice_quarantine
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=self.sample_rows)
        res = fake.repair(row_idx=2, auto_recover=True)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res.quarantined_count, 0)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["action"], "repair")
        self.assertEqual(fake.calls[0]["row_idx"], 2)

    def test_fake_repair_auto_recover_all(self):
        import invoice_quarantine
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=self.sample_rows)
        res = fake.repair(auto_recover_all=True)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res.quarantined_count, 0)
        self.assertEqual(res.duplicates_count, 0)
        self.assertEqual(res.metrics["accepted"], 3)
        self.assertTrue(res.invariant["passed"])

    def test_fake_manual_repair_and_validation(self):
        import invoice_quarantine
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=self.sample_rows)
        bad_res = fake.repair(row_idx=2, amount="abc")
        self.assertEqual(bad_res["status"], "error")

        good_res = fake.repair(row_idx=2, amount="45.00")
        self.assertEqual(good_res["status"], "ok")
        self.assertEqual(good_res.quarantined_count, 0)

    def test_fake_reset_restores_initial_state(self):
        import invoice_quarantine
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=self.sample_rows)
        fake.repair(auto_recover_all=True)
        self.assertEqual(fake.inspect().quarantined_count, 0)

        reset_res = fake.reset()
        self.assertEqual(reset_res["status"], "ok")
        snap = fake.inspect()
        self.assertEqual(snap.quarantined_count, 1)
        self.assertEqual(snap.duplicates_count, 1)
        self.assertEqual(fake.calls[-2]["action"], "reset")

    def test_fake_should_fail_raises_runtime_error(self):
        import invoice_quarantine
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=self.sample_rows, should_fail=True)
        with self.assertRaises(RuntimeError):
            fake.inspect()
        with self.assertRaises(RuntimeError):
            fake.repair(row_idx=2, auto_recover=True)
        with self.assertRaises(RuntimeError):
            fake.reset()


class InvoiceQuarantineTicket04Tests(unittest.TestCase):
    """Ticket 04: Backward-Compatible Module Delegation & Singleton Wrappers."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "adversarial_fixture.csv"
        self.csv_path.write_text(SAMPLE_ADVERSARIAL_CSV, encoding="utf-8-sig")

    def tearDown(self):
        import invoice_quarantine
        invoice_quarantine.reset_default_quarantine()
        self.temp_dir.cleanup()

    def test_default_quarantine_singleton_and_reset(self):
        import invoice_quarantine
        q1 = invoice_quarantine.get_default_quarantine()
        q2 = invoice_quarantine.get_default_quarantine()
        self.assertIs(q1, q2)

        invoice_quarantine.reset_default_quarantine()
        q3 = invoice_quarantine.get_default_quarantine()
        self.assertIsNot(q1, q3)

    def test_top_level_wrappers_delegate_to_singleton(self):
        import invoice_quarantine
        snap = invoice_quarantine.get_quarantine_data(csv_path=self.csv_path)
        self.assertEqual(snap.quarantined_count, 1)
        self.assertEqual(snap["metrics"]["quarantined"], 1)

        rep = invoice_quarantine.repair_quarantine_row(row_idx=12, amount="777.77", csv_path=self.csv_path)
        self.assertEqual(rep.status, "ok")
        self.assertEqual(rep["quarantined_count"], 0)

        res = invoice_quarantine.reset_quarantine_fixture(csv_path=self.csv_path)
        self.assertEqual(res.status, "ok")
        self.assertEqual(res["status"], "ok")

        csv_str = invoice_quarantine.get_adversarial_csv_path()
        self.assertTrue(isinstance(csv_str, str))


class InvoiceQuarantineTicket05Tests(unittest.TestCase):
    """Ticket 05: Server & Route Integration Verification."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.csv_path = self.root / "adversarial_fixture.csv"
        self.csv_path.write_text(SAMPLE_ADVERSARIAL_CSV, encoding="utf-8-sig")

    def tearDown(self):
        import invoice_quarantine
        invoice_quarantine.reset_default_quarantine()
        self.temp_dir.cleanup()

    def test_hud_server_quarantine_delegation(self):
        import hud_server
        orig_get_csv = hud_server.get_adversarial_csv_path
        try:
            hud_server.get_adversarial_csv_path = lambda: str(self.csv_path)

            data = hud_server.get_quarantine_data()
            self.assertEqual(data["metrics"]["received"], 12)
            self.assertEqual(data["metrics"]["quarantined"], 1)
            self.assertTrue(data["invariant"]["passed"])

            rep = hud_server.repair_quarantine_row(row_idx=12, amount="555.55")
            self.assertEqual(rep["status"], "ok")
            self.assertEqual(rep["quarantined_count"], 0)

            reset_res = hud_server.reset_quarantine_fixture()
            self.assertEqual(reset_res["status"], "ok")
            restored = hud_server.get_quarantine_data()
            self.assertEqual(restored["metrics"]["quarantined"], 1)
        finally:
            hud_server.get_adversarial_csv_path = orig_get_csv

    def test_type_safe_router_with_fake_quarantine(self):
        from hud.type_safe_router import TypeSafeRouter, HTTPRequest
        from hud.routes.quarantine_routes import register_quarantine_routes
        import invoice_quarantine

        sample_rows = [
            {"InvoiceID": "INV-1", "Amount": "100.00", "Date": "2026-01-01"},
            {"InvoiceID": "INV-2", "Amount": "-50.00", "Date": "2026-01-02"},
        ]
        fake = invoice_quarantine.FakeInvoiceQuarantine(initial_rows=sample_rows)
        router = TypeSafeRouter()
        register_quarantine_routes(router, fake)

        # GET /api/quarantine
        req_get = HTTPRequest(path="/api/quarantine", method="GET")
        resp_get = router.dispatch(req_get)
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.payload["metrics"]["quarantined"], 1)

        # POST /api/quarantine/repair (valid auto-recover)
        req_repair = HTTPRequest(path="/api/quarantine/repair", method="POST", body={"row_idx": 2, "auto_recover": True})
        resp_repair = router.dispatch(req_repair)
        self.assertEqual(resp_repair.status_code, 200)
        self.assertEqual(resp_repair.payload["quarantined_count"], 0)

        # POST /api/quarantine/repair (invalid amount -> 400)
        req_bad = HTTPRequest(path="/api/quarantine/repair", method="POST", body={"row_idx": 2, "amount": "invalid"})
        resp_bad = router.dispatch(req_bad)
        self.assertEqual(resp_bad.status_code, 400)
        self.assertEqual(resp_bad.payload["status"], "error")

        # POST /api/quarantine/reset
        req_reset = HTTPRequest(path="/api/quarantine/reset", method="POST")
        resp_reset = router.dispatch(req_reset)
        self.assertEqual(resp_reset.status_code, 200)
        self.assertEqual(resp_reset.payload["status"], "ok")

        # Verify audit trail in fake
        actions = [c["action"] for c in fake.calls]
        self.assertEqual(actions, ["inspect", "repair", "repair", "reset"])


if __name__ == "__main__":
    unittest.main()

