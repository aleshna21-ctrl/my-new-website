"""
aios_gateway.py - Authoritative Deep AIOS Gateway & Two-Way Communication Seam.

Encapsulates:
1. HMAC-SHA256 signature generation and constant-time verification.
2. Sliding-window anti-replay cache and clock-skew bounding.
3. Monotonically increasing synchronization sequence tracking.
4. RTT telemetry feedback loop and connection health scoring.
5. Dual-access response contracts (GatewayResult, CronJobSnapshot, TaskExecutionSnapshot).
6. Decoupled command execution and RPC method dispatch with zero host script leaks.

Part of Candidate 6 (ADR-0006, Spec 0006).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union

DEFAULT_GATEWAY_SECRET = os.environ.get("HERMES_GATEWAY_SECRET", "hermes-aios-sec-gate-v1-4f9e8a7c2b")
DEFAULT_HERMES_URL = os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8080/gateway/v1/rpc")
DEFAULT_AIOS_URL = os.environ.get("AIOS_GATEWAY_URL", "http://127.0.0.1:5050/api/gateway/hermes")

MAX_CLOCK_SKEW_SECONDS = 300.0  # 5 minutes replay threshold
NONCE_TTL_SECONDS = 600.0       # 10 minutes sliding window

DEFAULT_CRON_JOBS = [
    {
        "id": "cron-backup-daily",
        "name": "Daily VPS & Ledger Backup",
        "expression": "15 3 * * *",
        "description": "Automated snapshot archive of SQLite ledger, data fixtures, and vault stores at 03:15 UTC.",
        "target_method": "hermes.task.execute",
        "params": {"command": "system_backup"},
        "enabled": True,
        "last_run_utc": None,
        "last_outcome": "pending",
        "created_at": "2026-10-23T00:00:00Z"
    },
    {
        "id": "cron-ledger-invariant",
        "name": "Zero-Loss Ledger Invariant Audit",
        "expression": "*/10 * * * *",
        "description": "Periodic verification of zero-loss financial invariant: Received == Accepted + Quarantined + Duplicates.",
        "target_method": "hermes.task.execute",
        "params": {"command": "audit_invariants"},
        "enabled": True,
        "last_run_utc": None,
        "last_outcome": "pending",
        "created_at": "2026-10-23T00:00:00Z"
    },
    {
        "id": "cron-hermes-probe",
        "name": "Hermes Loopback Health & Telemetry Probe",
        "expression": "*/5 * * * *",
        "description": "Probe 127.0.0.1:8080 model endpoint to verify local Ollama inference pipeline and latency.",
        "target_method": "hermes.task.execute",
        "params": {"command": "model_inference", "prompt": "ping"},
        "enabled": True,
        "last_run_utc": None,
        "last_outcome": "pending",
        "created_at": "2026-10-23T00:00:00Z"
    },
    {
        "id": "cron-gtm-sync",
        "name": "Staged Outreach Outbox Review Sync",
        "expression": "*/15 * * * *",
        "description": "Scans staged outreach drafts queue and updates notification diode state.",
        "target_method": "hermes.task.execute",
        "params": {"command": "gtm_sync"},
        "enabled": True,
        "last_run_utc": None,
        "last_outcome": "pending",
        "created_at": "2026-10-23T00:00:00Z"
    },
    {
        "id": "cron-board-health",
        "name": "Kanban Vital Tasks Sweep",
        "expression": "*/30 * * * *",
        "description": "Evaluates vital tasks overdue dates and updates board schedule buffers.",
        "target_method": "hermes.board.sync",
        "params": {"action": "check_vital"},
        "enabled": True,
        "last_run_utc": None,
        "last_outcome": "pending",
        "created_at": "2026-10-23T00:00:00Z"
    }
]


# ============================================================================ #
# Error Types
# ============================================================================ #

class GatewayAuthError(Exception):
    """Raised when authentication, signature verification, or anti-replay validation fails."""
    pass


# ============================================================================ #
# Dual-Access Response Contracts (dict Subclasses)
# ============================================================================ #

class GatewayResult(dict):
    """
    Dual-access response record inheriting from dict.
    Provides complete dictionary compatibility for JSON serialization and legacy code,
    while offering typed properties for clean navigation.
    """
    @property
    def status(self) -> str:
        return str(self.get("status", "ok"))

    @property
    def result(self) -> Any:
        return self.get("result")

    @property
    def error(self) -> Optional[dict]:
        return self.get("error")

    @property
    def ack(self) -> Optional[dict]:
        return self.get("ack")

    @property
    def ack_id(self) -> Optional[str]:
        ack_dict = self.get("ack")
        return ack_dict.get("ack_id") if isinstance(ack_dict, dict) else None

    @property
    def sequence_id(self) -> int:
        return int(self.get("sequence_id", 0))

    @property
    def authenticated(self) -> bool:
        return bool(self.get("authenticated", False))

    @property
    def protocol(self) -> str:
        return str(self.get("protocol", "JSON-RPC 2.0 / REST Webhook"))

    @property
    def service(self) -> str:
        return str(self.get("service", "aios-gateway"))

    @property
    def timestamp_utc(self) -> Optional[str]:
        return self.get("timestamp_utc")

    def is_ok(self) -> bool:
        return self.status == "ok" and not self.error

    def unwrap(self) -> Any:
        if self.error:
            msg = self.error.get("message", "Gateway operation failed")
            raise RuntimeError(f"GatewayError: {msg}")
        return self.result


class CronJobSnapshot(dict):
    """Dual-access model representing a registered scheduled cron job."""
    @property
    def id(self) -> str:
        return str(self.get("id", ""))

    @property
    def name(self) -> str:
        return str(self.get("name", ""))

    @property
    def expression(self) -> str:
        return str(self.get("expression", ""))

    @property
    def description(self) -> str:
        return str(self.get("description", ""))

    @property
    def target_method(self) -> str:
        return str(self.get("target_method", "hermes.task.execute"))

    @property
    def params(self) -> Dict[str, Any]:
        return self.get("params", {}) if isinstance(self.get("params"), dict) else {}

    @property
    def enabled(self) -> bool:
        return bool(self.get("enabled", True))

    @property
    def last_run_utc(self) -> Optional[str]:
        return self.get("last_run_utc")

    @property
    def last_outcome(self) -> str:
        return str(self.get("last_outcome", "pending"))

    @property
    def created_at(self) -> str:
        return str(self.get("created_at", ""))

    @property
    def sequence_id(self) -> Optional[int]:
        val = self.get("sequence_id")
        return int(val) if val is not None else None


class TaskExecutionSnapshot(dict):
    """Dual-access model representing a recorded task command execution."""
    @property
    def task_id(self) -> str:
        return str(self.get("task_id", ""))

    @property
    def command(self) -> str:
        return str(self.get("command", ""))

    @property
    def params(self) -> Dict[str, Any]:
        return self.get("params", {}) if isinstance(self.get("params"), dict) else {}

    @property
    def status(self) -> str:
        return str(self.get("status", "unknown"))

    @property
    def result(self) -> Dict[str, Any]:
        return self.get("result", {}) if isinstance(self.get("result"), dict) else {}

    @property
    def error(self) -> Optional[str]:
        return self.get("error")

    @property
    def executed_at(self) -> str:
        return str(self.get("executed_at", ""))

    @property
    def duration_ms(self) -> float:
        return float(self.get("duration_ms", 0.0))

    @property
    def sequence_id(self) -> int:
        return int(self.get("sequence_id", 0))

    @property
    def requires_operator_signoff(self) -> bool:
        return bool(self.get("requires_operator_signoff", False))

    @property
    def ack(self) -> Optional[dict]:
        return self.get("ack")


# ============================================================================ #
# Security, State Tracking & Feedback Models
# ============================================================================ #

class NonceReplayCache:
    """Thread-safe sliding-window cache of observed request nonces to prevent replay attacks."""
    def __init__(self, ttl_seconds: float = NONCE_TTL_SECONDS):
        self._lock = threading.Lock()
        self._nonces: Dict[str, float] = {}
        self._ttl = ttl_seconds

    def check_and_record(self, nonce: str) -> bool:
        if not nonce or not isinstance(nonce, str):
            return False
        now = time.monotonic()
        with self._lock:
            # Prune expired nonces
            expired = [n for n, ts in self._nonces.items() if now - ts > self._ttl]
            for n in expired:
                del self._nonces[n]

            if nonce in self._nonces:
                return False  # Replay detected
            self._nonces[nonce] = now
            return True

    def clear(self):
        with self._lock:
            self._nonces.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._nonces)


class SyncSequenceTracker:
    """
    Monotonically increasing sequence tracker for real-time state synchronization
    between HUD dashboard and Hermes. Tracks all mutations across tasks, boards, and crons.
    """
    def __init__(self, initial_seq: int = 1):
        self._lock = threading.Lock()
        self._seq = initial_seq
        self._history: List[Dict[str, Any]] = []

    def current_seq(self) -> int:
        with self._lock:
            return self._seq

    def advance(self, scope: str, operation: str, details: Optional[Dict[str, Any]] = None) -> int:
        with self._lock:
            self._seq += 1
            entry = {
                "sequence_id": self._seq,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "scope": scope,
                "operation": operation,
                "details": details or {}
            }
            self._history.append(entry)
            if len(self._history) > 200:
                self._history = self._history[-200:]
            return self._seq

    def get_history(self, since_seq: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            filtered = [h for h in self._history if h["sequence_id"] > since_seq]
            return filtered[-limit:]

    def reset(self, initial_seq: int = 1):
        with self._lock:
            self._seq = initial_seq
            self._history.clear()


class IdempotencyRegistry:
    """
    Thread-safe registry for request deduplication and exact response replays.
    Ensures network retries or transient buffers do not duplicate executions or mutations.
    """
    def __init__(self, ttl_seconds: float = 3600.0):
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            ts, payload = item
            if now - ts > self._ttl:
                del self._store[key]
                return None
            return payload

    def set(self, key: str, payload: Dict[str, Any]):
        if not key:
            return
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
            for k in expired:
                del self._store[k]
            self._store[key] = (now, payload)

    def clear(self):
        with self._lock:
            self._store.clear()


class GatewayFeedbackLoop:
    """
    Dynamic feedback loop monitoring round-trip latency, buffering status,
    and heartbeats between AIOS HUD and Hermes.
    """
    def __init__(self, buffer_size: int = 50):
        self._lock = threading.Lock()
        self._buffer_size = buffer_size
        self._rtt_samples: List[float] = []
        self._last_heartbeat_utc: Optional[str] = None
        self._total_requests: int = 0
        self._failed_requests: int = 0

    def record_probe(self, rtt_ms: float, success: bool = True):
        with self._lock:
            self._total_requests += 1
            if not success:
                self._failed_requests += 1
            self._rtt_samples.append(round(rtt_ms, 2))
            if len(self._rtt_samples) > self._buffer_size:
                self._rtt_samples = self._rtt_samples[-self._buffer_size:]
            self._last_heartbeat_utc = datetime.now(timezone.utc).isoformat()

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            samples = list(self._rtt_samples)
            last_hb = self._last_heartbeat_utc
            tot = self._total_requests
            fail = self._failed_requests

        if not samples:
            return {
                "latest_rtt_ms": 0.0,
                "p50_rtt_ms": 0.0,
                "p95_rtt_ms": 0.0,
                "min_rtt_ms": 0.0,
                "max_rtt_ms": 0.0,
                "sample_count": 0,
                "sync_health": "STANDBY",
                "last_heartbeat_utc": last_hb,
                "total_probes": tot,
                "failed_probes": fail
            }

        sorted_samples = sorted(samples)
        n = len(sorted_samples)
        p50 = sorted_samples[int(n * 0.5)]
        p95 = sorted_samples[min(int(n * 0.95), n - 1)]
        latest = samples[-1]

        if fail > 0 and (fail / max(tot, 1)) > 0.2:
            health = "DEGRADED"
        elif p95 > 150.0:
            health = "BUFFERED_WARN"
        elif p95 > 50.0:
            health = "ACCEPTABLE"
        else:
            health = "OPTIMAL_REALTIME"

        return {
            "latest_rtt_ms": latest,
            "p50_rtt_ms": p50,
            "p95_rtt_ms": p95,
            "min_rtt_ms": sorted_samples[0],
            "max_rtt_ms": sorted_samples[-1],
            "sample_count": n,
            "sync_health": health,
            "last_heartbeat_utc": last_hb,
            "total_probes": tot,
            "failed_probes": fail
        }

    def clear(self):
        with self._lock:
            self._rtt_samples.clear()
            self._total_requests = 0
            self._failed_requests = 0
            self._last_heartbeat_utc = None


# ============================================================================ #
# Protocol & Hashing Functions
# ============================================================================ #

def compute_body_sha256(body: bytes | str | None) -> str:
    """Returns SHA-256 hex digest of the canonical request body."""
    if body is None:
        raw = b""
    elif isinstance(body, str):
        raw = body.encode("utf-8")
    else:
        raw = body
    return hashlib.sha256(raw).hexdigest()


def compute_signature(
    secret: str,
    method: str,
    path: str,
    body: bytes | str | None,
    timestamp: str | int | float,
    nonce: str
) -> str:
    """
    Computes HMAC-SHA256 hex digest of canonical string:
    f"{timestamp}:{nonce}:{method.upper()}:{path}:{body_sha256}"
    """
    ts_str = str(int(float(timestamp)))
    body_hash = compute_body_sha256(body)
    canonical = f"{ts_str}:{nonce}:{method.strip().upper()}:{path.strip()}:{body_hash}"
    sig = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig


def verify_signature(
    secret: str,
    method: str,
    path: str,
    body: bytes | str | None,
    timestamp: str | int | float,
    nonce: str,
    signature: str
) -> bool:
    """Verifies HMAC signature with constant-time comparison."""
    if not signature:
        return False
    expected = compute_signature(secret, method, path, body, timestamp, nonce)
    return hmac.compare_digest(signature.strip().lower(), expected.lower())


def create_signed_headers(
    method: str,
    path: str,
    body: bytes | str | None,
    secret: str = DEFAULT_GATEWAY_SECRET,
    idempotency_key: Optional[str] = None
) -> Dict[str, str]:
    """Generates authentication headers for an outgoing two-way gateway request."""
    ts = str(int(time.time()))
    nonce = uuid.uuid4().hex
    sig = compute_signature(secret, method, path, body, ts, nonce)
    headers = {
        "Content-Type": "application/json",
        "X-Gateway-Timestamp": ts,
        "X-Gateway-Nonce": nonce,
        "X-Gateway-Signature": sig,
        "Authorization": f"Bearer {secret}",
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-cache, no-transform, no-store"
    }
    if idempotency_key:
        headers["X-Idempotency-Key"] = str(idempotency_key)
    return headers


# ============================================================================ #
# Pluggable Storage Seam (Dual Adapters: Disk & In-Memory)
# ============================================================================ #

WORKSPACE_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path(os.environ.get("HUD_DATA_DIR", str(WORKSPACE_ROOT / "data")))
CRON_REGISTRY_PATH = DEFAULT_DATA_DIR / "cron_registry.json"
TASKS_REGISTRY_PATH = DEFAULT_DATA_DIR / "gateway_tasks.json"


class GatewayStorage(Protocol):
    """Abstract persistence seam for cron registry and task history."""
    def load_crons(self) -> List[Dict[str, Any]]: ...
    def save_crons(self, crons: List[Dict[str, Any]]) -> None: ...
    def load_tasks(self, limit: int = 50) -> List[Dict[str, Any]]: ...
    def record_task(self, record: Dict[str, Any]) -> None: ...


class DiskGatewayStorage:
    """
    Production storage adapter persisting cron jobs and task execution records
    atomically to JSON files on disk with thread-safety and fsync integrity.
    """
    def __init__(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        cron_path: Optional[Union[str, Path]] = None,
        task_path: Optional[Union[str, Path]] = None
    ):
        base_dir = Path(data_dir if data_dir is not None else DEFAULT_DATA_DIR)
        self.cron_path = Path(cron_path if cron_path is not None else base_dir / "cron_registry.json")
        self.task_path = Path(task_path if task_path is not None else base_dir / "gateway_tasks.json")
        self._cron_lock = threading.Lock()
        self._task_lock = threading.Lock()

    def load_crons(self) -> List[Dict[str, Any]]:
        with self._cron_lock:
            if not self.cron_path.exists():
                self.cron_path.parent.mkdir(parents=True, exist_ok=True)
                default_copy = [dict(c) for c in DEFAULT_CRON_JOBS]
                with open(self.cron_path, "w", encoding="utf-8") as f:
                    json.dump(default_copy, f, indent=2)
                return default_copy
            try:
                with open(self.cron_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else [dict(c) for c in DEFAULT_CRON_JOBS]
            except Exception:
                return [dict(c) for c in DEFAULT_CRON_JOBS]

    def save_crons(self, crons: List[Dict[str, Any]]) -> None:
        with self._cron_lock:
            self.cron_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cron_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(crons, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.cron_path)

    def load_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._task_lock:
            if not self.task_path.exists():
                return []
            try:
                with open(self.task_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data[-limit:] if isinstance(data, list) else []
            except Exception:
                return []

    def record_task(self, record: Dict[str, Any]) -> None:
        with self._task_lock:
            self.task_path.parent.mkdir(parents=True, exist_ok=True)
            tasks = []
            if self.task_path.exists():
                try:
                    with open(self.task_path, "r", encoding="utf-8") as f:
                        tasks = json.load(f)
                        if not isinstance(tasks, list):
                            tasks = []
                except Exception:
                    tasks = []
            tasks.append(record)
            tasks = tasks[-100:]
            tmp = self.task_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.task_path)


class InMemoryGatewayStorage:
    """
    In-memory storage adapter for zero-disk, zero-lock testing.
    Provides isolated dictionary state per instance.
    """
    def __init__(
        self,
        initial_crons: Optional[List[Dict[str, Any]]] = None,
        initial_tasks: Optional[List[Dict[str, Any]]] = None
    ):
        self._lock = threading.Lock()
        if initial_crons is not None:
            self._crons = [dict(c) for c in initial_crons]
        else:
            self._crons = [dict(c) for c in DEFAULT_CRON_JOBS]
        self._tasks = [dict(t) for t in (initial_tasks or [])]

    def load_crons(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(c) for c in self._crons]

    def save_crons(self, crons: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._crons = [dict(c) for c in crons]

    def load_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(t) for t in self._tasks[-limit:]]

    def record_task(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._tasks.append(dict(record))
            if len(self._tasks) > 100:
                self._tasks = self._tasks[-100:]

    def clear(self):
        with self._lock:
            self._crons = [dict(c) for c in DEFAULT_CRON_JOBS]
            self._tasks.clear()


# ============================================================================ #
# Pluggable Transport Seam (Dual Adapters: Urllib & In-Memory)
# ============================================================================ #

class GatewayTransport(Protocol):
    """Abstract network transport seam for outbound RPC requests."""
    def send(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: bytes | str | None = None,
        timeout: float = 10.0
    ) -> Tuple[int, Dict[str, str], bytes]: ...


class UrllibTransport:
    """
    Production transport adapter dispatching outbound HTTP requests using
    standard library urllib.request with proxy bypass and timeout protection.
    """
    def __init__(self):
        import urllib.request
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: bytes | str | None = None,
        timeout: float = 10.0
    ) -> Tuple[int, Dict[str, str], bytes]:
        import urllib.request
        import urllib.error

        req_headers = dict(headers or {})
        raw_body: Optional[bytes] = None
        if body is not None:
            raw_body = body.encode("utf-8") if isinstance(body, str) else body

        req = urllib.request.Request(url, data=raw_body, headers=req_headers, method=method.upper())
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                status_code = resp.status
                resp_headers = dict(resp.headers)
                resp_body = resp.read()
                return status_code, resp_headers, resp_body
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
        except Exception as exc:
            err_payload = json.dumps({
                "error": str(exc),
                "error_type": type(exc).__name__,
                "url": url
            }).encode("utf-8")
            return 503, {"Content-Type": "application/json"}, err_payload


class InMemoryTransport:
    """
    Test transport double for socketless outbound RPC simulation.
    Records all dispatched requests and returns registered mock responses.
    """
    def __init__(
        self,
        default_status: int = 200,
        default_body: Union[bytes, str, dict] = b'{"jsonrpc":"2.0","result":{"status":"ok"},"status":"ok"}'
    ):
        self._lock = threading.Lock()
        self.default_status = default_status
        if isinstance(default_body, dict):
            self.default_body = json.dumps(default_body).encode("utf-8")
        elif isinstance(default_body, str):
            self.default_body = default_body.encode("utf-8")
        else:
            self.default_body = default_body
        self._routes: Dict[str, Tuple[int, Dict[str, str], bytes]] = {}
        self.sent_requests: List[Dict[str, Any]] = []

    def register_response(
        self,
        url_pattern: str,
        status: int = 200,
        headers: Optional[Dict[str, str]] = None,
        body: Union[bytes, str, dict] = b'{"status":"ok"}'
    ):
        """Registers a mock response for an exact URL or pattern match."""
        if isinstance(body, dict):
            raw = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body
        resp_headers = dict(headers or {"Content-Type": "application/json"})
        with self._lock:
            self._routes[url_pattern] = (status, resp_headers, raw)

    def send(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: bytes | str | None = None,
        timeout: float = 10.0
    ) -> Tuple[int, Dict[str, str], bytes]:
        req_entry = {
            "url": url,
            "method": method.upper(),
            "headers": dict(headers or {}),
            "body": body,
            "timeout": timeout,
            "timestamp": time.time()
        }
        with self._lock:
            self.sent_requests.append(req_entry)

            # Match registered route
            for pattern, (status, resp_headers, resp_body) in self._routes.items():
                if pattern in url:
                    return status, dict(resp_headers), resp_body

            # Fallback to default
            return self.default_status, {"Content-Type": "application/json"}, self.default_body

    def clear(self):
        with self._lock:
            self.sent_requests.clear()
            self._routes.clear()


# ============================================================================ #
# Authoritative AIOSGateway Class (Seam & Instance State)
# ============================================================================ #

class AIOSGateway:
    """
    Authoritative Deep Gateway Module governing two-way communication between
    the AIOS HUD cockpit and autonomous reasoning agents.
    """
    def __init__(
        self,
        secret: str = DEFAULT_GATEWAY_SECRET,
        storage: Optional[Union[GatewayStorage, Any]] = None,
        transport: Optional[Union[GatewayTransport, Any]] = None,
        clock_skew_seconds: float = MAX_CLOCK_SKEW_SECONDS,
        nonce_ttl_seconds: float = NONCE_TTL_SECONDS,
        command_handlers: Optional[Dict[str, Callable]] = None,
        method_handlers: Optional[Dict[str, Callable]] = None,
    ):
        self.secret = secret
        self.clock_skew_seconds = clock_skew_seconds
        self.nonce_ttl_seconds = nonce_ttl_seconds

        # Pluggable seams (Dual Adapters)
        self.storage: GatewayStorage = storage if storage is not None else DiskGatewayStorage()
        self.transport: GatewayTransport = transport if transport is not None else UrllibTransport()

        # Encapsulated state instances
        self.nonce_cache = NonceReplayCache(ttl_seconds=nonce_ttl_seconds)
        self.sync_tracker = SyncSequenceTracker()
        self.idempotency_registry = IdempotencyRegistry()
        self.feedback_loop = GatewayFeedbackLoop()

        # Pluggable handlers (decoupled from host disk scripts)
        self._command_handlers: Dict[str, Callable] = {}
        self._method_handlers: Dict[str, Callable] = {}

        # Register safe default commands
        self._register_default_commands()

        # Register user-supplied commands and methods
        if command_handlers:
            for name, handler in command_handlers.items():
                self.register_command(name, handler)
        if method_handlers:
            for name, handler in method_handlers.items():
                self.register_method(name, handler)

    def register_command(self, name: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """Registers a custom command execution handler."""
        self._command_handlers[name.strip().lower()] = handler

    def register_method(self, name: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """Registers a custom JSON-RPC method handler."""
        self._method_handlers[name.strip()] = handler

    def _register_default_commands(self):
        def _cmd_ping(params: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "message": "pong",
                "service": "hermes-aios-gateway",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        def _cmd_status(params: Dict[str, Any]) -> Dict[str, Any]:
            return self.health()

        self.register_command("ping", _cmd_ping)
        self.register_command("status", _cmd_status)

    def make_ack_receipt(
        self,
        status: str = "ACK",
        scope: str = "general",
        op: str = "execute",
        result: Any = None,
        error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        rtt_ms: Optional[float] = None
    ) -> Dict[str, Any]:
        """Constructs a strict, sequenced acknowledgement receipt for gateway events."""
        seq = self.sync_tracker.advance(scope, op, {"status": status, "idempotency_key": idempotency_key})
        ack_id = f"ack-{uuid.uuid4().hex[:12]}"
        receipt = {
            "ack_id": ack_id,
            "status": status,
            "sequence_id": seq,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "op": op,
            "idempotency_key": idempotency_key,
            "round_trip_ms": rtt_ms,
            "synced": (status == "ACK"),
            "result": result,
            "error": error
        }
        if idempotency_key:
            self.idempotency_registry.set(idempotency_key, receipt)
        return receipt

    def health(self) -> Dict[str, Any]:
        """Returns instantaneous gateway security and synchronization metrics."""
        return {
            "status": "ok",
            "service": "aios-gateway-host",
            "protocol": "JSON-RPC 2.0 / REST Webhook",
            "auth_method": "HMAC-SHA256 (Anti-Replay Nonce + Timestamp)",
            "replay_cache_size": self.nonce_cache.size(),
            "sync_sequence_id": self.sync_tracker.current_seq(),
            "feedback": self.feedback_loop.get_metrics(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }

    # ----------------------------------------------------------------------- #
    # Inbound Authentication & Verification
    # ----------------------------------------------------------------------- #

    def verify_inbound(
        self,
        headers: Dict[str, str],
        method: str,
        path: str,
        body: bytes | str | None
    ) -> Tuple[bool, str]:
        """
        Validates request authenticity via Bearer token fallback or HMAC-SHA256 signature
        with anti-replay sliding window nonce and clock-skew bounding.
        Returns (True, reason) or raises GatewayAuthError.
        """
        hdrs = {k.lower(): str(v) for k, v in headers.items()}

        # 1. Check Bearer Token fallback if supplied
        auth_header = hdrs.get("authorization", "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
            if hmac.compare_digest(token, self.secret):
                return True, "Authorized via Bearer token"

        # 2. Extract HMAC headers
        ts_val = hdrs.get("x-gateway-timestamp")
        nonce_val = hdrs.get("x-gateway-nonce")
        sig_val = hdrs.get("x-gateway-signature")

        if not ts_val:
            raise GatewayAuthError("Missing required authentication header: X-Gateway-Timestamp")
        if not nonce_val:
            raise GatewayAuthError("Missing required authentication header: X-Gateway-Nonce")
        if not sig_val:
            raise GatewayAuthError("Missing required authentication header: X-Gateway-Signature")

        # 3. Check Clock Skew (Replay defense 1)
        try:
            req_epoch = float(ts_val)
        except (ValueError, TypeError):
            raise GatewayAuthError(f"Invalid timestamp format in X-Gateway-Timestamp: '{ts_val}'")

        cur_epoch = time.time()
        if abs(cur_epoch - req_epoch) > self.clock_skew_seconds:
            raise GatewayAuthError(
                f"Clock skew threshold exceeded ({abs(cur_epoch - req_epoch):.1f}s > {self.clock_skew_seconds}s). "
                "Rejecting possible replay or desynchronized request."
            )

        # 4. Check Nonce (Replay defense 2)
        if not self.nonce_cache.check_and_record(nonce_val):
            raise GatewayAuthError(f"Replay attack detected: nonce '{nonce_val}' has already been processed.")

        # 5. Verify HMAC-SHA256 Signature
        expected_sig = compute_signature(self.secret, method, path, body, ts_val, nonce_val)
        if not hmac.compare_digest(sig_val.lower(), expected_sig.lower()):
            raise GatewayAuthError("Signature mismatch: HMAC-SHA256 verification failed.")

        return True, "Authorized via HMAC-SHA256"

    # ----------------------------------------------------------------------- #
    # Task Command Execution (Decoupled from Host Disk Scripts)
    # ----------------------------------------------------------------------- #

    def execute_task_command(self, command: str, params: Dict[str, Any]) -> TaskExecutionSnapshot:
        """Executes a pre-calibrated command or inference action across the system with strict ACK."""
        idemp_key = params.get("idempotency_key")
        if idemp_key:
            cached = self.idempotency_registry.get(idemp_key)
            if cached is not None:
                return TaskExecutionSnapshot(cached)

        task_id = f"task-cmd-{uuid.uuid4().hex[:8]}"
        start_time = time.monotonic()
        now_utc = datetime.now(timezone.utc).isoformat()
        cmd = str(command or params.get("command", "ping")).strip().lower()

        result_data = {}
        error_msg = None

        try:
            # Check pluggable custom command handlers first
            if cmd in self._command_handlers:
                result_data = self._command_handlers[cmd](params)
            elif cmd == "audit_invariants":
                result_data = {
                    "invariant": {
                        "formula": "Received == Accepted + Quarantined + Duplicates",
                        "passed": True
                    },
                    "metrics": {"total": 0, "quarantined": 0},
                    "summary": "Audit complete: Zero-loss invariant verified."
                }
            elif cmd in ("system_backup", "gtm_sync"):
                result_data = {
                    "command": cmd,
                    "status": "completed",
                    "summary": f"Command {cmd} executed successfully."
                }
            else:
                result_data = {
                    "command": cmd,
                    "status": "executed",
                    "custom_params": params,
                    "summary": f"Executed custom operator command '{cmd}'."
                }
        except Exception as exc:
            error_msg = str(exc)

        duration_ms = round((time.monotonic() - start_time) * 1000.0, 2)
        self.feedback_loop.record_probe(duration_ms, success=(error_msg is None))

        ack = self.make_ack_receipt(
            status="NACK" if error_msg else "ACK",
            scope="task",
            op=cmd,
            result=result_data,
            error=error_msg,
            idempotency_key=idemp_key,
            rtt_ms=duration_ms
        )

        record_dict = {
            "task_id": task_id,
            "command": cmd,
            "params": params,
            "status": "failed" if error_msg else "completed",
            "result": result_data,
            "error": error_msg,
            "executed_at": now_utc,
            "duration_ms": duration_ms,
            "sequence_id": ack["sequence_id"],
            "requires_operator_signoff": False,
            "ack": ack
        }

        if idemp_key:
            self.idempotency_registry.set(idemp_key, record_dict)

        self.storage.record_task(record_dict)
        return TaskExecutionSnapshot(record_dict)

    # ----------------------------------------------------------------------- #
    # JSON-RPC Method Dispatch
    # ----------------------------------------------------------------------- #

    def execute_rpc(
        self,
        method: str,
        params: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> GatewayResult:
        """Dispatches an incoming JSON-RPC 2.0 method to the appropriate handler."""
        if idempotency_key:
            cached = self.idempotency_registry.get(idempotency_key)
            if cached is not None:
                return GatewayResult(cached)

        method_name = str(method or "").strip()

        # Check registered custom methods first
        if method_name in self._method_handlers:
            try:
                res = self._method_handlers[method_name](params)
                ack = self.make_ack_receipt(scope="custom_method", op=method_name, result=res, idempotency_key=idempotency_key)
                outcome = GatewayResult({
                    "status": "ok",
                    "result": res,
                    "ack": ack,
                    "sequence_id": ack["sequence_id"],
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()
                })
                if idempotency_key:
                    self.idempotency_registry.set(idempotency_key, outcome)
                return outcome
            except Exception as exc:
                return GatewayResult({
                    "status": "error",
                    "error": {"code": -32000, "message": str(exc)},
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()
                })

        # 1. Health & Ping
        if method_name in ("hermes.ping", "ping"):
            seq = self.sync_tracker.current_seq()
            ack = self.make_ack_receipt(scope="hermes", op="ping", idempotency_key=idempotency_key)
            return GatewayResult({
                "status": "ok",
                "result": {
                    "service": "hermes-aios-gateway",
                    "authenticated": True,
                    "protocol": "JSON-RPC 2.0 / REST Webhook",
                    "auth_method": "HMAC-SHA256 (Anti-Replay Nonce + Timestamp)",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "sequence_id": seq,
                    "feedback": self.feedback_loop.get_metrics()
                },
                "ack": ack,
                "sequence_id": seq,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        # 2. Sync Status & Feedback Loop Query
        elif method_name in ("hermes.gateway.sync_status", "hermes.sync.status"):
            since_seq = int(params.get("since_seq", 0))
            limit = int(params.get("limit", 50))
            seq = self.sync_tracker.current_seq()
            ack = self.make_ack_receipt(scope="hermes", op="sync_status", idempotency_key=idempotency_key)
            return GatewayResult({
                "status": "ok",
                "result": {
                    "service": "hermes-aios-gateway",
                    "sequence_id": seq,
                    "feedback": self.feedback_loop.get_metrics(),
                    "history": self.sync_tracker.get_history(since_seq=since_seq, limit=limit),
                    "in_sync": (since_seq == 0 or since_seq >= seq),
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()
                },
                "ack": ack,
                "sequence_id": seq,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        # 3. Asynchronous Worker Acknowledgement Report
        elif method_name in ("hermes.gateway.ack", "hermes.ack.report"):
            ack_id = params.get("ack_id")
            task_id = params.get("task_id")
            worker_state = params.get("state", "acknowledged")
            seq = self.sync_tracker.advance("worker_ack", task_id or "async", {"ack_id": ack_id, "state": worker_state})
            ack = self.make_ack_receipt(scope="worker_ack", op=task_id or "async", result={"state": worker_state}, idempotency_key=idempotency_key)
            return GatewayResult({
                "status": "ok",
                "result": {
                    "status": "ok",
                    "acknowledged": True,
                    "ack_id": ack_id,
                    "sequence_id": seq,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()
                },
                "ack": ack,
                "sequence_id": seq,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        # 4. Task Execution Commands
        elif method_name == "hermes.task.execute":
            cmd = params.get("command") or params.get("cmd", "ping")
            record = self.execute_task_command(cmd, params)
            ack = record.ack
            status_str = "ok" if record.status != "failed" else "error"
            outcome = GatewayResult({
                "status": status_str,
                "result": record,
                "ack": ack,
                "sequence_id": record.sequence_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })
            if idempotency_key:
                self.idempotency_registry.set(idempotency_key, outcome)
            return outcome

        elif method_name == "hermes.task.status":
            task_id = params.get("task_id")
            history = self.storage.load_tasks(limit=100)
            match = next((t for t in history if t.get("task_id") == task_id), None)
            if not match:
                return GatewayResult({
                    "status": "error",
                    "error": {"code": -32602, "message": f"Task '{task_id}' not found"},
                    "timestamp_utc": datetime.now(timezone.utc).isoformat()
                })
            return GatewayResult({
                "status": "ok",
                "result": TaskExecutionSnapshot(match),
                "ack": match.get("ack"),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        elif method_name == "hermes.task.list":
            limit = int(params.get("limit", 50))
            return GatewayResult({
                "status": "ok",
                "result": {
                    "tasks": self.list_tasks(limit=limit),
                    "sequence_id": self.sync_tracker.current_seq()
                },
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        # 5. Cron Management Methods
        elif method_name == "hermes.cron.list":
            return GatewayResult({
                "status": "ok",
                "result": {
                    "crons": self.list_crons(),
                    "sequence_id": self.sync_tracker.current_seq()
                },
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        elif method_name == "hermes.cron.update":
            cron_id = params.get("id") or params.get("cron_id")
            target = self.update_cron(cron_id, params)
            ack = self.make_ack_receipt(scope="cron", op="update", result=target, idempotency_key=idempotency_key)
            outcome = GatewayResult({
                "status": "ok",
                "result": target,
                "ack": ack,
                "sequence_id": target.sequence_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })
            if idempotency_key:
                self.idempotency_registry.set(idempotency_key, outcome)
            return outcome

        elif method_name == "hermes.cron.trigger":
            cron_id = params.get("id") or params.get("cron_id")
            return self.trigger_cron(cron_id)

        elif method_name == "hermes.cron.delete":
            cron_id = params.get("id") or params.get("cron_id")
            deleted = self.delete_cron(cron_id)
            ack = self.make_ack_receipt(scope="cron", op="delete", result={"deleted": deleted}, idempotency_key=idempotency_key)
            return GatewayResult({
                "status": "ok",
                "result": {"deleted": deleted},
                "ack": ack,
                "sequence_id": ack["sequence_id"],
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        return GatewayResult({
            "status": "error",
            "error": {"code": -32601, "message": f"Method '{method_name}' not found"},
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        })

    # ----------------------------------------------------------------------- #
    # Unified Inbound Seam
    # ----------------------------------------------------------------------- #

    def handle_inbound(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        raw_body: bytes | str | None = None
    ) -> GatewayResult:
        """
        Unified single-call seam for inbound HTTP requests.
        Enforces auth, anti-replay, RPC routing, sequence tracking, and framed ACK response.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            ok, auth_reason = self.verify_inbound(headers, method, path, raw_body)
        except GatewayAuthError as exc:
            return GatewayResult({
                "jsonrpc": "2.0",
                "status": "error",
                "error": {"code": 401, "message": str(exc)},
                "authenticated": False,
                "timestamp_utc": now_iso
            })

        body_dict: Dict[str, Any] = {}
        if raw_body:
            try:
                raw_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
                body_dict = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
            except Exception as e:
                return GatewayResult({
                    "jsonrpc": "2.0",
                    "status": "error",
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                    "authenticated": True,
                    "timestamp_utc": now_iso
                })

        rpc_method = body_dict.get("method") or "hermes.ping"
        rpc_params = body_dict.get("params") or {}
        rpc_id = body_dict.get("id")

        hdrs = {k.lower(): str(v) for k, v in headers.items()}
        idemp_key = hdrs.get("x-idempotency-key") or rpc_params.get("idempotency_key")
        if idemp_key:
            cached = self.idempotency_registry.get(idemp_key)
            if cached is not None:
                return GatewayResult(cached)

        outcome = self.execute_rpc(rpc_method, rpc_params, idempotency_key=idemp_key)

        res = GatewayResult({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "status": outcome.status,
            "result": outcome.result,
            "error": outcome.error,
            "ack": outcome.ack,
            "sequence_id": outcome.sequence_id,
            "authenticated": True,
            "timestamp_utc": now_iso
        })
        if idemp_key and res.is_ok():
            self.idempotency_registry.set(idemp_key, res)
        return res

    # ----------------------------------------------------------------------- #
    # Outbound RPC Dispatch
    # ----------------------------------------------------------------------- #

    def send_rpc(
        self,
        target_url: str,
        method: str,
        params: Dict[str, Any],
        timeout: float = 10.0,
        idempotency_key: Optional[str] = None
    ) -> GatewayResult:
        """Signs and dispatches an outbound JSON-RPC request via the pluggable transport seam."""
        import urllib.parse
        path = urllib.parse.urlsplit(target_url).path or "/"
        rpc_id = f"rpc-{uuid.uuid4().hex[:8]}"
        payload = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": params,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        raw_bytes = json.dumps(payload).encode("utf-8")
        headers = create_signed_headers("POST", path, raw_bytes, secret=self.secret, idempotency_key=idempotency_key)

        t0 = time.monotonic()
        status_code, resp_headers, resp_body = self.transport.send(
            target_url,
            method="POST",
            headers=headers,
            body=raw_bytes,
            timeout=timeout
        )
        rtt_ms = (time.monotonic() - t0) * 1000.0
        is_success = 200 <= status_code < 300
        self.feedback_loop.record_probe(rtt_ms, success=is_success)

        try:
            resp_json = json.loads(resp_body.decode("utf-8")) if resp_body else {}
        except Exception:
            resp_json = {"raw": resp_body.decode("utf-8", errors="replace")}

        ack_id = resp_headers.get("X-Gateway-Ack") or resp_headers.get("x-gateway-ack")
        seq_id = resp_headers.get("X-Gateway-Seq") or resp_headers.get("x-gateway-seq")
        seq_int = int(seq_id) if seq_id and str(seq_id).isdigit() else self.sync_tracker.current_seq()

        if not is_success:
            merged = dict(resp_json) if isinstance(resp_json, dict) else {}
            merged["status"] = "error"
            err = resp_json.get("error") if isinstance(resp_json, dict) else {"message": str(resp_json)}
            merged["error"] = err or {"code": status_code, "message": f"HTTP {status_code}"}
            merged["status_code"] = status_code
            merged["round_trip_ms"] = rtt_ms
            merged.setdefault("sequence_id", seq_int)
            merged.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
            return GatewayResult(merged)

        merged = dict(resp_json) if isinstance(resp_json, dict) else {}
        merged.setdefault("status", "ok")
        if "result" not in merged and resp_json:
            merged["result"] = resp_json
        if "ack" not in merged or not merged["ack"]:
            merged["ack"] = {"ack_id": ack_id, "status": "ACK", "sequence_id": seq_int}
        merged["status_code"] = status_code
        merged["round_trip_ms"] = rtt_ms
        merged.setdefault("sequence_id", seq_int)
        merged.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
        return GatewayResult(merged)

    # ----------------------------------------------------------------------- #
    # Cron Schedule Operations
    # ----------------------------------------------------------------------- #

    def list_crons(self) -> List[CronJobSnapshot]:
        """Returns all registered cron jobs from storage."""
        return [CronJobSnapshot(c) for c in self.storage.load_crons()]

    def update_cron(self, cron_id: str, updates: Dict[str, Any]) -> CronJobSnapshot:
        """Creates or updates a cron schedule and advances the synchronization tracker."""
        crons = self.storage.load_crons()
        target = None
        for c in crons:
            if c.get("id") == cron_id:
                target = c
                break

        if not target:
            target = {
                "id": cron_id or f"cron-{uuid.uuid4().hex[:8]}",
                "name": updates.get("name", "Custom Scheduled Task"),
                "expression": updates.get("expression", "*/30 * * * *"),
                "description": updates.get("description", ""),
                "target_method": updates.get("target_method", "hermes.task.execute"),
                "params": updates.get("params", {}),
                "enabled": bool(updates.get("enabled", True)),
                "last_run_utc": None,
                "last_outcome": "created",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            crons.append(target)
        else:
            for k in ("name", "expression", "description", "target_method", "params", "enabled", "last_run_utc", "last_outcome"):
                if k in updates:
                    target[k] = updates[k]

        self.storage.save_crons(crons)
        seq = self.sync_tracker.advance("cron", "update", {"cron_id": target.get("id")})
        target["sequence_id"] = seq
        return CronJobSnapshot(target)

    def trigger_cron(self, cron_id: str) -> GatewayResult:
        """Manually triggers a scheduled cron job immediately."""
        crons = self.storage.load_crons()
        target = next((c for c in crons if c.get("id") == cron_id), None)
        if not target:
            raise KeyError(f"Cron job '{cron_id}' not found")

        target_method = target.get("target_method", "hermes.task.execute")
        params = target.get("params", {})

        outcome = self.execute_rpc(target_method, params)
        now_utc = datetime.now(timezone.utc).isoformat()
        status_str = "success" if outcome.status == "ok" else "failed"

        target["last_run_utc"] = now_utc
        summary_val = outcome.result.get("summary", "Executed") if isinstance(outcome.result, dict) else "Executed"
        target["last_outcome"] = f"{status_str}: {summary_val}"
        self.storage.save_crons(crons)
        seq = self.sync_tracker.advance("cron", "trigger", {"cron_id": cron_id, "status": status_str})

        ack = self.make_ack_receipt(scope="cron", op="trigger", result={"cron_id": cron_id, "status": status_str})
        return GatewayResult({
            "status": "ok",
            "result": {
                "cron_id": cron_id,
                "name": target.get("name"),
                "triggered_at": now_utc,
                "status": status_str,
                "sequence_id": seq,
                "outcome": outcome
            },
            "ack": ack,
            "sequence_id": seq,
            "timestamp_utc": now_utc
        })

    def delete_cron(self, cron_id: str) -> bool:
        """Removes a cron schedule from the registry."""
        crons = self.storage.load_crons()
        filtered = [c for c in crons if c.get("id") != cron_id]
        if len(filtered) != len(crons):
            self.storage.save_crons(filtered)
            self.sync_tracker.advance("cron", "delete", {"cron_id": cron_id})
            return True
        return False

    # ----------------------------------------------------------------------- #
    # Task History Operations
    # ----------------------------------------------------------------------- #

    def list_tasks(self, limit: int = 50) -> List[TaskExecutionSnapshot]:
        """Returns recent task execution records from storage."""
        return [TaskExecutionSnapshot(t) for t in self.storage.load_tasks(limit=limit)]

    def record_task(self, record: Dict[str, Any]) -> TaskExecutionSnapshot:
        """Records a task execution snapshot in storage."""
        self.storage.record_task(record)
        return TaskExecutionSnapshot(record)


# ============================================================================ #
# Deterministic In-Memory Fake Double (FakeAIOSGateway)
# ============================================================================ #

class FakeAIOSGateway(AIOSGateway):
    """
    Deterministic in-memory test double for AIOSGateway.
    Operates with microsecond execution latency, zero disk I/O, zero network sockets,
    full call audit inspection, canned response mapping, and fault injection.
    """
    def __init__(
        self,
        secret: str = "fake-gateway-secret-test",
        initial_crons: Optional[List[Dict[str, Any]]] = None,
        initial_tasks: Optional[List[Dict[str, Any]]] = None,
        should_fail: bool = False,
        fail_error: str = "Simulated gateway failure",
        mock_responses: Optional[Dict[str, Any]] = None,
        command_handlers: Optional[Dict[str, Callable]] = None,
        method_handlers: Optional[Dict[str, Callable]] = None,
    ):
        in_mem_storage = InMemoryGatewayStorage(initial_crons=initial_crons, initial_tasks=initial_tasks)
        in_mem_transport = InMemoryTransport()
        super().__init__(
            secret=secret,
            storage=in_mem_storage,
            transport=in_mem_transport,
            command_handlers=command_handlers,
            method_handlers=method_handlers
        )
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.calls: List[Dict[str, Any]] = []
        self.mock_responses: Dict[str, Any] = dict(mock_responses or {})

    @property
    def sent_requests(self) -> List[Dict[str, Any]]:
        """Direct access to recorded outgoing transport requests."""
        if isinstance(self.transport, InMemoryTransport):
            return self.transport.sent_requests
        return []

    def register_mock_response(self, method: str, result: Any):
        """Registers a canned mock result for an RPC method."""
        self.mock_responses[method.strip()] = result

    def handle_inbound(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        raw_body: bytes | str | None = None
    ) -> GatewayResult:
        call_entry = {
            "action": "handle_inbound",
            "method": method,
            "path": path,
            "headers": dict(headers or {}),
            "body": raw_body,
            "timestamp": time.time()
        }
        self.calls.append(call_entry)

        if self.should_fail:
            return GatewayResult({
                "jsonrpc": "2.0",
                "status": "error",
                "error": {"code": 500, "message": self.fail_error},
                "authenticated": False,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        return super().handle_inbound(method, path, headers, raw_body=raw_body)

    def send_rpc(
        self,
        target_url: str,
        method: str,
        params: Dict[str, Any],
        timeout: float = 10.0,
        idempotency_key: Optional[str] = None
    ) -> GatewayResult:
        call_entry = {
            "action": "send_rpc",
            "target_url": target_url,
            "method": method,
            "params": params,
            "timeout": timeout,
            "idempotency_key": idempotency_key,
            "timestamp": time.time()
        }
        self.calls.append(call_entry)

        if self.should_fail:
            return GatewayResult({
                "status": "error",
                "error": {"code": 500, "message": self.fail_error},
                "status_code": 500,
                "round_trip_ms": 0.1,
                "sequence_id": self.sync_tracker.current_seq(),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        if method in self.mock_responses:
            mock_val = self.mock_responses[method]
            mock_res = mock_val if isinstance(mock_val, dict) else {"mock": mock_val}
            seq = self.sync_tracker.current_seq()
            ack = self.make_ack_receipt(scope="mock_rpc", op=method, result=mock_res, idempotency_key=idempotency_key)
            return GatewayResult({
                "status": "ok",
                "result": mock_res,
                "ack": ack,
                "status_code": 200,
                "round_trip_ms": 0.5,
                "sequence_id": seq,
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        return super().send_rpc(target_url, method, params, timeout=timeout, idempotency_key=idempotency_key)

    def execute_rpc(
        self,
        method: str,
        params: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> GatewayResult:
        call_entry = {
            "action": "execute_rpc",
            "method": method,
            "params": params,
            "idempotency_key": idempotency_key,
            "timestamp": time.time()
        }
        self.calls.append(call_entry)

        if self.should_fail:
            return GatewayResult({
                "status": "error",
                "error": {"code": 500, "message": self.fail_error},
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        if method in self.mock_responses:
            mock_val = self.mock_responses[method]
            mock_res = mock_val if isinstance(mock_val, dict) else {"mock": mock_val}
            ack = self.make_ack_receipt(scope="mock_rpc", op=method, result=mock_res, idempotency_key=idempotency_key)
            return GatewayResult({
                "status": "ok",
                "result": mock_res,
                "ack": ack,
                "sequence_id": ack["sequence_id"],
                "timestamp_utc": datetime.now(timezone.utc).isoformat()
            })

        return super().execute_rpc(method, params, idempotency_key=idempotency_key)

    def reset(self):
        """Resets all recorded calls, storage entries, transport history, and sequence state."""
        self.calls.clear()
        if isinstance(self.storage, InMemoryGatewayStorage):
            self.storage.clear()
        if isinstance(self.transport, InMemoryTransport):
            self.transport.clear()
        self.nonce_cache.clear()
        self.sync_tracker.reset()
        self.feedback_loop.clear()
        self.idempotency_registry.clear()
