"""
tests/test_shared_short_term_memory.py
======================================
Comprehensive test suite for AIOS Multi-Agent Shared Short-Term Memory (SSTM) Protocol
and Obsidian Vault Synchronization.
"""

import os
import sys
import time
import json
import shutil
import unittest
import urllib.request
import threading
from pathlib import Path

# Add root directory to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hud.shared_memory import (
    SharedMemoryStore,
    TaskRecord,
    AgentState,
    BlackboardEntry,
    get_shared_memory_store,
)
from hud_server import HUDHTTPServer, HUDRequestHandler


class TestSharedShortTermMemoryStore(unittest.TestCase):
    """Unit tests for thread-safe SharedMemoryStore logic and TTL management."""

    def setUp(self):
        self.temp_vault = REPO_ROOT / "scratch" / "test_vault"
        self.temp_vault.mkdir(parents=True, exist_ok=True)
        self.store = SharedMemoryStore()

    def tearDown(self):
        if self.temp_vault.exists():
            shutil.rmtree(self.temp_vault, ignore_errors=True)

    def test_canonical_agents_initialization(self):
        agents = self.store.get_agents()
        agent_ids = {a["agent_id"] for a in agents}
        self.assertIn("agent-supervisor", agent_ids)
        self.assertIn("agent-hermes-gateway", agent_ids)
        self.assertIn("agent-diagnostic-probe", agent_ids)
        self.assertIn("agent-invoice-ingestion", agent_ids)
        self.assertIn("agent-sow-worker", agent_ids)
        self.assertIn("agent-quarantine-guard", agent_ids)

    def test_record_task_completion_and_epoch_increment(self):
        initial_summary = self.store.get_state_summary()
        initial_epoch = initial_summary["epoch"]

        rec = self.store.record_task_completion(
            agent_id="agent-diagnostic-probe",
            task_id="test-probe-task-001",
            task_type="telemetry_audit",
            status="completed",
            input_summary={"target": "127.0.0.1:8080"},
            output_summary={"latency_ms": 1.45, "status": "optimal"},
            artifacts=["scratch/test_probe.json"],
            duration_ms=1.45,
            sync_vault_now=False
        )

        self.assertEqual(rec.task_id, "test-probe-task-001")
        self.assertEqual(rec.agent_id, "agent-diagnostic-probe")
        self.assertGreater(rec.epoch, initial_epoch)

        tasks = self.store.get_completed_tasks(limit=10)
        self.assertTrue(any(t["task_id"] == "test-probe-task-001" for t in tasks))

    def test_blackboard_set_get_and_ttl(self):
        # 1. Normal set/get
        entry = self.store.set_blackboard_key(
            key="test_pipeline_flag",
            value="ACTIVE_PROCESSING",
            writer_agent_id="agent-supervisor"
        )
        self.assertEqual(entry.key, "test_pipeline_flag")
        self.assertEqual(self.store.get_blackboard_key("test_pipeline_flag"), "ACTIVE_PROCESSING")

        v1 = entry.version
        entry_v2 = self.store.set_blackboard_key(
            key="test_pipeline_flag",
            value="STAGE_2_EXTRACTION",
            writer_agent_id="agent-sow-worker"
        )
        self.assertEqual(entry_v2.version, v1 + 1)
        self.assertEqual(self.store.get_blackboard_key("test_pipeline_flag"), "STAGE_2_EXTRACTION")

        # 3. TTL expiration test
        self.store.set_blackboard_key(
            key="ephemeral_nonce",
            value="temp-12345",
            writer_agent_id="agent-hermes-gateway",
            ttl_seconds=0.05
        )
        self.assertEqual(self.store.get_blackboard_key("ephemeral_nonce"), "temp-12345")
        time.sleep(0.08)
        self.assertIsNone(self.store.get_blackboard_key("ephemeral_nonce"))

    def test_agent_heartbeat_and_operational_state(self):
        ag = self.store.update_agent_heartbeat(
            agent_id="agent-invoice-ingestion",
            role="diode_ingestion",
            operational_state="busy",
            current_task_id="task-inv-999"
        )
        self.assertEqual(ag.operational_state, "busy")
        self.assertEqual(ag.current_task_id, "task-inv-999")

        # After task completion, state reverts to idle
        self.store.record_task_completion(
            agent_id="agent-invoice-ingestion",
            task_id="task-inv-999",
            task_type="csv_cleanse",
            status="completed",
            sync_vault_now=False
        )
        agents = {a["agent_id"]: a for a in self.store.get_agents()}
        self.assertEqual(agents["agent-invoice-ingestion"]["operational_state"], "idle")
        self.assertIsNone(agents["agent-invoice-ingestion"]["current_task_id"])

    def test_obsidian_vault_sync_markdown_files(self):
        sync_res = self.store.sync_to_obsidian_vault(target_dirs=[self.temp_vault])
        self.assertEqual(sync_res["status"], "SYNCHRONIZED")
        self.assertGreaterEqual(sync_res["written_files_count"], 3)

        f_state = self.temp_vault / "00_AIOS_OPERATIONAL_STATE.md"
        f_tasks = self.temp_vault / "01_AIOS_COMPLETED_TASKS_LOG.md"
        f_bb = self.temp_vault / "02_AIOS_CROSS_AGENT_BLACKBOARD.md"

        self.assertTrue(f_state.exists())
        self.assertTrue(f_tasks.exists())
        self.assertTrue(f_bb.exists())

        state_content = f_state.read_text(encoding="utf-8")
        self.assertIn("---", state_content)
        self.assertIn("type: \"aios-operational-state\"", state_content)
        self.assertIn("## 1. Sub-Agent Operational Roster", state_content)
        self.assertIn("## 2. Shared Working Memory Blackboard", state_content)
        self.assertIn("[[core]]", state_content)
        self.assertIn("[[modules/knowledge-memory]]", state_content)


