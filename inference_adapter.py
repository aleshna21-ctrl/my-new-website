"""Local inference with strict validation, bounded repair, explicit provenance, and unified health probing."""
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError
from data_contracts import FailureEvent

TARGET_DIR = Path(__file__).resolve().parent
TELEMETRY_FILE = TARGET_DIR / "inference_telemetry.json"


class InferenceFailure(Exception):
    def __init__(self, kind: str, detail: str, http_status: Optional[int] = None):
        super().__init__(detail)
        self.kind = kind
        self.http_status = http_status


def save_telemetry(envelope: Dict[str, Any]) -> None:
    """Publish a complete snapshot so readers never see a partially written JSON file."""
    target = Path(TELEMETRY_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
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
            try:
                os.unlink(temporary)
            except OSError:
                pass


DEFAULT_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
DEFAULT_MODEL = "qwen3:4b"


class InferenceResult(dict):
    """Deep result object representing inference execution, backward-compatible with dict."""

    def __init__(self, *args, raw_content: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._raw_content = raw_content

    @property
    def status(self) -> str:
        return self.get("status", "none")

    @property
    def data(self) -> Any:
        return self.get("data")

    @property
    def raw_content(self) -> str:
        if self._raw_content:
            return self._raw_content
        d = self.get("data")
        return d if isinstance(d, str) else ""

    @property
    def is_simulated(self) -> bool:
        return bool(self.get("is_simulated", False))

    @property
    def execution_mode(self) -> str:
        return self.get("execution_mode", "live_hermes")

    @property
    def attempts(self) -> List[Dict[str, Any]]:
        return self.get("attempts", [])

    @property
    def usage(self) -> Dict[str, int]:
        attempts = self.get("attempts", [])
        if attempts and isinstance(attempts[-1], dict) and "usage" in attempts[-1]:
            return attempts[-1]["usage"]
        return {}

    @property
    def error(self) -> Optional[str]:
        attempts = self.get("attempts", [])
        if attempts and isinstance(attempts[-1], dict):
            return attempts[-1].get("error")
        return None

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'InferenceResult' object has no attribute '{name}'")


class HermesHealth(dict):
    """Deep health status representing Hermes model socket state and cached telemetry."""

    def __init__(self, reachable: bool = False, models: Optional[List[str]] = None,
                 state: str = "standby", latency_ms: str = "0",
                 live_probe_detail: str = "OK", telemetry: Optional[Dict[str, Any]] = None,
                 **extra):
        models = models or []
        payload = {
            "reachable": reachable,
            "live_loopback_reachable": reachable,
            "models": models,
            "state": state,
            "latency_ms": latency_ms,
            "live_probe_detail": live_probe_detail,
            "telemetry": telemetry,
            **extra
        }
        super().__init__(payload)

    @property
    def reachable(self) -> bool:
        return bool(self.get("reachable", False))

    @property
    def models(self) -> List[str]:
        return self.get("models", [])

    @property
    def state(self) -> str:
        return self.get("state", "standby")

    @property
    def last_status(self) -> str:
        return self.get("last_status", "none")

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'HermesHealth' object has no attribute '{name}'")


class LiveLocalModelAdapter:
    """Production HTTP client for local Hermes inference and socket health probing."""

    def __init__(self, endpoint: Optional[str] = None,
                 model_tag: Optional[str] = None, max_retries: int = 1, max_tokens: int = 2048,
                 allow_simulation: bool = False, timeout: float = 45, model_name: Optional[str] = None,
                 keep_alive: int = -1):
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
        self.keep_alive = keep_alive
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._usage: Dict[str, int] = {}
        self._finish_reason: Optional[str] = None

        # Thread-safe internal probe lock and TTL cache
        self._probe_lock = threading.Lock()
        self._cached_health: Optional[HermesHealth] = None
        self._cached_health_at: float = 0.0

    @staticmethod
    def clean_json_text(text: str) -> str:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        return text.strip()

    def get_models_url(self) -> str:
        """Derive /v1/models URL from the chat completions endpoint."""
        url = urllib.parse.urlsplit(self.endpoint)
        path = url.path
        if path.endswith("/chat/completions"):
            base_path = path[:-len("/chat/completions")]
            models_path = f"{base_path}/models"
        else:
            models_path = "/v1/models"
        return f"{url.scheme}://{url.netloc}{models_path}"

    def call_local_server(self, prompt: str) -> str:
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
            "keep_alive": self.keep_alive,
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

    def query(self, prompt: str, schema: Optional[Type[BaseModel]] = None,
              allow_simulation: Optional[bool] = None) -> InferenceResult:
        """Unified inference seam handling raw textual queries and bounded schema extraction."""
        sim_allowed = self.allow_simulation if allow_simulation is None else allow_simulation

        if schema is None:
            # Unstructured query
            started = time.perf_counter()
            try:
                raw = self.call_local_server(prompt)
                latency = round((time.perf_counter() - started) * 1000, 1)
                envelope = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "endpoint": self.endpoint,
                    "model": self.model_tag,
                    "max_tokens": self.max_tokens,
                    "max_retries": self.max_retries,
                    "allow_simulation": sim_allowed,
                    "execution_mode": "live_hermes",
                    "is_simulated": False,
                    "status": "completed",
                    "attempts": [{
                        "attempt": 1,
                        "execution_mode": "live_hermes",
                        "latency_ms": latency,
                        "usage": dict(self._usage),
                        "outcome": "completed",
                        "error": None
                    }],
                    "data": raw
                }
                return InferenceResult(envelope, raw_content=raw)
            except InferenceFailure as exc:
                latency = round((time.perf_counter() - started) * 1000, 1)
                if sim_allowed:
                    sim_content = f"SIMULATED: Fallback response for prompt: {prompt[:60]}"
                    envelope = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "endpoint": self.endpoint,
                        "model": self.model_tag,
                        "max_tokens": self.max_tokens,
                        "max_retries": self.max_retries,
                        "allow_simulation": True,
                        "execution_mode": "simulated_fallback",
                        "is_simulated": True,
                        "status": "simulated",
                        "attempts": [{
                            "attempt": 1,
                            "execution_mode": "simulated_fallback",
                            "latency_ms": latency,
                            "usage": {},
                            "outcome": "simulated",
                            "error": str(exc)
                        }],
                        "data": sim_content
                    }
                    return InferenceResult(envelope, raw_content=sim_content)
                envelope = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "endpoint": self.endpoint,
                    "model": self.model_tag,
                    "max_tokens": self.max_tokens,
                    "max_retries": self.max_retries,
                    "allow_simulation": False,
                    "execution_mode": "endpoint_offline" if exc.kind in ("timeout", "connection_error") else "live_error",
                    "is_simulated": False,
                    "status": "error",
                    "attempts": [{
                        "attempt": 1,
                        "execution_mode": "endpoint_offline" if exc.kind in ("timeout", "connection_error") else "live_error",
                        "latency_ms": latency,
                        "usage": {},
                        "outcome": "failed",
                        "error": str(exc),
                        "error_kind": exc.kind
                    }],
                    "data": None
                }
                return InferenceResult(envelope, raw_content="")

        # Structured schema query with bounded repair
        contract = json.dumps(schema.model_json_schema(), ensure_ascii=True)
        original_prompt = "Return only a JSON object. Schema:\n" + contract + "\n\nInput:\n" + prompt
        current_prompt = original_prompt
        attempts = []
        data = None
        status = "quarantined"
        mode = "live_hermes"
        simulated = False
        last_raw = ""

        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            error = None
            raw = ""
            failure = None
            try:
                raw = self.call_local_server(current_prompt)
                last_raw = raw
            except InferenceFailure as exc:
                failure = exc
                error = str(exc)
                if sim_allowed:
                    raw = json.dumps({"type": "batch_export_failure", "description": "SIMULATED: Column mismatch in CSV header",
                                      "reported_events": 2, "period": "Q1", "evidence_ids": ["ev-sim-99"]})
                    simulated = True
                    mode = "simulated_fallback"
                    last_raw = raw
                else:
                    mode = "endpoint_offline" if exc.kind in ("timeout", "connection_error") else "live_error"

            record = {
                "attempt": attempt, "execution_mode": mode,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "usage": dict(self._usage), "finish_reason": self._finish_reason,
                "estimated_tokens": max(1, (len(current_prompt) + len(raw)) // 4),
                "error": error
            }

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

        envelope = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "endpoint": self.endpoint,
            "model": self.model_tag,
            "max_tokens": self.max_tokens,
            "max_retries": self.max_retries,
            "allow_simulation": sim_allowed,
            "execution_mode": mode,
            "is_simulated": simulated,
            "status": status,
            "attempts": attempts,
            "data": data
        }
        save_telemetry(envelope)
        return InferenceResult(envelope, raw_content=last_raw)

    def enforce_schema_and_quarantine(self, prompt: str, schema: Type[BaseModel]) -> InferenceResult:
        """Backward-compatible entry point forwarding directly to query()."""
        return self.query(prompt, schema=schema, allow_simulation=self.allow_simulation)

    def health(self, probe_live: bool = False, ttl: float = 15.0) -> HermesHealth:
        """Check Hermes health with live socket probing and thread-safe TTL caching."""
        with self._probe_lock:
            now = time.monotonic()
            if not probe_live and self._cached_health is not None and (now - self._cached_health_at < ttl):
                return self._cached_health

            # Read latest telemetry file snapshot
            saved_telemetry: Dict[str, Any] = {}
            target_file = Path(TELEMETRY_FILE)
            if target_file.exists():
                try:
                    with open(target_file, "r", encoding="utf-8") as f:
                        saved_telemetry = json.load(f)
                except Exception:
                    saved_telemetry = {}

            # Perform socket probe against /v1/models
            started = time.monotonic()
            reachable = False
            detail = "OK"
            models: List[str] = []
            try:
                models_url = self.get_models_url()
                req = urllib.request.Request(models_url, method="GET")
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        reachable = True
                        raw_body = resp.read(65536).decode("utf-8", errors="replace")
                        try:
                            data = json.loads(raw_body)
                            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                                models = [item["id"] for item in data["data"] if isinstance(item, dict) and "id" in item]
                        except Exception:
                            pass
                    else:
                        detail = f"HTTP {resp.status}"
            except Exception as exc:
                reachable = False
                detail = str(exc)

            latency_ms = str(round((time.monotonic() - started) * 1000))
            last_exec_mode = saved_telemetry.get("execution_mode", "untested")
            is_sim = saved_telemetry.get("is_simulated", False)
            last_status = saved_telemetry.get("status", "none")

            health_info = HermesHealth(
                reachable=reachable,
                models=models,
                state="connected" if reachable else "standby",
                latency_ms=latency_ms,
                live_probe_detail=detail,
                last_execution_mode=last_exec_mode,
                is_simulated=is_sim,
                last_status=last_status,
                max_tokens=saved_telemetry.get("max_tokens", self.max_tokens),
                max_retries=saved_telemetry.get("max_retries", self.max_retries),
                attempts=saved_telemetry.get("attempts", []),
                timestamp_utc=saved_telemetry.get("timestamp_utc", None),
                model=saved_telemetry.get("model", self.model_tag),
                endpoint=saved_telemetry.get("endpoint", self.endpoint),
                probe_running=self._probe_lock.locked(),
                server_pid=os.getpid(),
                build_id=os.environ.get("BUILD_ID", "1.58.8"),
                telemetry=saved_telemetry
            )
            self._cached_health = health_info
            self._cached_health_at = now
            return health_info


