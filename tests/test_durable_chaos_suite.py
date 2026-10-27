#!/usr/bin/env python3
"""
tests/test_durable_chaos_suite.py
=================================
Automated test suite wrapping test_durable_chaos verification logic
against an isolated temporary ledger database.
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Ensure root in path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from test_durable_chaos import run_chaos_test


class TestDurableChaosSuite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_chaos_lifecycle_tag_team_and_ejection(self):
        """Executes full chaos loop and verifies tag-team swap and 3-strike ejection."""
        passed = run_chaos_test(
            db_path=self.db_path,
            poll_interval=1.0,
            timeout_sec=20.0,
            auto_spawn_daemon=True,
        )
        self.assertTrue(passed, "Chaos test sequence failed to verify tag-team or 3-strike ejection.")


if __name__ == "__main__":
    unittest.main()
