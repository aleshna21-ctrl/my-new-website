"""Tests for Quarantine Auto-Recovery, in-browser row edit, and invariant re-parsing."""
import os
import shutil
import tempfile
import unittest

import hud_server as hud

SAMPLE_CSV = (
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


class QuarantineRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.temp_dir, "adversarial_fixture.csv")
        with open(self.csv_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_CSV)

        # Patch hud_server paths to use isolated temporary directory
        self._orig_offline = hud.OFFLINE_DIR
        self._orig_get_csv = hud.get_adversarial_csv_path
        hud.get_adversarial_csv_path = lambda: self.csv_path

    def tearDown(self):
        hud.get_adversarial_csv_path = self._orig_get_csv
        hud.OFFLINE_DIR = self._orig_offline
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_quarantine_data_detects_malformed_penny_row(self):
        data = hud.get_quarantine_data()
        metrics = data["metrics"]
        self.assertEqual(metrics["received"], 12)
        self.assertEqual(metrics["accepted"], 10)
        self.assertEqual(metrics["quarantined"], 1)
        self.assertEqual(metrics["duplicates"], 1)
        self.assertTrue(data["invariant"]["passed"])

        # Row 12 must be flagged as quarantined due to negative/sub-penny amount
        row12 = [r for r in data["rows"] if r["row_idx"] == 12][0]
        self.assertEqual(row12["invoice_id"], "INV-4459-QZJZ")
        self.assertEqual(row12["amount"], "-999.995")
        self.assertEqual(row12["status"], "quarantined")
        self.assertTrue(row12["is_malformed"])
        self.assertIn("Negative StrictStr amount", row12["reason"])

    def test_operator_edit_row_and_reparse(self):
        # Operator manually edits row 12 to 999.99
        res = hud.repair_quarantine_row(row_idx=12, amount="999.99")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["quarantined_count"], 0)
        self.assertEqual(res["metrics"]["accepted"], 11)
        self.assertEqual(res["metrics"]["quarantined"], 0)
        self.assertEqual(res["metrics"]["duplicates"], 1)
        self.assertTrue(res["invariant"]["passed"])

        # Verify on disk
        updated = hud.get_quarantine_data()
        row12 = [r for r in updated["rows"] if r["row_idx"] == 12][0]
        self.assertEqual(row12["amount"], "999.99")
        self.assertEqual(row12["status"], "accepted")
        self.assertFalse(row12["is_malformed"])

    def test_auto_recover_single_penny_row(self):
        # Auto-recover strips negative sign and truncates sub-penny fraction
        res = hud.repair_quarantine_row(row_idx=12, auto_recover=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["quarantined_count"], 0)
        row12 = [r for r in res["rows"] if r["row_idx"] == 12][0]
        self.assertEqual(row12["amount"], "999.99")
        self.assertEqual(row12["status"], "accepted")

    def test_auto_recover_all_rows(self):
        # Auto-recovers all malformed amounts and duplicate IDs
        res = hud.repair_quarantine_row(auto_recover_all=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["quarantined_count"], 0)
        self.assertEqual(res["duplicates_count"], 0)
        self.assertEqual(res["metrics"]["accepted"], 12)
        self.assertTrue(res["invariant"]["passed"])

    def test_invalid_amount_is_rejected(self):
        # Reject non-numeric input
        res = hud.repair_quarantine_row(row_idx=12, amount="not_a_number")
        self.assertEqual(res["status"], "error")
        self.assertIn("Invalid StrictStr amount", res["error"])

        # Reject negative amounts
        res = hud.repair_quarantine_row(row_idx=12, amount="-50.00")
        self.assertEqual(res["status"], "error")

    def test_reset_fixture_restores_baseline(self):
        # Modify first
        hud.repair_quarantine_row(row_idx=12, amount="100.00")
        mid = hud.get_quarantine_data()
        self.assertEqual(mid["metrics"]["quarantined"], 0)

        # Reset
        reset_res = hud.reset_quarantine_fixture()
        self.assertEqual(reset_res["status"], "ok")
        restored = hud.get_quarantine_data()
        self.assertEqual(restored["metrics"]["quarantined"], 1)
        row12 = [r for r in restored["rows"] if r["row_idx"] == 12][0]
        self.assertEqual(row12["amount"], "-999.995")


if __name__ == "__main__":
    unittest.main()