class FakeHermesAdapter:
    """Deterministic in-memory test double for Hermes model inference and health probing."""

    def __init__(self, canned_query_response: Optional[Any] = None,
                 is_reachable: bool = True, models: Optional[List[str]] = None,
                 canned_health: Optional[Dict[str, Any]] = None,
                 should_fail: bool = False, failure_exc: Optional[Exception] = None,
                 delay_s: float = 0.0):
        self.canned_query_response = canned_query_response
        self.is_reachable = is_reachable
        self.models = models or ["mock-hermes-4b"]
        self.canned_health = canned_health
        self.should_fail = should_fail
        self.failure_exc = failure_exc or RuntimeError("FakeHermesAdapter simulated failure")
        self.delay_s = delay_s
        self.calls: List[Dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def last_prompt(self) -> Optional[str]:
        return self.calls[-1].get("prompt") if self.calls else None

    def reset(self) -> None:
        self.calls.clear()

    def query(self, prompt: str, schema: Optional[Type[BaseModel]] = None,
              allow_simulation: bool = False) -> InferenceResult:
        if self.delay_s > 0:
            time.sleep(self.delay_s)
        self.calls.append({"method": "query", "prompt": prompt, "schema": schema, "allow_simulation": allow_simulation})
        if self.should_fail:
            raise self.failure_exc

        # Resolve response if a list of canned responses was supplied
        resp = self.canned_query_response
        if isinstance(resp, list):
            resp = resp.pop(0) if resp else "Empty canned queue"

        if schema is not None:
            if isinstance(resp, dict):
                try:
                    validated = schema.model_validate(resp)
                    parsed_data = validated.model_dump(mode="json")
                    return InferenceResult(
                        data=parsed_data,
                        status="validated_live",
                        raw_content=json.dumps(parsed_data),
                        is_simulated=False,
                        execution_mode="fake_hermes",
                        attempts=[{"attempt": 1, "outcome": "validated_live", "latency_ms": 1.0}]
                    )
                except ValidationError as err:
                    if allow_simulation:
                        sim_data = {"type": "simulated_event", "description": "SIMULATED: fake fallback"}
                        return InferenceResult(
                            data=sim_data,
                            status="validated_simulation",
                            raw_content=json.dumps(sim_data),
                            is_simulated=True,
                            execution_mode="simulated_fallback",
                            attempts=[{"attempt": 1, "outcome": "validated_simulation", "error": str(err)}]
                        )
                    return InferenceResult(
                        data=None,
                        status="quarantined",
                        raw_content=json.dumps(resp),
                        is_simulated=False,
                        execution_mode="fake_hermes",
                        error=str(err),
                        attempts=[{"attempt": 1, "outcome": "quarantined", "error": str(err)}]
                    )
            elif isinstance(resp, str):
                try:
                    validated = schema.model_validate_json(resp, strict=True)
                    parsed_data = validated.model_dump(mode="json")
                    return InferenceResult(
                        data=parsed_data,
                        status="validated_live",
                        raw_content=resp,
                        is_simulated=False,
                        execution_mode="fake_hermes",
                        attempts=[{"attempt": 1, "outcome": "validated_live", "latency_ms": 1.0}]
                    )
                except ValidationError as err:
                    return InferenceResult(
                        data=None,
                        status="quarantined",
                        raw_content=resp,
                        is_simulated=False,
                        execution_mode="fake_hermes",
                        error=str(err),
                        attempts=[{"attempt": 1, "outcome": "quarantined", "error": str(err)}]
                    )
            parsed_data = resp or {}
            return InferenceResult(
                data=parsed_data,
                status="validated_live",
                raw_content=json.dumps(parsed_data) if isinstance(parsed_data, dict) else str(parsed_data),
                is_simulated=False,
                execution_mode="fake_hermes",
                attempts=[{"attempt": 1, "outcome": "validated_live", "latency_ms": 1.0}]
            )

        raw = str(resp or "Fake text response")
        return InferenceResult(
            data=raw,
            status="completed",
            raw_content=raw,
            is_simulated=False,
            execution_mode="fake_hermes",
            attempts=[{"attempt": 1, "outcome": "completed", "latency_ms": 1.0}]
        )

    def health(self, probe_live: bool = False, ttl: float = 15.0) -> HermesHealth:
        if self.delay_s > 0:
            time.sleep(self.delay_s)
        self.calls.append({"method": "health", "probe_live": probe_live, "ttl": ttl})
        if self.should_fail:
            raise self.failure_exc
        if self.canned_health is not None:
            return HermesHealth(**self.canned_health)
        return HermesHealth(
            reachable=self.is_reachable,
            models=list(self.models),
            state="connected" if self.is_reachable else "standby",
            latency_ms="1.0",
            live_probe_detail="OK" if self.is_reachable else "Offline",
            last_status="validated_live" if self.is_reachable else "none",
            last_execution_mode="fake_hermes",
            is_simulated=False
        )

    def enforce_schema_and_quarantine(self, prompt: str, schema: Type[BaseModel]) -> InferenceResult:
        return self.query(prompt, schema=schema, allow_simulation=False)

    def call_local_server(self, prompt: str) -> str:
        res = self.query(prompt)
        return res.raw_content


HermesAdapter = LiveLocalModelAdapter

_DEFAULT_ADAPTER: Optional[LiveLocalModelAdapter] = None


def get_default_adapter() -> LiveLocalModelAdapter:
    """Retrieve the global default model adapter singleton."""
    global _DEFAULT_ADAPTER
    if _DEFAULT_ADAPTER is None:
        _DEFAULT_ADAPTER = LiveLocalModelAdapter()
    return _DEFAULT_ADAPTER


if __name__ == "__main__":
    event = {"type": "probe_test", "description": "Synthetic CLI probe", "reported_events": 1,
             "period": "TEST", "evidence_ids": ["cli-probe"]}
    result = LiveLocalModelAdapter().enforce_schema_and_quarantine(json.dumps(event), FailureEvent)
    print(json.dumps(result, indent=2))
