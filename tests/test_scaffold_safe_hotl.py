#!/usr/bin/env python3
"""
tests/test_scaffold_safe_hotl.py
================================
Unit test suite verifying:
1. Predefined HOTL Roster injection (aios-systems-architect, jev-tool-fabricator, qa-telemetry-daemon).
2. Explicit exclusion/purging of legacy trading personas.
3. Single active local LLM model constraint with role prompt-swapping.
4. Constrained iteration loop reaching >= 0.85 confidence and transitioning to '[ DONE ]'.
5. Hard cap ejection after 3 failed attempts, immediately transitioning to '[ NEEDS_REVIEW ]'
   with full operator escalation telemetry.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scaffold_safe_hotl import (
    CONFIDENCE_THRESHOLD,
    MAX_ITERATION_ATTEMPTS,
    SAFE_HOTL_PERSONAS,
    HOTLInferenceEngine,
    HOTLLoopController,
    HOTLRosterManager,
    init_hotl_schema,
)
from job_ledger import VALID_TRANSITIONS, update_job_state


class ScaffoldSafeHOTLTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_hotl_ledger.db"
        init_hotl_schema(self.db_path)
        self.manager = HOTLRosterManager(db_path=self.db_path)
        self.engine = HOTLInferenceEngine(allow_simulation=True)
        self.controller = HOTLLoopController(db_path=self.db_path, engine=self.engine)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_predefined_roster_injection(self):
        """Verifies the three safe personas are injected into both hotl_agent_roster and agent_states."""
        res = self.manager.populate_safe_roster()
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["registered_personas"]), 3)

        expected_ids = {"aios-systems-architect", "jev-tool-fabricator", "qa-telemetry-daemon"}
        self.assertEqual(set(res["registered_personas"]), expected_ids)

        # Check hotl_agent_roster table
        active_roster = self.manager.get_active_roster()
        roster_ids = {p["agent_id"] for p in active_roster}
        self.assertEqual(roster_ids, expected_ids)

        for p in active_roster:
            self.assertEqual(p["confidence_threshold"], CONFIDENCE_THRESHOLD)
            self.assertEqual(p["is_active"], 1)
            self.assertIn("MANDATES", p["persona_prompt"])

        # Check agent_states table
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT agent_id, state, meta FROM agent_states WHERE agent_id IN (?, ?, ?)",
                        tuple(expected_ids))
            states = cur.fetchall()
            self.assertEqual(len(states), 3)
            for row in states:
                self.assertEqual(row["state"], "ACTIVE")
                meta = json.loads(row["meta"])
                self.assertTrue(meta.get("single_model_constrained"))
                self.assertEqual(meta.get("confidence_threshold"), CONFIDENCE_THRESHOLD)
        finally:
            conn.close()

    def test_legacy_trading_persona_purging(self):
        """Verifies that any legacy trading, quant, or market personas are purged/deactivated."""
        # Manually inject legacy trading agents into agent_states
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT INTO agent_states (agent_id, name, role, state, last_heartbeat, capabilities, meta)
                VALUES ('agent-legacy-trader', 'Legacy High-Frequency Trader', 'market_quant_trader', 'ACTIVE', 'now', '[]', '{}')
                """
            )
            conn.execute(
                """
                INSERT INTO agent_states (agent_id, name, role, state, last_heartbeat, capabilities, meta)
                VALUES ('agent-market-maker', 'Market Maker Bot', 'execution_desk', 'ACTIVE', 'now', '[]', '{}')
                """
            )
            conn.commit()
        finally:
            conn.close()

        # Run purge
        purged = self.manager.purge_legacy_trading_personas()
        self.assertIn("agent-legacy-trader", purged)
        self.assertIn("agent-market-maker", purged)

        # Verify state in database is deactivated
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT agent_id, state FROM agent_states WHERE agent_id IN ('agent-legacy-trader', 'agent-market-maker')")
            rows = cur.fetchall()
            for r in rows:
                self.assertEqual(r["state"], "DEACTIVATED_LEGACY_TRADING")
        finally:
            conn.close()

    def test_single_model_role_swapping(self):
        """Verifies role swapping operates via prompt injection while keeping model tag constant."""
        # Query systems architect
        res_arch = self.engine.query_role(
            persona_id="aios-systems-architect",
            user_prompt="Design an asynchronous broker architecture",
        )
        self.assertEqual(res_arch["persona_id"], "aios-systems-architect")
        self.assertEqual(res_arch["model_tag"], self.engine.model_tag)
        self.assertIn("architecture_spec", res_arch["output"])

        # Query tool fabricator
        res_fab = self.engine.query_role(
            persona_id="jev-tool-fabricator",
            user_prompt="Fabricate a Python WAL connection helper",
        )
        self.assertEqual(res_fab["persona_id"], "jev-tool-fabricator")
        self.assertEqual(res_fab["model_tag"], self.engine.model_tag)  # Zero VRAM change
        self.assertIn("artifact", res_fab["output"])

        # Query QA evaluator
        res_qa = self.engine.query_role(
            persona_id="qa-telemetry-daemon",
            user_prompt="Evaluate tool implementation",
            force_qa_confidence=0.91,
        )
        self.assertEqual(res_qa["persona_id"], "qa-telemetry-daemon")
        self.assertEqual(res_qa["model_tag"], self.engine.model_tag)  # Identical model tag
        qa_data = json.loads(res_qa["output"])
        self.assertEqual(qa_data["confidence_score"], 0.91)
        self.assertTrue(qa_data["passed"])

    def test_constrained_iteration_loop_passes(self):
        """Verifies evaluation loop succeeds and transitions to '[ DONE ]' when confidence >= 0.85."""
        job_id = "test-job-passing"
        # Simulate score progression: attempt 1 = 0.72 (< 0.85), attempt 2 = 0.90 (>= 0.85)
        outcome = self.controller.run_task_iteration(
            job_id=job_id,
            task_description="Build non-destructive migration script",
            drafter_id="jev-tool-fabricator",
            simulated_scores=[0.72, 0.90],
        )

        self.assertEqual(outcome["final_state"], "[ DONE ]")
        self.assertEqual(outcome["terminal_status"], "PASSED_THRESHOLD")
        self.assertEqual(outcome["attempts_used"], 2)
        self.assertTrue(outcome["passed"])
        self.assertGreaterEqual(outcome["final_confidence"], 0.85)

        # Verify ledger state in SQLite
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT state, attempt_count, model_output FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["state"], "[ DONE ]")
            self.assertEqual(row["attempt_count"], 2)
            out_json = json.loads(row["model_output"])
            self.assertEqual(out_json["terminal_status"], "PASSED_THRESHOLD")

            # Verify iteration logs
            cur.execute("SELECT count(*) FROM hotl_iteration_logs WHERE job_id = ?", (job_id,))
            count = cur.fetchone()[0]
            self.assertEqual(count, 2)
        finally:
            conn.close()

    def test_hard_cap_ejection_after_three_attempts(self):
        """
        Verifies hard cap of 3 attempts:
        When confidence < 0.85 on attempts 1, 2, and 3, execution immediately halts
        and transitions the task to '[ NEEDS_REVIEW ]' with an escalation packet.
        """
        job_id = "test-job-eject"
        # Simulate failing scores for all 3 attempts
        failing_scores = [0.55, 0.68, 0.79]

        outcome = self.controller.run_task_iteration(
            job_id=job_id,
            task_description="Implement speculative high-frequency trading algorithm",
            drafter_id="aios-systems-architect",
            simulated_scores=failing_scores,
        )

        # 1. State must immediately update to [ NEEDS_REVIEW ]
        self.assertEqual(outcome["final_state"], "[ NEEDS_REVIEW ]")
        self.assertEqual(outcome["terminal_status"], "HARD_CAP_EXCEEDED")
        self.assertEqual(outcome["attempts_used"], 3)
        self.assertFalse(outcome["passed"])
        self.assertLess(outcome["final_confidence"], 0.85)
        self.assertEqual(outcome["final_confidence"], 0.79)

        # 2. Verify ledger state in SQLite
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT state, attempt_count, model_output FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(row["attempt_count"], 3)

            # 3. Verify operator escalation packet in model_output
            packet = json.loads(row["model_output"])
            self.assertEqual(packet["terminal_status"], "HARD_CAP_EXCEEDED")
            self.assertEqual(packet["final_state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(packet["attempts_used"], 3)
            self.assertIn("Human operator intervention required", packet["escalation_notes"])
            self.assertEqual(len(packet["history"]), 3)

            # 4. Verify iteration logs table has exactly 3 records
            cur.execute("SELECT attempt_number, confidence_score, passed FROM hotl_iteration_logs WHERE job_id = ? ORDER BY attempt_number ASC", (job_id,))
            logs = cur.fetchall()
            self.assertEqual(len(logs), 3)
            self.assertEqual(logs[0]["attempt_number"], 1)
            self.assertEqual(logs[0]["passed"], 0)
            self.assertEqual(logs[1]["attempt_number"], 2)
            self.assertEqual(logs[1]["passed"], 0)
            self.assertEqual(logs[2]["attempt_number"], 3)
            self.assertEqual(logs[2]["passed"], 0)
        finally:
            conn.close()

    def test_operator_resolution_accept(self):
        """Verifies that human operator can review and accept a task in [ NEEDS_REVIEW ], transitioning it to [ DONE ]."""
        job_id = "test-job-operator-override"
        failing_scores = [0.60, 0.70, 0.78]

        # 1. Force task to reach [ NEEDS_REVIEW ] via 3 failed attempts
        outcome = self.controller.run_task_iteration(
            job_id=job_id,
            task_description="Build specialized bridge adapter",
            drafter_id="aios-systems-architect",
            simulated_scores=failing_scores,
        )
        self.assertEqual(outcome["final_state"], "[ NEEDS_REVIEW ]")

        # 2. Operator resolves task with ACCEPT
        res = self.controller.operator_resolve_task(
            job_id=job_id,
            decision="ACCEPT",
            operator_id="human-operator",
            notes="Attempt 3: Score 0.78 (< 0.85) Accept",
        )
        self.assertEqual(res["final_state"], "[ DONE ]")
        self.assertEqual(res["terminal_status"], "OPERATOR_ACCEPTED")

        # 3. Verify SQLite persistence and operator review audit trail
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute("SELECT state, model_output FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            self.assertEqual(row["state"], "[ DONE ]")
            output_data = json.loads(row["model_output"])
            op_review = output_data["operator_review"]
            self.assertEqual(op_review["decision"], "ACCEPT")
            self.assertEqual(op_review["operator_id"], "human-operator")
            self.assertEqual(op_review["previous_state"], "[ NEEDS_REVIEW ]")
            self.assertEqual(op_review["target_state"], "[ DONE ]")
            self.assertIn("Attempt 3: Score 0.78 (< 0.85) Accept", op_review["notes"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
