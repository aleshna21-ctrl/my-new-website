"""
tests/test_architectural_patches.py
Unit and integration tests for Architectural and Stability Patches:
1. Hermes stability patch: keep_alive=-1 in payload constructor; probe does not block execution payloads.
2. Obsidian AIOS root node generation and live job_ledger.db querying.
3. Assignment node routing to Kanban orchestrator, ledger state, educate, and 3 trigger sources.
"""

import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import hud_server
from inference_adapter import LiveLocalModelAdapter
from hud.obsidian_root_generator import (
    AIOSObsidianGenerator,
    query_ledger_stats,
    generate_aios_obsidian_vault,
)
from hud.os_dashboard import (
    FLOW_EDGES,
    OBSIDIAN_NOTES,
    OBSIDIAN_LINKS,
    compose_frame,
)
from hud_server import os_frame


class TestHermesStabilityPatch(unittest.TestCase):
    def test_live_local_model_adapter_payload_includes_keep_alive(self):
        """Verifies that the API payload constructor includes keep_alive=-1 to lock model in VRAM."""
        adapter = LiveLocalModelAdapter(
            endpoint="http://127.0.0.1:8080/v1/chat/completions",
            model_tag="qwen3:4b",
            keep_alive=-1,
        )
        self.assertEqual(adapter.keep_alive, -1)

        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": '{"test": "ok"}'}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                }).encode("utf-8")

        def fake_open(request, timeout=None):
            captured_requests.append(request)
            return FakeResponse()

        adapter._opener.open = fake_open
        res = adapter.call_local_server("Extract test fact")
        self.assertEqual(res, '{"test": "ok"}')
        self.assertEqual(len(captured_requests), 1)

        sent_payload = json.loads(captured_requests[0].data.decode("utf-8"))
        self.assertIn("keep_alive", sent_payload)
        self.assertEqual(sent_payload["keep_alive"], -1)
        self.assertEqual(sent_payload["model"], "qwen3:4b")

    def test_probe_lock_does_not_block_execution_payloads(self):
        """
        Verifies that PROBE_LOCK does NOT block execution payloads (e.g. gateway task executions).
        Execution payloads must proceed immediately and concurrently even when probe lock is held.
        """
        # Simulate an ongoing synthetic health probe holding PROBE_LOCK
        hud_server.PROBE_LOCK.acquire()
        try:
            self.assertTrue(hud_server.PROBE_LOCK.locked())

            # Execute an execution payload (execute_task_command)
            from hud.gateway import execute_task_command
            start_t = time.perf_counter()
            outcome = execute_task_command("ping", {"idempotency_key": "test-key-probe-unblocked"})
            elapsed = time.perf_counter() - start_t

            # Verify execution payload succeeded with zero lock blockage
            self.assertEqual(outcome.get("status"), "completed")
            self.assertIn("ack", outcome)
            self.assertLess(elapsed, 0.5)  # Should execute virtually instantly
        finally:
            hud_server.PROBE_LOCK.release()
            self.assertFalse(hud_server.PROBE_LOCK.locked())


class TestObsidianRootAndAgentGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name) / "vault"
        self.db_path = Path(self.temp_dir.name) / "job_ledger.db"

        # Create mock job_ledger.db
        conn = sqlite3.connect(str(self.db_path))
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
        conn.execute("INSERT INTO jobs VALUES ('job-1', 'scope-a', 'reconciliation', 'completed', 1, '2026-10-26T00:00:00Z', '2026-10-26T01:00:00Z')")
        conn.execute("INSERT INTO jobs VALUES ('job-2', 'scope-b', 'risk_extraction', 'completed', 1, '2026-10-26T00:00:00Z', '2026-10-26T02:00:00Z')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ledger_querying(self):
        stats = query_ledger_stats(self.db_path)
        self.assertEqual(stats["total_jobs"], 2)
        self.assertEqual(stats["completed"], 2)
        self.assertIn("reconciliation", stats["by_type"])
        self.assertIn("risk_extraction", stats["by_type"])

    def test_obsidian_root_and_agents_generation(self):
        generator = AIOSObsidianGenerator(self.vault_path)
        with patch("hud.obsidian_root_generator.get_ledger_db_path", return_value=self.db_path):
            res = generator.generate_all()

        self.assertEqual(res["status"], "success")

        # Verify 00_AIOS_ROOT.md
        root_file = self.vault_path / "00_AIOS_ROOT.md"
        self.assertTrue(root_file.exists())
        root_text = root_file.read_text(encoding="utf-8")
        self.assertIn("title: \"AIOS Root Node // Ring-0 Operating System Core\"", root_text)
        self.assertIn("node_id: \"aios-root\"", root_text)
        self.assertIn("[[agents/JEV-PowerShell-Patcher]]", root_text)
        self.assertIn("[[agents/cron]]", root_text)
        self.assertIn("[[agents/maintain-daemon]]", root_text)
        self.assertIn("[[agents/meta-diode-relay]]", root_text)
        self.assertIn("[[agents/hermes-sub-agents]]", root_text)
        self.assertIn("[[03_AIOS_ASSIGNMENTS]]", root_text)

        # Verify all agent files exist and wire directly to root
        agents_dir = self.vault_path / "agents"
        expected_agents = [
            "JEV-PowerShell-Patcher.md",
            "cron.md",
            "maintain-daemon.md",
            "meta-diode-relay.md",
            "hermes-sub-agents.md",
        ]
        for ag in expected_agents:
            ag_file = agents_dir / ag
            self.assertTrue(ag_file.exists(), f"Agent file {ag} should exist")
            ag_text = ag_file.read_text(encoding="utf-8")
            self.assertIn("[[00_AIOS_ROOT]]", ag_text, f"{ag} must link directly to [[00_AIOS_ROOT]]")
            self.assertIn("[[03_AIOS_ASSIGNMENTS]]", ag_text)


class TestAssignmentsNodeRouting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name) / "vault"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_assignments_markdown_links_and_three_trigger_sources(self):
        generator = AIOSObsidianGenerator(self.vault_path)
        res = generator.generate_all()
        self.assertEqual(res["status"], "success")

        assignments_file = self.vault_path / "03_AIOS_ASSIGNMENTS.md"
        self.assertTrue(assignments_file.exists())
        text = assignments_file.read_text(encoding="utf-8")

        # 1. Links directly to Kanban board orchestrator
        self.assertIn("Kanban Board Orchestrator", text)
        self.assertIn("data/os_board.json", text)

        # 2. Links directly to SQLite ledger state
        self.assertIn("SQLite Ledger State", text)
        self.assertIn("data/job_ledger.db", text)

        # 3. Links directly to specific educate
        self.assertIn("[[modules/knowledge-memory.md]]", text)
        self.assertIn("[[modules/execution.md]]", text)
        self.assertIn("[[modules/source-governance.md]]", text)
        self.assertIn("[[modules/hermes-delegation.md]]", text)

        # 4. Explicitly maps incoming edges to three trigger sources
        self.assertIn("aios-directed", text.lower())
        self.assertIn("operator-directed", text.lower())
        self.assertIn("event-driven", text.lower())

    def test_os_dashboard_graph_includes_assignments_node_and_triggers(self):
        """Verifies that os_dashboard graph structures include the assignments node and incoming edges."""
        # Check FLOW_EDGES
        edge_targets = [dst for _, dst, _ in FLOW_EDGES]
        self.assertIn("assignments", edge_targets)

        # Check incoming edges to assignments
        incoming_to_assign = [label for _, dst, label in FLOW_EDGES if dst == "assignments"]
        self.assertTrue(any("operator-directed" in lbl for lbl in incoming_to_assign))
        self.assertTrue(any("aios-directed" in lbl for lbl in incoming_to_assign))
        self.assertTrue(any("event-driven" in lbl for lbl in incoming_to_assign))

        # Check OBSIDIAN_NOTES
        note_ids = {n["id"] for n in OBSIDIAN_NOTES}
        self.assertIn("aios-root", note_ids)
        self.assertIn("assignments", note_ids)
        core_note = next(n for n in OBSIDIAN_NOTES if n["id"] == "core.md")
        self.assertEqual(core_note["ring"], 1, "core.md must be demoted to Ring 1 child of AIOS")

        # Check OBSIDIAN_LINKS
        link_pairs = {(src, dst) for src, dst, _, _, _ in OBSIDIAN_LINKS}
        self.assertIn(("aios-root", "assignments"), link_pairs)
        self.assertIn(("aios-root", "core.md"), link_pairs)
        self.assertNotIn(("assignments", "core.md"), link_pairs, "Isolated link from assignments to core.md must be removed")
        self.assertIn(("assignments", "hermes-delegation"), link_pairs)
        self.assertIn(("assignments", "execution"), link_pairs)

        # Check os_frame nodes
        frame = os_frame()
        self.assertIn("assignments", frame["nodes"])
        self.assertIn("triggers", frame["nodes"]["assignments"])
        self.assertEqual(frame["nodes"]["assignments"]["triggers"], ["aios-directed", "operator-directed", "event-driven"])


