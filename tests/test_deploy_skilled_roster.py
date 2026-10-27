#!/usr/bin/env python3
"""
tests/test_deploy_skilled_roster.py
===================================
Automated unit test suite verifying the domain-agnostic Hermes skilled roster deployment:
1. Agent Profiles: structural-extractor, logic-synthesizer, content-drafter.
2. Legacy Trading Persona Scrubbing.
3. Modular Skills:
   - Regex Data Sanitization
   - Pydantic Schema Enforcement
   - Deterministic Math/Logic Validation
   - Jinja2 Templating & Markdown Formatting
4. AIOS Plugin Integrations:
   - SQLite State Updater ([ INBOX ], [ DONE ], [ NEEDS_REVIEW ])
   - HUD Telemetry Emitter
5. Dual-Environment Routing:
   - General AIOS tasks -> staging_buffer
   - Sensitive / air-gapped tasks -> offline-restricted directory
6. Resource Binding:
   - Loopback port 8080 lock.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deploy_skilled_roster import (
    HermesSkilledRosterDeployer,
    HERMES_SKILLED_ROSTER,
    RegexDataSanitizerSkill,
    PydanticSchemaEnforcerSkill,
    DeterministicMathLogicValidatorSkill,
    Jinja2MarkdownDrafterSkill,
    SQLiteStateUpdaterPlugin,
    HUDTelemetryEmitterPlugin,
    DualEnvironmentRouter,
)


class TestDeploySkilledRoster(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"
        self.deployer = HermesSkilledRosterDeployer(db_path=self.db_path)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_legacy_scrubbing_and_profile_injection(self):
        """Directive 1: Verifies legacy trading personas are purged and Hermes profiles are injected."""
        # Seed database with a legacy trading persona
        now = "2026-10-26T12:00:00Z"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO agent_states (agent_id, name, role, state, last_heartbeat, capabilities, meta)
                VALUES ('legacy-quant-bot', 'Quant Trader Bot', 'trading_desk', 'ACTIVE', ?, '[]', '{}')
            """, (now,))

        # Run scrubbing and deployment
        purged = self.deployer.scrub_legacy_trading_personas()
        self.assertIn("legacy-quant-bot", purged)

        # Verify legacy persona deactivated
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state FROM agent_states WHERE agent_id = 'legacy-quant-bot'").fetchone()
            self.assertEqual(row["state"], "DEACTIVATED_LEGACY_TRADING")

        # Deploy skilled roster
        res = self.deployer.deploy_roster()
        self.assertEqual(len(res["deployed_agents"]), 9)
        expected_9 = (
            "structural-extractor",
            "logic-synthesizer",
            "content-drafter",
            "systems-engineer",
            "code-fabricator",
            "boundary-enforcer",
            "trend-monitor",
            "execution-dispatcher",
            "resilience-warden",
        )
        for agent_id in expected_9:
            self.assertIn(agent_id, res["deployed_agents"])

        # Audit database state
        audit = self.deployer.verify_deployment()
        for agent_id in expected_9:
            self.assertTrue(audit[agent_id]["in_agent_states"])
            self.assertTrue(audit[agent_id]["in_hotl_roster"])
            self.assertIn("8080", audit[agent_id]["endpoint"])

    def test_modular_skills_assignment(self):
        """Directive 2: Verifies assigned skills for each agent operate deterministically."""
        # 1. Extractor Skill A: Regex Data Sanitization
        raw_text = "Employee John Doe (john.doe@enterprise.org, 415-555-2671, SSN 000-12-3456) with token Bearer abcd1234efgh5678ijkl9012"
        clean_text = RegexDataSanitizerSkill.sanitize_text(raw_text)
        self.assertNotIn("john.doe@enterprise.org", clean_text)
        self.assertIn("[REDACTED_EMAIL]", clean_text)
        self.assertNotIn("415-555-2671", clean_text)
        self.assertIn("[REDACTED_PHONE]", clean_text)
        self.assertNotIn("000-12-3456", clean_text)
        self.assertIn("[REDACTED_SSN]", clean_text)
        self.assertIn("[REDACTED_TOKEN]", clean_text)

        # 2. Extractor Skill B: Pydantic Schema Enforcement
        test_data = {"record_id": 101, "name": "Apex Thermal", "score": "0.95"}
        expected_schema = {"record_id": int, "name": str, "score": float}
        valid, validated, errors = PydanticSchemaEnforcerSkill.enforce_schema(test_data, expected_schema)
        self.assertTrue(valid)
        self.assertEqual(validated["score"], 0.95)
        self.assertEqual(len(errors), 0)

        # 3. Synthesizer Skill: Deterministic Math/Logic Validation
        valid_eq, res, err = DeterministicMathLogicValidatorSkill.evaluate_arithmetic_expression("(500 * 2) - 150 / 3")
        self.assertTrue(valid_eq)
        self.assertEqual(res, 950.0)
        self.assertIsNone(err)

        balanced, deb, cred, diff = DeterministicMathLogicValidatorSkill.verify_reconciliation_balance(
            debits=[1500.50, 499.50], credits=[2000.00]
        )
        self.assertTrue(balanced)
        self.assertEqual(diff, 0.0)

        # 4. Drafter Skill: Jinja2 Templating & Markdown Formatting
        rendered = Jinja2MarkdownDrafterSkill.render_template(
            "Agent {{ agent }} processed job {{ job }} successfully.",
            {"agent": "content-drafter", "job": "job-100"}
        )
        self.assertEqual(rendered, "Agent content-drafter processed job job-100 successfully.")

        doc = Jinja2MarkdownDrafterSkill.format_markdown_document(
            title="Synthesis Report",
            summary="Verified multi-agent output.",
            sections={"Metrics": {"Confidence": 0.95}},
            alerts=[("TIP", "Deterministic pipeline active.")],
        )
        self.assertIn("# Synthesis Report", doc)
        self.assertIn("> [!TIP]", doc)

    def test_aios_plugin_integration(self):
        """Directive 3: Verifies SQLite State Updater and HUD Telemetry Emitter plugins."""
        job_id = "test-job-plugin-01"
        now = "2026-10-26T12:00:00Z"
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, payload, created_at, updated_at)
                VALUES (?, 'scope-test', 'task', '[ INBOX ]', 'test payload', ?, ?)
            """, (job_id, now, now))

        # 1. Test SQLite State Updater: Transition [ INBOX ] -> [ DONE ]
        updated = SQLiteStateUpdaterPlugin.update_task_state(
            db_path=self.db_path,
            job_id=job_id,
            new_state="[ DONE ]",
            agent_id="content-drafter",
            model_output="Execution completed by content-drafter",
            from_state="[ INBOX ]",
        )
        self.assertTrue(updated)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state, model_output, attempt_count FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ DONE ]")
            self.assertEqual(row["attempt_count"], 1)

        # 2. Test SQLite State Updater: Transition [ DONE ] -> [ NEEDS_REVIEW ]
        escalated = SQLiteStateUpdaterPlugin.update_task_state(
            db_path=self.db_path,
            job_id=job_id,
            new_state="[ NEEDS_REVIEW ]",
            agent_id="qa-telemetry-daemon",
            model_output="Escalated for human operator review",
        )
        self.assertTrue(escalated)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT state FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            self.assertEqual(row["state"], "[ NEEDS_REVIEW ]")

        # 3. Test HUD Telemetry Emitter
        emitted = HUDTelemetryEmitterPlugin.emit_telemetry_event(
            db_path=self.db_path,
            agent_id="structural-extractor",
            job_id=job_id,
            event_type="SCHEMA_EXTRACTION_SUCCESS",
            retry_count=0,
            payload="Sanitized JSON dataset",
        )
        self.assertTrue(emitted)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            log_row = conn.execute("SELECT * FROM telemetry_log WHERE job_id = ?", (job_id,)).fetchone()
            self.assertIsNotNone(log_row)
            self.assertEqual(log_row["assigned_role"], "structural-extractor")
            self.assertEqual(log_row["event_type"], "SCHEMA_EXTRACTION_SUCCESS")

    def test_dual_environment_routing(self):
        """Directive 4: Verifies general tasks route to staging_buffer and sensitive tasks route to offline-restricted."""
        # 1. General Task Routing
        gen_job_id = "test-gen-job-01"
        gen_context = {"is_sensitive": False, "task": "Standard report compilation"}
        gen_res = DualEnvironmentRouter.route_output(
            db_path=self.db_path,
            job_id=gen_job_id,
            assigned_agent="content-drafter",
            output_data="General documentation output",
            task_context=gen_context,
        )
        self.assertEqual(gen_res["destination"], "staging_buffer")
        self.assertFalse(gen_res["is_sensitive"])
        self.assertTrue(Path(gen_res["file_path"]).exists())

        # Verify SQLite staging_buffer entry
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            staged = conn.execute("SELECT * FROM staging_buffer WHERE job_id = ?", (gen_job_id,)).fetchone()
            self.assertIsNotNone(staged)
            self.assertEqual(staged["status"], "STAGED")
            self.assertEqual(staged["staged_payload"], "General documentation output")

        # 2. Sensitive Task Routing
        sens_job_id = "test-sens-job-02"
        sens_context = {"is_sensitive": True, "classification": "CONFIDENTIAL_PII"}
        sens_res = DualEnvironmentRouter.route_output(
            db_path=self.db_path,
            job_id=sens_job_id,
            assigned_agent="structural-extractor",
            output_data="CONFIDENTIAL CLIENT RECORDS",
            task_context=sens_context,
        )
        self.assertEqual(sens_res["destination"], "offline_restricted")
        self.assertTrue(sens_res["is_sensitive"])
        self.assertTrue(Path(sens_res["file_path"]).exists())
        self.assertIn("restricted", sens_res["file_path"])

        # Verify staging_buffer table masks the sensitive content
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            staged = conn.execute("SELECT * FROM staging_buffer WHERE job_id = ?", (sens_job_id,)).fetchone()
            self.assertIsNotNone(staged)
            self.assertEqual(staged["status"], "OFFLINE_RESTRICTED")
            self.assertIn("[OFFLINE RESTRICTED CONTENT AIR-GAPPED]", staged["staged_payload"])
            self.assertNotIn("CONFIDENTIAL CLIENT RECORDS", staged["staged_payload"])

    def test_resource_binding_to_loopback_8080(self):
        """Directive 5: Verifies all agent inference endpoints are locked to loopback port 8080."""
        self.deployer.deploy_roster()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT agent_id, model_endpoint, model_tag FROM hotl_agent_roster").fetchall()
            for r in rows:
                self.assertIn(":8080", r["model_endpoint"])
                self.assertIn("127.0.0.1", r["model_endpoint"])


if __name__ == "__main__":
    unittest.main()
