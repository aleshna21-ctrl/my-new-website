"""Regression tests. All telemetry is isolated in temporary directories."""
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, r"C:\Users\alesh\jev-workspace\delivery-offline")
sys.path.insert(0, str(HERE))
import inference_adapter as adapter
from data_contracts import FailureEvent
import hud_server as hud

EVENT = {"type": "probe_test", "description": "Test record", "reported_events": 1,
         "period": "TEST", "evidence_ids": ["ev-test"]}


class Response(io.BytesIO):
    status = 200


def response(content=None, **extra):
    message = {"content": json.dumps(EVENT) if content is None else content}
    message.update(extra)
    return Response(json.dumps({"choices": [{"message": message, "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50}}).encode())


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.telemetry = Path(self.temp.name) / "inference_telemetry.json"
        self.file_patch = patch.object(adapter, "TELEMETRY_FILE", self.telemetry)
        self.file_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.temp.cleanup()

    def test_hud_constructor_and_legacy_model_alias_are_compatible(self):
        obj = adapter.LiveLocalModelAdapter(allow_simulation=False, model_name="qwen3:4b")
        self.assertFalse(obj.allow_simulation)
        self.assertEqual(obj.model_tag, "qwen3:4b")

    def test_configuration_rejects_cloud_endpoints_and_unbounded_repairs(self):
        for kwargs in ({"endpoint": "https://example.com/v1/chat/completions"},
                       {"max_retries": 2}, {"max_tokens": 4097}, {"allow_simulation": "false"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                adapter.LiveLocalModelAdapter(**kwargs)

    def test_strict_connection_failure_is_quarantined_and_replaces_old_telemetry(self):
        self.telemetry.write_text(json.dumps({"is_simulated": True, "status": "validated_simulation"}))
        obj = adapter.LiveLocalModelAdapter()
        with patch.object(obj._opener, "open", side_effect=urllib.error.URLError("refused")) as network:
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(result["status"], "quarantined")
        self.assertIsNone(result["data"])
        self.assertFalse(result["is_simulated"])
        self.assertEqual(json.loads(self.telemetry.read_text()), result)

    def test_explicit_simulation_is_visibly_marked(self):
        obj = adapter.LiveLocalModelAdapter(allow_simulation=True)
        with patch.object(obj._opener, "open", side_effect=urllib.error.URLError("refused")):
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(result["status"], "validated_simulation")
        self.assertTrue(result["is_simulated"])
        self.assertTrue(result["data"]["description"].startswith("SIMULATED:"))

    def test_socket_timeout_becomes_a_recorded_failure(self):
        obj = adapter.LiveLocalModelAdapter()
        with patch.object(obj._opener, "open", side_effect=TimeoutError("timed out")):
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(result["attempts"][0]["error_kind"], "timeout")

    def test_model_http_rejection_preserves_status_and_response_body(self):
        obj = adapter.LiveLocalModelAdapter()
        error = urllib.error.HTTPError(obj.endpoint, 404, "Not Found", {}, io.BytesIO(b'{"error":"model missing"}'))
        with patch.object(obj._opener, "open", side_effect=error):
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        record = result["attempts"][0]
        self.assertEqual(record["http_status"], 404)
        self.assertIn("model missing", record["error"])
        self.assertEqual(result["execution_mode"], "live_error")
        self.assertIsNone(result["data"])

    def test_one_repair_can_recover_invalid_json(self):
        obj = adapter.LiveLocalModelAdapter()
        with patch.object(obj._opener, "open", side_effect=[response("not json"), response()]) as network:
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(result["status"], "validated_live")
        self.assertEqual(result["data"], EVENT)
        repair_request = json.loads(network.call_args_list[1].args[0].data)
        self.assertIn("not json", repair_request["messages"][-1]["content"])
        self.assertIn("reported_events", repair_request["messages"][-1]["content"])

    def test_fractional_event_count_is_not_coerced_to_an_integer(self):
        obj = adapter.LiveLocalModelAdapter(max_retries=0)
        bad = dict(EVENT, reported_events=1.5)
        with patch.object(obj._opener, "open", return_value=response(json.dumps(bad))):
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(result["status"], "quarantined")
        self.assertIsNone(result["data"])

    def test_repair_exhaustion_is_quarantined_after_two_attempts(self):
        obj = adapter.LiveLocalModelAdapter()
        with patch.object(obj._opener, "open", side_effect=[response("{}"), response("{}")]) as network:
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(len(result["attempts"]), 2)

    def test_reasoning_cannot_substitute_for_a_missing_final_answer(self):
        obj = adapter.LiveLocalModelAdapter(max_retries=0)
        with patch.object(obj._opener, "open", return_value=response("", reasoning=json.dumps(EVENT))):
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(result["status"], "quarantined")

    def test_live_output_records_actual_usage_and_atomic_snapshot(self):
        obj = adapter.LiveLocalModelAdapter()
        with patch.object(obj._opener, "open", return_value=response()):
            result = obj.enforce_schema_and_quarantine("input", FailureEvent)
        self.assertEqual(result["status"], "validated_live")
        self.assertEqual(result["attempts"][0]["usage"]["completion_tokens"], 30)
        self.assertFalse(result["allow_simulation"])
        self.assertEqual(list(Path(self.temp.name).glob(".inference-*")), [])


class HUDTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file_patch = patch.object(adapter, "TELEMETRY_FILE", self.root / "inference_telemetry.json")
        self.file_patch.start()
        self.offline_patch = patch.object(hud, "OFFLINE_DIR", str(self.root))
        self.offline_patch.start()
        self.server = hud.HUDHTTPServer(("127.0.0.1", 0), hud.HUDRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.file_patch.stop()
        self.offline_patch.stop()
        self.temp.cleanup()

    def post(self, body):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST", "/api/hermes/probe", json.dumps(body), {"Content-Type": "application/json"})
            reply = connection.getresponse()
            return reply.status, json.loads(reply.read())
        finally:
            connection.close()

    def test_hud_strict_route_returns_validated_live_data(self):
        def answer(request, **kwargs):
            payload = json.loads(request.data)
            prompt = payload["messages"][-1]["content"]
            sample = json.loads(prompt.split("preserving all values: ", 1)[1])
            return response(json.dumps(sample))
        with patch("urllib.request.OpenerDirector.open", side_effect=answer):
            status, result = self.post({"allow_simulation": False})
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "validated_live")
        self.assertFalse(result["is_simulated"])
        self.assertTrue(result["data"]["evidence_ids"][0].startswith("hud-probe-"))

    def test_hud_rejects_string_false_instead_of_enabling_simulation(self):
        status, result = self.post({"allow_simulation": "false"})
        self.assertEqual(status, 400)
        self.assertIn("JSON boolean", result["error"])

    def test_hud_returns_json_when_the_backend_raises(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=RuntimeError("test failure")):
            status, result = self.post({"allow_simulation": False})
        self.assertEqual(status, 500)
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertFalse(hud.PROBE_LOCK.locked())

    def test_concurrent_probe_gets_a_clear_busy_response(self):
        hud.PROBE_LOCK.acquire()
        try:
            status, result = self.post({"allow_simulation": False})
        finally:
            hud.PROBE_LOCK.release()
        self.assertEqual(status, 409)
        self.assertIn("already running", result["error"])

    def test_fresh_connectivity_is_separate_from_saved_simulation(self):
        (self.root / "inference_telemetry.json").write_text(json.dumps({"is_simulated": True, "status": "validated_simulation"}))
        with patch("urllib.request.OpenerDirector.open", return_value=Response(b"{}")):
            result = hud.get_hermes_telemetry()
        self.assertTrue(result["live_loopback_reachable"])
        self.assertTrue(result["is_simulated"])
        self.assertIn("server_pid", result)

    def test_a_second_server_cannot_bind_the_same_port(self):
        with self.assertRaises(OSError):
            second = hud.HUDHTTPServer(("127.0.0.1", self.server.server_port), hud.HUDRequestHandler)
            second.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