class TestSharedShortTermMemoryHTTPEndpoints(unittest.TestCase):
    """Integration tests verifying HTTP endpoints for cross-agent memory."""

    @classmethod
    def setUpClass(cls):
        cls.server = HUDHTTPServer(("127.0.0.1", 0), HUDRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path: str):
        req = urllib.request.Request(f"{self.base_url}{path}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_http_memory_state_endpoint(self):
        data = self._get("/api/memory/state")
        self.assertIn("epoch", data)
        self.assertIn("agents", data)
        self.assertIn("blackboard", data)
        self.assertIn("vault_sync_status", data)
        self.assertGreaterEqual(len(data["agents"]), 6)

    def test_http_memory_task_complete_and_tasks_list(self):
        t_id = f"http-task-{int(time.time()*1000)}"
        post_res = self._post("/api/memory/task/complete", {
            "agent_id": "agent-hermes-gateway",
            "task_id": t_id,
            "task_type": "model_inference",
            "status": "completed",
            "input_summary": {"prompt": "Health probe ping"},
            "output_summary": {"model": "qwen3:4b", "status": "ok"},
            "duration_ms": 42.5
        })
        self.assertEqual(post_res["status"], "recorded")
        self.assertEqual(post_res["task"]["task_id"], t_id)

        tasks_list = self._get("/api/memory/tasks")
        self.assertTrue(any(t["task_id"] == t_id for t in tasks_list["tasks"]))

    def test_http_blackboard_set_and_get(self):
        set_res = self._post("/api/memory/blackboard", {
            "key": "test_http_key",
            "value": {"status": "all_subagents_nominal"},
            "writer_agent_id": "agent-supervisor"
        })
        self.assertEqual(set_res["status"], "set")
        self.assertEqual(set_res["entry"]["key"], "test_http_key")

        # Get specific key
        get_res = self._get("/api/memory/blackboard?key=test_http_key")
        self.assertEqual(get_res["key"], "test_http_key")
        self.assertEqual(get_res["value"], {"status": "all_subagents_nominal"})

    def test_http_agent_heartbeat(self):
        hb_res = self._post("/api/memory/agent/heartbeat", {
            "agent_id": "agent-diagnostic-probe",
            "operational_state": "idle",
            "capabilities": ["network_probe", "rtt_telemetry"]
        })
        self.assertEqual(hb_res["status"], "updated")
        self.assertEqual(hb_res["agent"]["operational_state"], "idle")

    def test_http_obsidian_sync_endpoint(self):
        sync_res = self._post("/api/memory/sync-obsidian", {})
        self.assertIn("status", sync_res)
        self.assertIn(sync_res["status"], ("SYNCHRONIZED", "PARTIAL_SYNC"))
        self.assertGreaterEqual(sync_res["written_files_count"], 1)

    def test_http_obsidian_status(self):
        status_res = self._get("/api/memory/obsidian-status")
        self.assertIn("status", status_res)
        self.assertIn("local_vault_exists", status_res)
        self.assertTrue(status_res["local_vault_exists"])


if __name__ == "__main__":
    unittest.main()
