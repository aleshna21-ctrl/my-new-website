"""Local inference with strict validation, bounded repair, and explicit provenance."""
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Type

from pydantic import BaseModel, ValidationError
from data_contracts import FailureEvent

TARGET_DIR = Path(__file__).resolve().parent
TELEMETRY_FILE = TARGET_DIR / "inference_telemetry.json"


class InferenceFailure(Exception):
    def __init__(self, kind, detail, http_status=None):
        super().__init__(detail)
        self.kind = kind
        self.http_status = http_status


def save_telemetry(envelope):
    """Publish a complete snapshot so readers never see a partially written JSON file."""
    target = Path(TELEMETRY_FILE)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".inference-", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            json.dump(envelope, stream, indent=2, allow_nan=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


DEFAULT_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_MODEL = "qwen3:4b"


class LiveLocalModelAdapter:
    def __init__(self, endpoint=None,
                 model_tag=None, max_retries=1, max_tokens=2048,
                 allow_simulation=False, timeout=45, model_name=None):
        if endpoint is None:
            endpoint = os.environ.get("HERMES_ENDPOINT", DEFAULT_ENDPOINT)
        url = urllib.parse.urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1", "hermes", "host.docker.internal", "0.0.0.0")
                or url.path != "/v1/chat/completions" or url.username or url.password
                or url.query or url.fragment):
            raise ValueError("Inference endpoint must be a local HTTP chat-completions endpoint.")
        if type(allow_simulation) is not bool:
            raise ValueError("allow_simulation must be a JSON boolean.")
        if type(max_retries) is not int or not 0 <= max_retries <= 1:
            raise ValueError("At most one repair retry is permitted.")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ValueError("max_tokens must be an integer between 1 and 4096.")
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError("timeout must be greater than zero and at most 60 seconds.")
        self.endpoint = endpoint
        resolved_tag = model_name if model_name is not None else (model_tag if model_tag is not None else os.environ.get("HERMES_MODEL", DEFAULT_MODEL))
        if not isinstance(resolved_tag, str) or not resolved_tag.strip():
            raise ValueError("A model tag is required.")
        self.model_tag = resolved_tag
        self.model_name = self.model_tag
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.allow_simulation = allow_simulation
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._usage = {}
        self._finish_reason = None

    @staticmethod
    def clean_json_text(text):
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        return text.strip()

    def call_local_server(self, prompt):
        """Return only final answer content. Reasoning is never accepted as extracted data."""
        self._usage = {}
        self._finish_reason = None
        payload = {
            "model": self.model_tag,
            "messages": [
                {"role": "system", "content": "Extract only facts supplied in the input. Return one JSON object matching the supplied schema. Keep monetary values as strings. No commentary."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode("utf-8"),
                                        headers={"Content-Type": "application/json", "User-Agent": "JEV-Inference-Adapter"}, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise InferenceFailure("http_error", "Ollama HTTP %s: %s" % (exc.code, detail), exc.code) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            kind = "timeout" if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError) else "connection_error"
            raise InferenceFailure(kind, str(exc)) from exc
        try:
            result = json.loads(body, parse_float=Decimal)
            choice = result["choices"][0]
            content = choice["message"].get("content")
            usage = result.get("usage", {})
            self._usage = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                           if type(usage.get(key)) is int and usage[key] >= 0}
            self._finish_reason = choice.get("finish_reason")
            if not isinstance(content, str):
                content = ""
            return self.clean_json_text(content)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise InferenceFailure("invalid_response", "Ollama returned an invalid completion envelope: " + str(exc)) from exc

    def enforce_schema_and_quarantine(self, prompt: str, schema: Type[BaseModel]):
        contract = json.dumps(schema.model_json_schema(), ensure_ascii=True)
        original_prompt = "Return only a JSON object. Schema:\n" + contract + "\n\nInput:\n" + prompt
        current_prompt = original_prompt
        attempts = []
        data = None
        status = "quarantined"
        mode = "live_hermes"
        simulated = False
        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            error = None
            raw = ""
            failure = None
            try:
                raw = self.call_local_server(current_prompt)
            except InferenceFailure as exc:
                failure = exc
                error = str(exc)
                if self.allow_simulation:
                    raw = json.dumps({"type": "batch_export_failure", "description": "SIMULATED: Column mismatch in CSV header",
                                      "reported_events": 2, "period": "Q1", "evidence_ids": ["ev-sim-99"]})
                    simulated = True
                    mode = "simulated_fallback"
                else:
                    mode = "endpoint_offline" if exc.kind in ("timeout", "connection_error") else "live_error"
            record = {"attempt": attempt, "execution_mode": mode,
                      "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                      "usage": dict(self._usage), "finish_reason": self._finish_reason,
                      "estimated_tokens": max(1, (len(current_prompt) + len(raw)) // 4),
                      "error": error}
            if failure:
                record.update(error_kind=failure.kind, http_status=failure.http_status)
                if not simulated:
                    record["outcome"] = "quarantined"
                    attempts.append(record)
                    break
            try:
                validated = schema.model_validate_json(raw, strict=True)
                data = validated.model_dump(mode="json")
                status = "validated_simulation" if simulated else "validated_live"
                record["outcome"] = status
                attempts.append(record)
                break
            except ValidationError as exc:
                record["outcome"] = "validation_failed"
                record["error"] = str(exc)
                if self._finish_reason == "length":
                    record["error_kind"] = "token_limit"
                attempts.append(record)
                if simulated:
                    break
                current_prompt = (original_prompt + "\n\nYour previous answer:\n" + raw[:12000]
                                  + "\n\nValidation error:\n" + str(exc)[:6000]
                                  + "\nRepair only those errors. Return one JSON object using only the supplied input.")
        envelope = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "endpoint": self.endpoint,
                    "model": self.model_tag, "max_tokens": self.max_tokens, "max_retries": self.max_retries,
                    "allow_simulation": self.allow_simulation, "execution_mode": mode,
                    "is_simulated": simulated, "status": status, "attempts": attempts, "data": data}
        save_telemetry(envelope)
        return envelope


if __name__ == "__main__":
    event = {"type": "probe_test", "description": "Synthetic CLI probe", "reported_events": 1,
             "period": "TEST", "evidence_ids": ["cli-probe"]}
    result = LiveLocalModelAdapter().enforce_schema_and_quarantine(json.dumps(event), FailureEvent)
    print(json.dumps(result, indent=2))
