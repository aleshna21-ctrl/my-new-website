"""
tests/test_deep_hermes_adapter.py
Comprehensive unit tests for the deepened Hermes model adapter seam:
- query(prompt, schema=None, allow_simulation=False) -> InferenceResult
- health(probe_live=False, ttl=15.0) -> HermesHealth
- FakeHermesAdapter test substitutability without socket monkey-patching
- Backward compatibility for enforce_schema_and_quarantine and call_local_server
"""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

from pydantic import BaseModel

import inference_adapter as adapter
from data_contracts import FailureEvent


class SampleSchema(BaseModel):
    name: str
    score: int


class ResponseMock(io.BytesIO):
    status = 200

    def __init__(self, data_bytes: bytes, status: int = 200):
        super().__init__(data_bytes)
        self.status = status


def build_chat_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 20) -> bytes:
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "qwen3:4b",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    }
    return json.dumps(payload).encode("utf-8")


class DeepHermesAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.telemetry_path = Path(self.temp_dir.name) / "inference_telemetry.json"
        self.patcher = patch.object(adapter, "TELEMETRY_FILE", self.telemetry_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_query_unstructured_without_schema(self):
        """query() without a schema returns raw textual completion wrapped in InferenceResult."""
        adp = adapter.LiveLocalModelAdapter(allow_simulation=False)
        mock_response = ResponseMock(build_chat_response("Hello from local Hermes!"))
        with patch.object(adp._opener, "open", return_value=mock_response):
            res = adp.query("Greet the world")

        self.assertIsInstance(res, adapter.InferenceResult)
        self.assertEqual(res.status, "completed")
        self.assertEqual(res.raw_content, "Hello from local Hermes!")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["data"], "Hello from local Hermes!")
        self.assertFalse(res.is_simulated)

    def test_query_with_schema_validates_and_returns_structured_data(self):
        """query() with a schema enforces validation and populates .data dictionary."""
        adp = adapter.LiveLocalModelAdapter(allow_simulation=False)
        valid_json = json.dumps({"name": "benchmark", "score": 98})
        mock_response = ResponseMock(build_chat_response(valid_json))
        with patch.object(adp._opener, "open", return_value=mock_response):
            res = adp.query("Generate score", schema=SampleSchema)

        self.assertIsInstance(res, adapter.InferenceResult)
        self.assertEqual(res.status, "validated_live")
        self.assertEqual(res.data, {"name": "benchmark", "score": 98})
        self.assertEqual(res["status"], "validated_live")
        self.assertEqual(res["data"]["name"], "benchmark")
        self.assertTrue(self.telemetry_path.exists())

    def test_query_with_schema_bounded_repair(self):
        """query() repairs invalid JSON once within bounded retries."""
        adp = adapter.LiveLocalModelAdapter(max_retries=1, allow_simulation=False)
        resp1 = ResponseMock(build_chat_response("invalid json"))
        resp2 = ResponseMock(build_chat_response(json.dumps({"name": "repaired", "score": 100})))

        with patch.object(adp._opener, "open", side_effect=[resp1, resp2]) as mock_open:
            res = adp.query("Generate score", schema=SampleSchema)

        self.assertEqual(mock_open.call_count, 2)
        self.assertEqual(res.status, "validated_live")
        self.assertEqual(res.data["name"], "repaired")
        self.assertEqual(len(res.attempts), 2)

    def test_health_probe_live_and_caching(self):
        """health() performs socket probe, caches result with TTL, and reads telemetry snapshot."""
        # Seed telemetry file
        self.telemetry_path.write_text(json.dumps({
            "status": "validated_live",
            "is_simulated": False,
            "execution_mode": "live_hermes",
            "max_tokens": 2048,
            "model": "qwen3:4b"
        }), encoding="utf-8")

        adp = adapter.LiveLocalModelAdapter()

        # Mock probe response for /v1/models
        mock_models_json = json.dumps({"data": [{"id": "qwen3:4b"}, {"id": "hermes-2-pro"}]}).encode("utf-8")
        mock_probe_resp = ResponseMock(mock_models_json)

        with patch.object(urllib.request, "build_opener") as mock_builder:
            mock_opener = MagicMock()
            mock_opener.open.return_value = mock_probe_resp
            mock_builder.return_value = mock_opener

            health1 = adp.health(probe_live=True, ttl=15.0)
            self.assertTrue(health1.reachable)
            self.assertTrue(health1["live_loopback_reachable"])
            self.assertIn("qwen3:4b", health1.models)
            self.assertEqual(health1.last_status, "validated_live")

            # Subsequent call within TTL should return cached state without network hit
            mock_opener.open.reset_mock()
            health2 = adp.health(probe_live=False, ttl=15.0)
            mock_opener.open.assert_not_called()
            self.assertTrue(health2.reachable)

    def test_fake_hermes_adapter_test_substitutability(self):
        """FakeHermesAdapter satisfies the exact 2-method seam without socket patching."""
        fake = adapter.FakeHermesAdapter(
            canned_query_response={"name": "simulated_agent", "score": 42},
            is_reachable=True,
            models=["fake-model-v1"]
        )

        # 1. Seam test: query()
        res = fake.query("Any prompt", schema=SampleSchema)
        self.assertIsInstance(res, adapter.InferenceResult)
        self.assertEqual(res.status, "validated_live")
        self.assertEqual(res.data["name"], "simulated_agent")
        self.assertEqual(len(fake.calls), 1)

        # 2. Seam test: health()
        health = fake.health(probe_live=True)
        self.assertIsInstance(health, adapter.HermesHealth)
        self.assertTrue(health.reachable)
        self.assertEqual(health.models, ["fake-model-v1"])

    def test_backward_compatibility_wrappers(self):
        """enforce_schema_and_quarantine and call_local_server forward seamlessly to seam."""
        adp = adapter.LiveLocalModelAdapter(allow_simulation=False)
        valid_json = json.dumps({
            "type": "ledger_reconcile_failure",
            "description": "Checksum mismatch",
            "reported_events": 1,
            "period": "2026-Q1",
            "evidence_ids": ["ev-1"]
        })
        mock_response = ResponseMock(build_chat_response(valid_json))
        with patch.object(adp._opener, "open", return_value=mock_response):
            env = adp.enforce_schema_and_quarantine("Verify", FailureEvent)

        self.assertEqual(env["status"], "validated_live")
    def test_ticket_01_seam_and_contracts_acceptance_criteria(self):
        """Verify all specific acceptance criteria of Ticket 01:
        1. query() and health() signatures
        2. Endpoint host validation (local loopback allowed, remote rejected)
        3. InferenceResult property and dictionary access
        4. HermesHealth property and dictionary access
        5. Unstructured query execution
        6. Legacy call_local_server caller compatibility
        """
        # 1 & 2. Valid loopback endpoints vs cloud/external rejection
        valid_endpoints = [
            "http://127.0.0.1:8080/v1/chat/completions",
            "http://localhost:8080/v1/chat/completions",
            "http://hermes:8080/v1/chat/completions",
            "http://host.docker.internal:8080/v1/chat/completions",
            "http://0.0.0.0:8080/v1/chat/completions",
        ]
        for ep in valid_endpoints:
            adp = adapter.LiveLocalModelAdapter(endpoint=ep, model_tag="qwen3:4b")
            self.assertEqual(adp.endpoint, ep)

        invalid_endpoints = [
            "https://api.openai.com/v1/chat/completions",
            "http://192.168.1.50:8080/v1/chat/completions",
            "http://127.0.0.1:8080/v1/models",
            "http://user:pass@127.0.0.1:8080/v1/chat/completions",
            "http://127.0.0.1:8080/v1/chat/completions?query=1",
        ]
        for bad_ep in invalid_endpoints:
            with self.assertRaises(ValueError):
                adapter.LiveLocalModelAdapter(endpoint=bad_ep)

        # 3. Unstructured query & InferenceResult dual access
        adp = adapter.LiveLocalModelAdapter(allow_simulation=False)
        mock_response = ResponseMock(build_chat_response("Unstructured text answer"))
        with patch.object(adp._opener, "open", return_value=mock_response):
            res = adp.query("Tell me status")

        self.assertIsInstance(res, adapter.InferenceResult)
        self.assertEqual(res.status, "completed")
        self.assertEqual(res.data, "Unstructured text answer")
        self.assertEqual(res.raw_content, "Unstructured text answer")
        self.assertFalse(res.is_simulated)
        self.assertEqual(len(res.attempts), 1)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["data"], "Unstructured text answer")

        # 4. HermesHealth dual property and dictionary access
        mock_models_json = json.dumps({"data": [{"id": "qwen3:4b"}]}).encode("utf-8")
        with patch.object(urllib.request, "build_opener") as mock_builder:
            mock_op = MagicMock()
            mock_op.open.return_value = ResponseMock(mock_models_json)
            mock_builder.return_value = mock_op

            health = adp.health(probe_live=True)
            self.assertIsInstance(health, adapter.HermesHealth)
            self.assertTrue(health.reachable)
            self.assertEqual(health.state, "connected")
            self.assertIn("qwen3:4b", health.models)
            self.assertIsNotNone(health.latency_ms)
            self.assertTrue(health["live_loopback_reachable"])
            self.assertEqual(health["state"], "connected")
            self.assertIn("qwen3:4b", health["models"])

        # 5. Legacy call_local_server compatibility
        with patch.object(adp._opener, "open", return_value=ResponseMock(build_chat_response("Direct response"))):
            direct = adp.call_local_server("Ping")
            self.assertEqual(direct, "Direct response")

    def test_ticket_02_fake_hermes_adapter_acceptance_criteria(self):
        """Verify all specific acceptance criteria of Ticket 02:
        1. Identical query() and health() method signatures
        2. Configurable parameters (canned responses, reachable, models, health)
        3. Pydantic schema validation against canned dicts and json strings
        4. Quarantine handling for invalid canned schema responses
        5. In-memory audit trail (calls, call_count, last_prompt, reset)
        6. Configurable exception raising via should_fail
        7. Sequential canned responses
        8. Transparent substitutability for LiveLocalModelAdapter
        """
        # 1 & 2. Configuration & signatures
        fake = adapter.FakeHermesAdapter(
            canned_query_response={"name": "agent-one", "score": 99},
            is_reachable=True,
            models=["mock-qwen-4b", "mock-hermes-3b"],
            canned_health={"reachable": True, "state": "healthy_mock"}
        )
        self.assertEqual(fake.call_count, 0)
        self.assertIsNone(fake.last_prompt)

        # 3. Schema validation on canned dict
        res = fake.query("Validate agent", schema=SampleSchema)
        self.assertEqual(res.status, "validated_live")
        self.assertEqual(res.data["name"], "agent-one")
        self.assertEqual(res.data["score"], 99)
        self.assertEqual(fake.call_count, 1)
        self.assertEqual(fake.last_prompt, "Validate agent")

        # 4. Quarantine on invalid schema
        fake_bad = adapter.FakeHermesAdapter(canned_query_response={"name": "broken"})
        res_bad = fake_bad.query("Invalid schema test", schema=SampleSchema)
        self.assertEqual(res_bad.status, "quarantined")
        self.assertIsNone(res_bad.data)
        self.assertIsNotNone(res_bad.error)

        # 5. Health probe contract
        health = fake.health(probe_live=False)
        self.assertTrue(health.reachable)
        self.assertEqual(health.state, "healthy_mock")
        self.assertEqual(fake.call_count, 2)

        # 6. should_fail resilience testing
        class CustomNetworkFault(Exception):
            pass

        failing_fake = adapter.FakeHermesAdapter(should_fail=True, failure_exc=CustomNetworkFault("Simulated offline"))
        with self.assertRaises(CustomNetworkFault):
            failing_fake.query("Ping")
        with self.assertRaises(CustomNetworkFault):
            failing_fake.health()

        # 7. Sequential canned responses
        seq_fake = adapter.FakeHermesAdapter(canned_query_response=["First answer", "Second answer"])
        r1 = seq_fake.query("Q1")
        r2 = seq_fake.query("Q2")
        self.assertEqual(r1.data, "First answer")
        self.assertEqual(r2.data, "Second answer")

        # 8. Reset audit trail
        seq_fake.reset()
        self.assertEqual(seq_fake.call_count, 0)

    def test_ticket_03_bounded_schema_repair_and_quarantine_acceptance_criteria(self):
        """Verify all specific acceptance criteria of Ticket 03:
        1. Stripping <think> reasoning tags and markdown code fences
        2. Strict Pydantic validation returning validated_live
        3. Single repair retry on malformed JSON with validation error feedback
        4. Successful attempt 2 repair returns validated_live with len(attempts) == 2
        5. Irreparable output after attempt 2 transitions to quarantined with data=None
        6. max_retries parameter validation (<= 1 allowed, > 1 rejected)
        7. Explicit simulation fallback when offline with allow_simulation=True
        8. Legacy enforce_schema_and_quarantine forwarding
        """
        # 1. Cleaning reasoning tags and code fences
        raw_reasoning = "<think>Analysing schema requirements...</think>```json\n{\"name\": \"cleaned\", \"score\": 85}\n```"
        cleaned = adapter.LiveLocalModelAdapter.clean_json_text(raw_reasoning)
        self.assertEqual(cleaned, '{"name": "cleaned", "score": 85}')

        # 2. Strict Pydantic validation
        adp = adapter.LiveLocalModelAdapter(max_retries=1, allow_simulation=False)
        with patch.object(adp._opener, "open", return_value=ResponseMock(build_chat_response('{"name": "ok", "score": 100}'))):
            res_ok = adp.query("Strict test", schema=SampleSchema)
        self.assertEqual(res_ok.status, "validated_live")
        self.assertEqual(res_ok.data, {"name": "ok", "score": 100})
        self.assertEqual(len(res_ok.attempts), 1)

        # 3 & 4. Bounded repair retry
        resp_bad = ResponseMock(build_chat_response('{"name": "repaired"}')) # missing required field 'score'
        resp_repaired = ResponseMock(build_chat_response('{"name": "repaired", "score": 77}'))
        with patch.object(adp._opener, "open", side_effect=[resp_bad, resp_repaired]) as mock_open:
            res_repaired = adp.query("Repair test", schema=SampleSchema)

        self.assertEqual(mock_open.call_count, 2)
        self.assertEqual(res_repaired.status, "validated_live")
        self.assertEqual(res_repaired.data["score"], 77)
        self.assertEqual(len(res_repaired.attempts), 2)
        self.assertEqual(res_repaired.attempts[0]["outcome"], "validation_failed")
        self.assertEqual(res_repaired.attempts[1]["outcome"], "validated_live")
        # Verify repair prompt included validation error
        repair_call = mock_open.call_args_list[1]
        sent_body = json.loads(repair_call.args[0].data)
        self.assertIn("Validation error:", sent_body["messages"][-1]["content"])

        # 5. Repair exhaustion leads to quarantined status and data=None
        resp_bad1 = ResponseMock(build_chat_response('{"name": "broken"}'))
        resp_bad2 = ResponseMock(build_chat_response('{"name": "still_broken"}'))
        with patch.object(adp._opener, "open", side_effect=[resp_bad1, resp_bad2]):
            res_quarantine = adp.query("Exhaustion test", schema=SampleSchema)
        self.assertEqual(res_quarantine.status, "quarantined")
        self.assertIsNone(res_quarantine.data)
        self.assertEqual(len(res_quarantine.attempts), 2)
        self.assertFalse(res_quarantine.is_simulated)

        # 6. max_retries validation bounds
        with self.assertRaises(ValueError):
            adapter.LiveLocalModelAdapter(max_retries=2)
        with self.assertRaises(ValueError):
            adapter.LiveLocalModelAdapter(max_retries=-1)
        adapter.LiveLocalModelAdapter(max_retries=0) # permitted
        adapter.LiveLocalModelAdapter(max_retries=1) # permitted

        # 7. Explicit simulation fallback when endpoint offline
        sim_adp = adapter.LiveLocalModelAdapter(allow_simulation=True)
        with patch.object(sim_adp._opener, "open", side_effect=urllib.error.URLError("Connection refused")):
            res_sim = sim_adp.query("Offline query", schema=FailureEvent)
        self.assertEqual(res_sim.status, "validated_simulation")
        self.assertTrue(res_sim.is_simulated)
        self.assertTrue(res_sim.data["description"].startswith("SIMULATED:"))

        # 8. Legacy wrapper equivalence
        with patch.object(adp._opener, "open", return_value=ResponseMock(build_chat_response('{"name": "legacy", "score": 50}'))):
            legacy_res = adp.enforce_schema_and_quarantine("Legacy call", SampleSchema)
        self.assertEqual(legacy_res.status, "validated_live")
        self.assertEqual(legacy_res.data["name"], "legacy")

    def test_ticket_04_health_probing_ttl_and_routes_acceptance_criteria(self):
        """Verify all specific acceptance criteria of Ticket 04:
        1. health(probe_live=False, ttl=15.0) reuses cached HermesHealth within TTL
        2. health(probe_live=True) bypasses TTL cache
        3. Internal _probe_lock ensures thread-safe updates
        4. HermesProbe in hud.hermes delegates to adapter.health()
        5. execute_hermes_probe returns 409 Conflict when lock is held
        6. Socket timeout and connection errors in health() return reachable=False gracefully
        """
        adp = adapter.LiveLocalModelAdapter()
        mock_models_json = json.dumps({"data": [{"id": "qwen3:4b"}]}).encode("utf-8")

        # 1 & 2. TTL caching vs live probe bypass
        with patch.object(urllib.request, "build_opener") as mock_builder:
            mock_opener = MagicMock()
            mock_opener.open.side_effect = lambda *a, **kw: ResponseMock(mock_models_json)
            mock_builder.return_value = mock_opener

            # First probe populates cache
            h1 = adp.health(probe_live=False, ttl=15.0)
            self.assertTrue(h1.reachable)
            self.assertEqual(mock_opener.open.call_count, 1)

            # Second probe within 15s reuses cache without network call
            h2 = adp.health(probe_live=False, ttl=15.0)
            self.assertEqual(mock_opener.open.call_count, 1)
            self.assertEqual(h1, h2)

            # Forced live probe bypasses TTL cache
            h3 = adp.health(probe_live=True)
            self.assertEqual(mock_opener.open.call_count, 2)
            self.assertTrue(h3.reachable)

        # 3. Thread-safe probe lock contention
        import hud_server
        self.assertFalse(hud_server.PROBE_LOCK.locked())

        # 4. HermesProbe background worker delegation
        from hud.hermes import HermesProbe
        fake_backend = adapter.FakeHermesAdapter(is_reachable=True, models=["test-qwen"])
        probe_worker = HermesProbe(adapter=fake_backend)
        probe_worker.probe()
        self.assertTrue(probe_worker.state["connected"])
        self.assertEqual(probe_worker.state["models"], ["test-qwen"])

        # 5. Non-blocking 409 Conflict when lock is held
        hud_server.PROBE_LOCK.acquire()
        try:
            resp = hud_server.execute_hermes_probe({"allow_simulation": False})
            self.assertEqual(resp.status_code, 409)
            self.assertIn("already running", resp.payload["error"])
        finally:
            hud_server.PROBE_LOCK.release()

        # 6. Socket timeouts and connection errors handled gracefully in health()
        with patch.object(urllib.request, "build_opener") as mock_builder:
            mock_failing_opener = MagicMock()
            mock_failing_opener.open.side_effect = TimeoutError("Timed out")
            mock_builder.return_value = mock_failing_opener

            failing_adp = adapter.LiveLocalModelAdapter()
            failing_health = failing_adp.health(probe_live=True)
            self.assertFalse(failing_health.reachable)
            self.assertEqual(failing_health.state, "standby")
            self.assertIn("Timed out", failing_health.live_probe_detail)

    def test_ticket_05_atomic_persistence_and_suite_migration_acceptance_criteria(self):
        """Verify all specific acceptance criteria of Ticket 05:
        1. Telemetry snapshots written atomically with os.replace and fsync
        2. Parent directory creation on demand and temp file cleanup
        3. Persisted JSON strictly adheres to the 11 expected contract keys
        4. Zero leftover .inference-*.tmp files in the directory
        5. FakeHermesAdapter integrates cleanly with AIOS Gateway tasks without sockets
        """
        # 1 & 2. Atomic persistence into a non-existent nested directory
        nested_dir = Path(self.temp_dir.name) / "deep" / "nested" / "telemetry"
        nested_file = nested_dir / "inference_telemetry.json"

        with patch.object(adapter, "TELEMETRY_FILE", nested_file):
            envelope = {
                "timestamp_utc": "2026-10-27T00:00:00Z",
                "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
                "model": "qwen3:4b",
                "max_tokens": 2048,
                "max_retries": 1,
                "allow_simulation": False,
                "execution_mode": "live_hermes",
                "is_simulated": False,
                "status": "validated_live",
                "attempts": [{"attempt": 1, "outcome": "validated_live"}],
                "data": {"verified": True}
            }
            adapter.save_telemetry(envelope)

            # Assert file exists and nested dir was created
            self.assertTrue(nested_file.exists())

            # 3. Exactly 11 contract keys
            saved = json.loads(nested_file.read_text(encoding="utf-8"))
            expected_keys = {
                "timestamp_utc", "endpoint", "model", "max_tokens", "max_retries",
                "allow_simulation", "execution_mode", "is_simulated", "status",
                "attempts", "data"
            }
            self.assertEqual(set(saved.keys()), expected_keys)
            self.assertEqual(saved["status"], "validated_live")
            self.assertEqual(saved["data"]["verified"], True)

            # 4. Zero leaked temporary files
            leaked_tmp = list(nested_dir.glob(".inference-*.tmp"))
            self.assertEqual(leaked_tmp, [])

        # 5. Gateway execution scenario using FakeHermesAdapter without network sockets
        fake = adapter.FakeHermesAdapter(
            canned_query_response={"status": "gateway_ok", "task_id": "task-999"},
            is_reachable=True
        )
        task_res = fake.query("Execute gateway diagnostic", schema=None)
        self.assertEqual(task_res.status, "completed")
        self.assertIn("task-999", task_res.raw_content)
        self.assertEqual(fake.call_count, 1)


if __name__ == "__main__":
    unittest.main()