class TestAIOSGTMOutreachMigration(unittest.TestCase):
    """
    Rigorously tests:
    1. AIOS GTM Governance: 04_AIOS_GTM_OUTREACH.md is a Ring 1 child of [[00_AIOS_ROOT]].
    2. Dedicated Client Nodes: Markdown files generated for all prospects (e.g., Cambridge Specialty Company, Apex Thermal Solutions).
    3. Contextual Mapping: Extracted data includes vertical, problem context, ERP systems, and financial leakage.
    4. Execution Routing: Direct links to 04_AIOS_GTM_OUTREACH and outbound edge to [[modules/hermes-delegation.md|Hermes Delegation]].
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name) / "vault"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_gtm_governance_node_and_root_linkage(self):
        from migrate_gtm_research import execute_gtm_migration

        res = execute_gtm_migration(self.vault_path)
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["prospects_count"], 9)

        # 1. AIOS GTM Governance Node
        gtm_node = self.vault_path / "04_AIOS_GTM_OUTREACH.md"
        self.assertTrue(gtm_node.exists(), "04_AIOS_GTM_OUTREACH.md must exist")
        gtm_text = gtm_node.read_text(encoding="utf-8")
        self.assertIn("parent: \"[[00_AIOS_ROOT]]\"", gtm_text)
        self.assertIn("ring: 1", gtm_text)
        self.assertIn("[[modules/hermes-delegation.md|Hermes Delegation]]", gtm_text)

        # Check AIOS Root link
        root_node = self.vault_path / "00_AIOS_ROOT.md"
        if root_node.exists():
            root_text = root_node.read_text(encoding="utf-8")
            self.assertIn("[[04_AIOS_GTM_OUTREACH", root_text)

    def test_dedicated_client_nodes_contextual_mapping_and_routing(self):
        from migrate_gtm_research import execute_gtm_migration

        res = execute_gtm_migration(self.vault_path)
        gtm_dir = self.vault_path / "gtm"
        self.assertTrue(gtm_dir.exists())

        # Test Cambridge Specialty Company
        cambridge_file = gtm_dir / "Cambridge-Specialty-Company.md"
        self.assertTrue(cambridge_file.exists(), "Cambridge Specialty Company node must exist")
        c_text = cambridge_file.read_text(encoding="utf-8")
        self.assertIn("parent: \"[[04_AIOS_GTM_OUTREACH]]\"", c_text)
        self.assertIn("Precision Manufacturing / B2B", c_text)
        self.assertIn("JobBOSS", c_text)
        self.assertIn("QuickBooks", c_text)
        self.assertIn("Manual data reconciliation", c_text)
        self.assertIn("Month-end close labor drag", c_text)
        self.assertIn("[[modules/hermes-delegation.md|Hermes Delegation]]", c_text)
        self.assertIn("Level 4", c_text)

        # Test Apex Thermal Solutions
        apex_file = gtm_dir / "Apex-Thermal-Solutions.md"
        self.assertTrue(apex_file.exists(), "Apex Thermal Solutions node must exist")
        a_text = apex_file.read_text(encoding="utf-8")
        self.assertIn("parent: \"[[04_AIOS_GTM_OUTREACH]]\"", a_text)
        self.assertIn("Commercial Refrigeration/HVAC", a_text)
        self.assertIn("ServiceTitan", a_text)
        self.assertIn("QuickBooks Enterprise", a_text)
        self.assertIn("vendor core credits", a_text)
        self.assertIn("[[modules/hermes-delegation.md|Hermes Delegation]]", a_text)

    def test_dashboard_visualizer_gtm_wiring(self):
        # Verify OBSIDIAN_NOTES includes gtm-outreach
        gtm_notes = [n for n in OBSIDIAN_NOTES if n["id"] == "gtm-outreach"]
        self.assertEqual(len(gtm_notes), 1)
        self.assertEqual(gtm_notes[0]["ring"], 1)

        # Verify OBSIDIAN_LINKS
        link_pairs = {(src, dst) for src, dst, _, _, _ in OBSIDIAN_LINKS}
        self.assertIn(("aios-root", "gtm-outreach"), link_pairs)
        self.assertIn(("gtm-outreach", "hermes-delegation"), link_pairs)


if __name__ == "__main__":
    unittest.main()
