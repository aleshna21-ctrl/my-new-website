"""
tests/test_hermes_adapter_dashboard_integration.py
Comprehensive Integration & Functionality Tests for the Hermes Adapter with AIOS Dashboard.

Verifies:
1. Adapter Initialization & Host Resolution (Local, Docker network aliases, reject cloud/external).
2. Data Sanitization & Cleaning (<think> tags stripped, markdown fences removed).
3. Schema Validation, Quarantine & Bounded Repair Logic.
4. Atomic Telemetry Persistence (inference_telemetry.json).
5. AIOS Dashboard Frame Composition & Node Telemetry Ingestion.
6. Gateway RPC Integration & Two-Way Token Metric Reporting.
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT))

import data_contracts
from data_contracts import FailureEvent
import inference_adapter as adapter
from hud import gateway
from hud import os_dashboard as osd
import hud_server


class ResponseMock(io.BytesIO):
    status = 200

    def __init__(self, data_bytes: bytes, status: int = 200):
        super().__init__(data_bytes)
        self.status = status


def build_completion_payload(content_str: str, prompt_tokens: int = 15, completion_tokens: int = 25, finish_reason: str = "stop") -> bytes:
    payload = {
        "id": "chatcmpl-test-001",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "qwen3:4b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content_str},
                "finish_reason": finish_reason
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    }
    return json.dumps(payload).encode("utf-8")


class HermesAdapterConfigurationTests(unittest.TestCase):
    def test_local_and_container_hostnames_allowed(self):
        valid_endpoints = [
            "http://127.0.0.1:8080/v1/chat/completions",
            "http://localhost:8080/v1/chat/completions",
            "http://hermes:8080/v1/chat/completions",
            "http://host.docker.internal:8080/v1/chat/completions",
            "http://0.0.0.0:8080/v1/chat/completions"
        ]
        for ep in valid_endpoints:
            with self.subTest(endpoint=ep):
                obj = adapter.LiveLocalModelAdapter(endpoint=ep, model_tag="qwen3:4b")
                self.assertEqual(obj.endpoint, ep)
                self.assertEqual(obj.model_tag, "qwen3:4b")

    def test_remote_and_invalid_endpoints_rejected(self):
        invalid_endpoints = [
            "https://api.openai.com/v1/chat/completions",      # Cloud HTTPS rejected
            "http://192.168.1.50:8080/v1/chat/completions",    # External IP rejected
            "http://127.0.0.1:8080/v1/completions",            # Invalid path
            "http://user:pass@127.0.0.1:8080/v1/chat/completions", # User auth rejected
            "http://127.0.0.1:8080/v1/chat/completions?arg=1", # Query params rejected
        ]
        for ep in invalid_endpoints:
            with self.subTest(endpoint=ep):
                with self.assertRaises(ValueError):
                    adapter.LiveLocalModelAdapter(endpoint=ep)

    def test_strict_parameter_types_and_bounds(self):
        with self.assertRaises(ValueError):
            adapter.LiveLocalModelAdapter(max_retries=2)  # max_retries > 1 forbidden
        with self.assertRaises(ValueError):
            adapter.LiveLocalModelAdapter(max_tokens=5000)  # max_tokens > 4096 forbidden
        with self.assertRaises(ValueError):
            adapter.LiveLocalModelAdapter(allow_simulation="true")  # must be bool


class HermesAdapterDataCleaningTests(unittest.TestCase):
    def test_think_tags_stripped_from_reasoning_models(self):
        raw = "<think>\nLet us analyze the problem step-by-step.\nThe invoice is invalid.\n</think>\n{\"type\": \"error\", \"description\": \"Data breach\", \"reported_events\": 1, \"period\": \"Q2\", \"evidence_ids\": []}"
        cleaned = adapter.LiveLocalModelAdapter.clean_json_text(raw)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("Let us analyze", cleaned)
        parsed = json.loads(cleaned)
        self.assertEqual(parsed["type"], "error")
        self.assertEqual(parsed["reported_events"], 1)

    def test_markdown_code_fences_stripped(self):
        raw = "```json\n{\"type\": \"test\", \"description\": \"Valid\", \"reported_events\": 3, \"period\": \"Q3\", \"evidence_ids\": []}\n```"
        cleaned = adapter.LiveLocalModelAdapter.clean_json_text(raw)
        self.assertFalse(cleaned.startswith("```"))
        self.assertFalse(cleaned.endswith("```"))
        parsed = json.loads(cleaned)
        self.assertEqual(parsed["type"], "test")


class HermesAdapterExecutionAndQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.telemetry_path = Path(self.temp_dir.name) / "inference_telemetry.json"
        self.patcher = patch.object(adapter, "TELEMETRY_FILE", self.telemetry_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_successful_inference_and_schema_validation(self):
        adp = adapter.LiveLocalModelAdapter(allow_simulation=False)
        valid_json = json.dumps({
            "type": "ledger_reconcile_failure",
            "description": "Checksum invariant mismatch",
            "reported_events": 2,
            "period": "2026-Q1",
            "evidence_ids": ["ev-101", "ev-102"]
        })
        mock_response = ResponseMock(build_completion_payload(valid_json, prompt_tokens=22, completion_tokens=35))

        with patch.object(adp._opener, "open", return_value=mock_response):
            envelope = adp.enforce_schema_and_quarantine("Verify invariant", FailureEvent)

        self.assertEqual(envelope["status"], "validated_live")
        self.assertFalse(envelope["is_simulated"])
        self.assertEqual(envelope["data"]["type"], "ledger_reconcile_failure")
        self.assertEqual(envelope["data"]["reported_events"], 2)

        # Check telemetry file written atomically
        self.assertTrue(self.telemetry_path.exists())
        saved = json.loads(self.telemetry_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "validated_live")
        self.assertEqual(saved["attempts"][0]["usage"]["total_tokens"], 57)

    def test_single_repair_recovers_malformed_first_attempt(self):
        adp = adapter.LiveLocalModelAdapter(max_retries=1, allow_simulation=False)
        bad_json = "Malformed JSON output without quotes"
        good_json = json.dumps({
            "type": "recovered_event",
            "description": "Repaired valid JSON",
            "reported_events": 1,
            "period": "2026-Q4",
            "evidence_ids": ["ev-repaired"]
        })
        resp1 = ResponseMock(build_completion_payload(bad_json))
        resp2 = ResponseMock(build_completion_payload(good_json))

        with patch.object(adp._opener, "open", side_effect=[resp1, resp2]) as mock_open:
            envelope = adp.enforce_schema_and_quarantine("Verify input", FailureEvent)

        self.assertEqual(mock_open.call_count, 2)
        self.assertEqual(envelope["status"], "validated_live")
        self.assertEqual(len(envelope["attempts"]), 2)
        self.assertEqual(envelope["attempts"][0]["outcome"], "validation_failed")
        self.assertEqual(envelope["attempts"][1]["outcome"], "validated_live")
        self.assertEqual(envelope["data"]["description"], "Repaired valid JSON")

    def test_repair_exhaustion_quarantines_and_preserves_audit_trail(self):
        adp = adapter.LiveLocalModelAdapter(max_retries=1, allow_simulation=False)
        bad_json1 = "{\"type\": \"broken\""
        bad_json2 = "{\"type\": \"still_broken\""
        resp1 = ResponseMock(build_completion_payload(bad_json1))
        resp2 = ResponseMock(build_completion_payload(bad_json2))

        with patch.object(adp._opener, "open", side_effect=[resp1, resp2]):
            envelope = adp.enforce_schema_and_quarantine("Test prompt", FailureEvent)

        self.assertEqual(envelope["status"], "quarantined")
        self.assertIsNone(envelope["data"])
        self.assertEqual(len(envelope["attempts"]), 2)
        self.assertFalse(envelope["is_simulated"])


class HermesDashboardTelemetryIntegrationTests(unittest.TestCase):
    def test_dashboard_frame_integrates_hermes_node(self):
        mock_gateway = {
            "status": "ok",
            "service": "aios-gateway-host",
            "protocol": "JSON-RPC 2.0 / REST Webhook",
            "hermes_online": True,
            "hermes_service": "hermes-gateway-daemon",
            "hermes_agent_online": True,
            "hermes_agent_url": "http://127.0.0.1:32768",
            "endpoint_hermes": "http://127.0.0.1:8080/gateway/v1/rpc",
            "crons_total": 5,
            "crons_enabled": 5,
            "tasks_executed": 40,
            "replay_cache_size": 0,
            "timestamp_utc": "2026-10-26T00:00:00Z"
        }
        with patch.object(hud_server, "get_gateway_status", return_value=mock_gateway):
            frame = hud_server.os_frame()

        self.assertIn("nodes", frame)
        self.assertIn("hermes", frame["nodes"])
        self.assertIn("model", frame["nodes"])
        self.assertEqual(frame["counters"]["gateway_tasks"], 40)
        self.assertEqual(frame["counters"]["gateway_crons"], 5)
        self.assertTrue(frame["counters"]["gateway_online"])
        self.assertTrue(frame["gateway"]["hermes_online"])
        self.assertEqual(frame["gateway"]["hermes_service"], "hermes-gateway-daemon")
        self.assertTrue(frame["gateway"]["hermes_agent_online"])

    def test_dashboard_frame_gracefully_handles_offline_hermes(self):
        mock_gateway = {
            "status": "ok",
            "hermes_online": False,
            "hermes_service": "hermes-8080",
            "hermes_agent_online": False,
            "endpoint_hermes": "http://127.0.0.1:8080/gateway/v1/rpc",
            "crons_total": 5,
            "crons_enabled": 5,
            "tasks_executed": 12,
            "replay_cache_size": 0,
            "timestamp_utc": "2026-10-26T00:00:00Z"
        }
        with patch.object(hud_server, "get_gateway_status", return_value=mock_gateway):
            frame = hud_server.os_frame()

        self.assertFalse(frame["counters"]["gateway_online"])
        self.assertFalse(frame["gateway"]["hermes_online"])
        self.assertFalse(frame["gateway"]["hermes_agent_online"])
        self.assertEqual(frame["counters"]["gateway_tasks"], 12)


class HermesGatewayTaskExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_path = Path(self.temp_dir.name) / "gateway_tasks.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_model_inference_task_execution_records_tokens(self):
        with patch.object(gateway, "TASKS_REGISTRY_PATH", self.tasks_path):
            mock_resp_json = {
                "choices": [{"message": {"content": "System operating normally at nominal latency."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 28, "total_tokens": 40}
            }
            mock_http_resp = ResponseMock(json.dumps(mock_resp_json).encode("utf-8"))

            mock_cm = MagicMock()
            mock_cm.__enter__.return_value = mock_http_resp
            mock_cm.__exit__.return_value = None

            with patch("urllib.request.build_opener") as mock_build:
                mock_opener_instance = MagicMock()
                mock_opener_instance.open.return_value = mock_cm
                mock_build.return_value = mock_opener_instance

                record = gateway.execute_task_command("model_inference", {
                    "prompt": "Evaluate system health",
                    "model": "qwen3:4b"
                })

            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["command"], "model_inference")
            self.assertIn("System operating normally", record["result"]["response"])
            self.assertEqual(record["result"]["raw_usage"]["total_tokens"], 40)
            self.assertGreaterEqual(record["duration_ms"], 0.0)

            # Confirm recorded in task history
            history = gateway.load_task_history(path=self.tasks_path)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["task_id"], record["task_id"])

    def test_gateway_rpc_two_way_board_sync(self):
        temp_board = Path(self.temp_dir.name) / "test_board.json"
        initial_board = {
            "revision": 1,
            "updated_at": "2026-10-26T00:00:00Z",
            "columns": [{"id": "todo", "title": "To Do"}],
            "tasks": [{"id": "task-01", "title": "Existing Task", "status": "todo", "priority": 2, "vital": False}]
        }
        temp_board.write_text(json.dumps(initial_board), encoding="utf-8")

        sync_params = {
            "board_path": temp_board,
            "tasks": [
                {"title": "Hermes Autonomous Discovered Task", "priority": 1, "vital": True, "estimate_min": 45}
            ]
        }
        res = gateway.execute_gateway_rpc("hermes.board.sync", sync_params)
        self.assertEqual(res["result"]["status"], "ok")
        self.assertEqual(res["result"]["synced_count"], 1)
        self.assertEqual(res["result"]["total_tasks"], 2)


if __name__ == "__main__":
    unittest.main()
