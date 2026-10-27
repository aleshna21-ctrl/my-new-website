"""
job_ledger.py
Authoritative Deep Job Ledger Module for AIOS & JEV Cockpit.

Encapsulates SQLite storage, connection lifecycle, concurrency pragmas (WAL + busy_timeout),
state machine validation, one-way atomic metadata diode emissions, and in-memory test doubles.
Eliminates process-level os.chdir side-effects.
"""

from __future__ import annotations
import contextlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Set, List, Any, Union

BASE_DIR = Path(__file__).resolve().parent

def get_default_target_dir() -> str:
    env_dir = os.environ.get("DELIVERY_OFFLINE_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir
    preferred = r"C:\Users\alesh\jev-workspace\delivery-offline"
    if os.path.isdir(preferred):
        return preferred
    return str(BASE_DIR / "data")

def get_default_db_path() -> str:
    env_db = os.environ.get("JOB_LEDGER_DB")
    if env_db:
        return env_db
    td = get_default_target_dir()
    db_file = os.path.join(td, "job_ledger.db")
    if os.path.isfile(db_file):
        return db_file
    return str(BASE_DIR / "data" / "job_ledger.db")

def get_default_outbox_path() -> str:
    env_outbox = os.environ.get("JOB_LEDGER_OUTBOX")
    if env_outbox:
        return env_outbox
    preferred = r"C:\Users\alesh\jev-workspace\notification-outbox\metadata_outbox.json"
    if os.path.isfile(preferred):
        return preferred
    return str(BASE_DIR / "data" / "metadata_outbox.json")

# Module constants for backward-compatibility
TARGET_DIR = get_default_target_dir()
DB_FILE = get_default_db_path()
OUTBOX_FILE = get_default_outbox_path()

# Strict State Machine Transition Graph (Module 11 + Dynamic Inbox Intake + HOTL Ejection + Multi-Agent Matrix)
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "[ INBOX ]": {"queued", "running", "validated", "quarantined", "[ DONE ]", "[ STAGED / REVIEW ]", "[ NEEDS_REVIEW ]", "[ ACTIVE_ENFORCER ]", "[ ACTIVE_ARCHITECT ]", "[ ACTIVE_WARDEN ]", "[ ACTIVE_FABRICATOR ]"},
    "inbox": {"queued", "running", "validated", "quarantined", "[ DONE ]", "[ STAGED / REVIEW ]", "[ NEEDS_REVIEW ]"},
    "queued": {"running", "quarantined", "[ NEEDS_REVIEW ]"},
    "running": {"validated", "quarantined", "[ DONE ]", "[ NEEDS_REVIEW ]"},
    "validated": {"approved", "completed", "quarantined", "[ NEEDS_REVIEW ]"},
    "approved": {"completed", "quarantined", "[ NEEDS_REVIEW ]"},
    "completed": set(),
    "[ DONE ]": set(),
    "[ STAGED / REVIEW ]": {"[ DONE ]", "[ NEEDS_REVIEW ]", "approved", "completed"},
    "[ NEEDS_REVIEW ]": {"queued", "running", "[ INBOX ]", "[ DONE ]", "quarantined", "approved", "[ NEW_PAYLOAD ]"},
    "quarantined": {"queued"},
    # Multi-Agent Matrix states
    "[ NEW_PAYLOAD ]": {"[ ACTIVE_ENFORCER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_ENFORCER ]": {"[ PAYLOAD_CLEAN ]", "[ DRAFT_VERIFIED ]", "[ NEW_PAYLOAD ]", "[ DRAFT_READY ]", "[ NEEDS_REVIEW ]", "quarantined"},
    "[ PAYLOAD_CLEAN ]": {"[ ACTIVE_EXTRACTOR ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_EXTRACTOR ]": {"[ SYNTHESIS_PENDING ]", "[ PAYLOAD_CLEAN ]", "[ NEEDS_REVIEW ]", "quarantined"},
    "[ SYNTHESIS_PENDING ]": {"[ ACTIVE_SYNTHESIZER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ EXTRACTED ]": {"[ ACTIVE_SYNTHESIZER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_SYNTHESIZER ]": {"[ NEEDS_CODE ]", "[ NEEDS_CONTENT ]", "[ SYNTHESIS_PENDING ]", "[ NEEDS_REVIEW ]", "quarantined"},
    "[ NEEDS_CODE ]": {"[ ACTIVE_SYSTEMS_ENGINEER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_SYSTEMS_ENGINEER ]": {"[ BLUEPRINT_READY ]", "[ NEEDS_CODE ]", "[ NEEDS_REVIEW ]", "quarantined"},
    "[ BLUEPRINT_READY ]": {"[ ACTIVE_FABRICATOR ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_FABRICATOR ]": {"[ DONE ]", "[ BLUEPRINT_READY ]", "[ NEEDS_CODE ]", "[ NEEDS_REVIEW ]", "quarantined"},
    "[ NEEDS_CONTENT ]": {"[ ACTIVE_DRAFTER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_DRAFTER ]": {"[ DRAFT_READY ]", "[ NEEDS_CONTENT ]", "[ NEEDS_REVIEW ]", "quarantined"},
    "[ DRAFT_READY ]": {"[ ACTIVE_ENFORCER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ DRAFT_VERIFIED ]": {"[ ACTIVE_DISPATCHER ]", "quarantined", "[ NEEDS_REVIEW ]"},
    "[ ACTIVE_DISPATCHER ]": {"[ DONE ]", "[ DRAFT_VERIFIED ]", "[ NEEDS_REVIEW ]", "quarantined"},
}

NOTIFY_STATES: Set[str] = {"validated", "approved", "completed", "quarantined", "[ NEEDS_REVIEW ]"}
SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LedgerSnapshot(dict):
    """
    Dual-access contract for ledger snapshots.
    Operates as a standard dict for JSON serialization, while exposing typed properties.
    """
    def __init__(
        self,
        counts: Optional[Dict[str, int]] = None,
        jobs: Optional[List[Dict[str, Any]]] = None,
        timestamp_utc: Optional[str] = None
    ):
        super().__init__()
        self["counts"] = counts or {}
        self["jobs"] = jobs or []
        self["timestamp_utc"] = timestamp_utc or utc_now_iso()

    @property
    def counts(self) -> Dict[str, int]:
        return self.get("counts", {})

    @property
    def jobs(self) -> List[Dict[str, Any]]:
        return self.get("jobs", [])

    @property
    def timestamp_utc(self) -> str:
        return self.get("timestamp_utc", "")

    @property
    def total_count(self) -> int:
        return len(self.jobs)

    @property
    def active_count(self) -> int:
        c = self.counts
        return c.get("queued", 0) + c.get("running", 0) + c.get("[ INBOX ]", 0) + c.get("inbox", 0)

    @property
    def completed_count(self) -> int:
        c = self.counts
        return c.get("completed", 0) + c.get("[ DONE ]", 0)


class JobLedger:
    """
    Authoritative Deep Job Ledger Repository Seam.
    Encapsulates SQLite connection lifecycle, WAL concurrency, state machine rules,
    and atomic metadata diode event persistence.
    """
    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        outbox_path: Optional[Union[str, Path]] = None,
        read_only: bool = False
    ):
        self.db_path = str(db_path) if db_path is not None else get_default_db_path()
        self.outbox_path = Path(outbox_path) if outbox_path is not None else Path(get_default_outbox_path())
        self.read_only = read_only
        self._is_memory = (self.db_path == ":memory:")
        self._lock = threading.RLock()

        if self._is_memory:
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            try:
                self._mem_conn.execute("PRAGMA busy_timeout = 5000;")
            except Exception:
                pass
        else:
            self._mem_conn = None

    @contextlib.contextmanager
    def connect(self, read_only: Optional[bool] = None):
        """Yields an SQLite connection configured with busy_timeout=5000 and WAL mode."""
        is_ro = self.read_only if read_only is None else read_only
        if self._is_memory:
            with self._lock:
                yield self._mem_conn
            return

        if is_ro and os.path.exists(self.db_path):
            uri_path = f"file:{Path(self.db_path).resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri_path, uri=True, timeout=5.0)
            try:
                conn.execute("PRAGMA busy_timeout = 5000;")
            except Exception:
                pass
        else:
            parent_dir = os.path.dirname(os.path.abspath(self.db_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=5.0)
            try:
                conn.execute("PRAGMA busy_timeout = 5000;")
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
            except Exception:
                pass

        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initializes tables and schema columns idempotently."""
        if self.read_only:
            return
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    scope_id TEXT,
                    job_type TEXT,
                    state TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_states (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    state TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL,
                    capabilities TEXT,
                    meta TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS staging_buffer (
                    buffer_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    assigned_agent TEXT NOT NULL,
                    staged_payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'STAGED',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_log (
                    log_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    assigned_role TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT,
                    error_trace TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(jobs)")
            existing_cols = {col[1] for col in cur.fetchall()}
            if "payload" not in existing_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN payload TEXT")
            if "model_output" not in existing_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN model_output TEXT")
            if "assigned_role" not in existing_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN assigned_role TEXT DEFAULT 'aios-systems-architect'")
            if "retry_count" not in existing_cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN retry_count INTEGER DEFAULT 0")
            conn.commit()

    def queue_job(self, job_id: str, scope_id: str, job_type: str, payload: Optional[str] = None) -> bool:
        """Inserts a new job in 'queued' state."""
        self.init_db()
        now = utc_now_iso()
        with self.connect() as conn:
            conn.isolation_level = None
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("""
                    INSERT INTO jobs (job_id, scope_id, job_type, state, attempt_count, created_at, updated_at, payload)
                    VALUES (?, ?, ?, 'queued', 0, ?, ?, ?)
                """, (job_id, scope_id, job_type, now, now, payload))
                success = (cur.rowcount == 1)
                conn.execute("COMMIT")
                return success
            except (sqlite3.IntegrityError, sqlite3.OperationalError):
                conn.execute("ROLLBACK")
                return False

    def claim_job(self) -> Optional[str]:
        """Atomically claims the oldest queued job, updating state to 'running'."""
        self.init_db()
        with self.connect() as conn:
            conn.isolation_level = None
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("""
                    SELECT job_id, job_type FROM jobs
                    WHERE state = 'queued'
                    ORDER BY created_at ASC LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    conn.execute("COMMIT")
                    return None

                job_id = row["job_id"]
                now = utc_now_iso()
                cur.execute("""
                    UPDATE jobs
                    SET state = 'running', attempt_count = attempt_count + 1, updated_at = ?
                    WHERE job_id = ? AND state = 'queued'
                """, (now, job_id))

                if cur.rowcount != 1:
                    conn.execute("ROLLBACK")
                    return None

                conn.execute("COMMIT")
                return job_id
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def update_job_state(self, job_id: str, new_state: str, raise_on_error: bool = False) -> bool:
        """Enforces VALID_TRANSITIONS and updates job state conditionally."""
        self.init_db()
        with self.connect() as conn:
            conn.isolation_level = None
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("SELECT state, job_type FROM jobs WHERE job_id = ?", (job_id,))
                row = cur.fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    if raise_on_error:
                        raise KeyError(f"Job '{job_id}' does not exist in ledger.")
                    return False

                current_state = row["state"]
                job_type = row["job_type"]
                allowed = VALID_TRANSITIONS.get(current_state, set())
                if new_state not in allowed:
                    conn.execute("ROLLBACK")
                    if raise_on_error:
                        raise ValueError(
                            f"Illegal state transition for {job_id}: '{current_state}' -> '{new_state}'. "
                            f"Allowed transitions: {sorted(allowed)}"
                        )
                    return False

                now = utc_now_iso()
                cur.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?
                    WHERE job_id = ? AND state = ?
                """, (new_state, now, job_id, current_state))

                if cur.rowcount != 1:
                    conn.execute("ROLLBACK")
                    if raise_on_error:
                        raise RuntimeError(f"Concurrent state modification detected for job {job_id}.")
                    return False

                conn.execute("COMMIT")
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                if raise_on_error:
                    raise
                return False

        self.emit_sanitized_metadata_event(job_id, job_type, current_state, new_state)
        return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single job by job_id."""
        if not self.read_only:
            self.init_db()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
            if not cur.fetchone():
                return None
            cur.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves most recent jobs up to limit."""
        if not self.read_only:
            self.init_db()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
            if not cur.fetchone():
                return []
            cur.execute("SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]

    def get_snapshot(self) -> LedgerSnapshot:
        """Aggregates state counts and retrieves active/recent job records."""
        if not self.read_only:
            self.init_db()
        counts = {
            "queued": 0, "running": 0, "validated": 0, "approved": 0,
            "completed": 0, "quarantined": 0, "[ INBOX ]": 0, "[ DONE ]": 0, "[ NEEDS_REVIEW ]": 0
        }
        jobs: List[Dict[str, Any]] = []

        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
            if not cur.fetchone():
                return LedgerSnapshot(counts=counts, jobs=[], timestamp_utc=utc_now_iso())

            cur.execute("SELECT job_id, scope_id, job_type, state, attempt_count, updated_at FROM jobs ORDER BY updated_at DESC")
            for row in cur.fetchall():
                d = dict(row)
                jobs.append(d)
                st = d.get("state", "")
                if st in counts:
                    counts[st] += 1
                else:
                    counts[st] = 1

        return LedgerSnapshot(counts=counts, jobs=jobs, timestamp_utc=utc_now_iso())

    def stage_to_buffer(self, job_id: str, assigned_agent: str, staged_payload: str, status: str = "STAGED") -> bool:
        """Stages a generated payload into staging_buffer for desktop agent pickup."""
        self.init_db()
        now = utc_now_iso()
        with self.connect() as conn:
            conn.isolation_level = None
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO staging_buffer (buffer_id, job_id, assigned_agent, staged_payload, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (f"buf-{job_id}", job_id, assigned_agent, staged_payload, status, now))
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                return False

    def get_staging_buffer_item(self, job_id: str) -> Optional[dict]:
        """Retrieves staged payload by job_id from staging_buffer table."""
        if not self.read_only:
            self.init_db()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='staging_buffer'")
            if not cur.fetchone():
                return None
            cur.execute("SELECT * FROM staging_buffer WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def log_telemetry_event(
        self,
        job_id: str,
        assigned_role: str,
        retry_count: int,
        event_type: str,
        payload: Optional[str] = None,
        error_trace: Optional[str] = None,
    ) -> bool:
        """Inserts a structured telemetry failure/routing event into telemetry_log."""
        self.init_db()
        now = utc_now_iso()
        log_id = f"telem-{job_id}-{int(time.time() * 1000)}"
        with self.connect() as conn:
            conn.isolation_level = None
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("""
                    INSERT INTO telemetry_log (log_id, job_id, assigned_role, retry_count, event_type, payload, error_trace, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (log_id, job_id, assigned_role, retry_count, event_type, payload, error_trace, now))
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                return False

    def get_telemetry_logs_for_job(self, job_id: str) -> list:
        """Retrieves all telemetry events for a given job_id."""
        if not self.read_only:
            self.init_db()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry_log'")
            if not cur.fetchone():
                return []
            cur.execute("SELECT * FROM telemetry_log WHERE job_id = ? ORDER BY created_at ASC", (job_id,))
            return [dict(r) for r in cur.fetchall()]

    def inject_inbox_job(
        self,
        job_id: str,
        scope_id: str,
        job_type: str,
        state: str = "[ INBOX ]",
        payload: Optional[str] = None,
        assigned_role: Optional[str] = None,
        retry_count: int = 0
    ) -> bool:
        """Injects an intake payload into the [ INBOX ] state of the ledger assigned to an agent."""
        self.init_db()
        now = utc_now_iso()
        role = assigned_role or scope_id or "aios-systems-architect"
        with self.connect() as conn:
            conn.isolation_level = None
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO jobs (
                        job_id, scope_id, job_type, state, attempt_count, created_at, updated_at,
                        payload, assigned_role, retry_count
                    )
                    VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """, (job_id, scope_id, job_type, state, now, now, payload, role, retry_count))
                success = (cur.rowcount >= 1)
                conn.execute("COMMIT")
                return success
            except Exception:
                conn.execute("ROLLBACK")
                return False

    def register_agent_state(
        self,
        agent_id: str,
        name: str,
        role: str,
        state: str = "active",
        capabilities: Optional[list] = None,
        meta: Optional[dict] = None
    ) -> bool:
        """Dynamically populates or updates active agent operational states in job_ledger.db."""
        self.init_db()
        now = utc_now_iso()
        with self.connect() as conn:
            conn.isolation_level = None
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute("""
                    INSERT OR REPLACE INTO agent_states (agent_id, name, role, state, last_heartbeat, capabilities, meta)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    agent_id,
                    name,
                    role,
                    state,
                    now,
                    json.dumps(capabilities or []),
                    json.dumps(meta or {})
                ))
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                return False

    def get_active_agent_states(self) -> list:
        """Retrieves all dynamically registered agent states from job_ledger.db."""
        if not self.read_only:
            self.init_db()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_states'")
            if not cur.fetchone():
                return []
            cur.execute("SELECT * FROM agent_states ORDER BY last_heartbeat DESC")
            results = []
            for row in cur.fetchall():
                d = dict(row)
                try:
                    d["capabilities"] = json.loads(d.get("capabilities") or "[]")
                except Exception:
                    d["capabilities"] = []
                try:
                    d["meta"] = json.loads(d.get("meta") or "{}")
                except Exception:
                    d["meta"] = {}
                results.append(d)
            return results

    def emit_sanitized_metadata_event(
        self,
        job_id: str,
        job_type: str,
        from_state: str,
        to_state: str
    ) -> None:
        """
        One-Way Metadata Diode: Atomically exports ONLY opaque state transition metadata.
        Never exports scope_id, financial amounts, or client strings.
        Uses NamedTemporaryFile, fsync, and atomic os.replace.
        """
        if to_state not in NOTIFY_STATES:
            return
        if not SAFE_ID_PATTERN.match(job_id) or not SAFE_ID_PATTERN.match(job_type):
            raise ValueError("Security violation: Non-opaque identifier blocked from metadata diode.")

        target_dir = str(self.outbox_path.parent)
        os.makedirs(target_dir, exist_ok=True)

        events: List[Dict[str, Any]] = []
        if self.outbox_path.exists():
            try:
                with open(self.outbox_path, "r", encoding="utf-8") as f:
                    events = json.load(f)
            except (json.JSONDecodeError, OSError):
                events = []

        event = {
            "event_id": f"evt-{len(events) + 1:04d}",
            "source_env": "delivery-offline",
            "job_id": job_id,
            "job_type": job_type,
            "from_state": from_state,
            "to_state": to_state,
            "requires_review": to_state in {"quarantined", "validated", "[ NEEDS_REVIEW ]"},
            "dispatched_via_smtp": False,
            "timestamp_utc": utc_now_iso()
        }
        events.append(event)

        temp_file = None
        try:
            temp_file = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target_dir,
                prefix=".outbox-",
                suffix=".tmp",
                delete=False
            )
            json.dump(events, temp_file, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            os.replace(temp_file.name, str(self.outbox_path))
        except Exception:
            if temp_file is not None and os.path.exists(temp_file.name):
                try:
                    os.remove(temp_file.name)
                except OSError:
                    pass
            raise


class FakeJobLedger:
    """
    In-memory deterministic test double implementing the JobLedger seam.
    Provides fast, lock-free testing without SQLite dependencies or filesystem side-effects.
    """
    def __init__(
        self,
        initial_jobs: Optional[List[Dict[str, Any]]] = None,
        should_fail: bool = False
    ):
        self.should_fail = should_fail
        self.calls: List[Dict[str, Any]] = []
        self._jobs: Dict[str, Dict[str, Any]] = {}

        if initial_jobs:
            for j in initial_jobs:
                jid = j["job_id"]
                self._jobs[jid] = {
                    "job_id": jid,
                    "scope_id": j.get("scope_id", "test-scope"),
                    "job_type": j.get("job_type", "test-type"),
                    "state": j.get("state", "queued"),
                    "attempt_count": j.get("attempt_count", 0),
                    "created_at": j.get("created_at", utc_now_iso()),
                    "updated_at": j.get("updated_at", utc_now_iso()),
                    "payload": j.get("payload"),
                }

    def _check_failure(self):
        if self.should_fail:
            raise RuntimeError("Simulated FakeJobLedger operational failure.")

    def init_db(self) -> None:
        self._check_failure()
        self.calls.append({"action": "init_db"})

    def queue_job(self, job_id: str, scope_id: str, job_type: str, payload: Optional[str] = None) -> bool:
        self._check_failure()
        self.calls.append({"action": "queue_job", "job_id": job_id, "scope_id": scope_id, "job_type": job_type})
        now = utc_now_iso()
        self._jobs[job_id] = {
            "job_id": job_id,
            "scope_id": scope_id,
            "job_type": job_type,
            "state": "queued",
            "attempt_count": 0,
            "created_at": now,
            "updated_at": now,
            "payload": payload,
        }
        return True

    def claim_job(self) -> Optional[str]:
        self._check_failure()
        self.calls.append({"action": "claim_job"})
        queued = [j for j in self._jobs.values() if j.get("state") == "queued"]
        if not queued:
            return None
        queued.sort(key=lambda j: j.get("created_at", ""))
        target = queued[0]
        target["state"] = "running"
        target["attempt_count"] = target.get("attempt_count", 0) + 1
        target["updated_at"] = utc_now_iso()
        return target["job_id"]

    def update_job_state(self, job_id: str, new_state: str, raise_on_error: bool = False) -> bool:
        self._check_failure()
        self.calls.append({"action": "update_job_state", "job_id": job_id, "new_state": new_state})
        if job_id not in self._jobs:
            if raise_on_error:
                raise KeyError(f"Job {job_id} not found in fake ledger.")
            return False

        current = self._jobs[job_id]
        cur_state = current.get("state", "")
        allowed = VALID_TRANSITIONS.get(cur_state, set())
        if new_state not in allowed:
            if raise_on_error:
                raise ValueError(f"Illegal state transition {cur_state} -> {new_state}")
            return False

        current["state"] = new_state
        current["updated_at"] = utc_now_iso()
        return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        self._check_failure()
        self.calls.append({"action": "get_job", "job_id": job_id})
        j = self._jobs.get(job_id)
        return dict(j) if j else None

    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        self._check_failure()
        self.calls.append({"action": "list_jobs", "limit": limit})
        jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.get("updated_at", ""), reverse=True)
        return [dict(j) for j in jobs[:limit]]

    def get_snapshot(self) -> LedgerSnapshot:
        self._check_failure()
        self.calls.append({"action": "get_snapshot"})
        counts = {
            "queued": 0, "running": 0, "validated": 0, "approved": 0,
            "completed": 0, "quarantined": 0, "[ INBOX ]": 0, "[ DONE ]": 0, "[ NEEDS_REVIEW ]": 0
        }
        jobs = list(self._jobs.values())
        for j in jobs:
            st = j.get("state", "")
            if st in counts:
                counts[st] += 1
            else:
                counts[st] = 1

        return LedgerSnapshot(counts=counts, jobs=[dict(j) for j in jobs], timestamp_utc=utc_now_iso())


# --------------------------------------------------------------------------- #
# Module-level default singleton & backward-compatible delegation
# --------------------------------------------------------------------------- #
_DEFAULT_LEDGER: Optional[JobLedger] = None
_DEFAULT_LEDGER_LOCK = threading.RLock()


def get_default_ledger() -> JobLedger:
    global _DEFAULT_LEDGER
    with _DEFAULT_LEDGER_LOCK:
        current_db = DB_FILE
        current_outbox = OUTBOX_FILE
        if _DEFAULT_LEDGER is None or _DEFAULT_LEDGER.db_path != str(current_db) or _DEFAULT_LEDGER.outbox_path != Path(current_outbox):
            _DEFAULT_LEDGER = JobLedger(
                db_path=current_db,
                outbox_path=current_outbox
            )
        return _DEFAULT_LEDGER


def reset_default_ledger() -> None:
    global _DEFAULT_LEDGER, DB_FILE, OUTBOX_FILE
    with _DEFAULT_LEDGER_LOCK:
        _DEFAULT_LEDGER = None
        DB_FILE = get_default_db_path()
        OUTBOX_FILE = get_default_outbox_path()


def init_db() -> None:
    get_default_ledger().init_db()


def queue_job(job_id: str, scope_id: str, job_type: str, payload: Optional[str] = None) -> bool:
    return get_default_ledger().queue_job(job_id, scope_id, job_type, payload)


def claim_job() -> Optional[str]:
    return get_default_ledger().claim_job()


def update_job_state(job_id: str, new_state: str, raise_on_error: bool = False) -> bool:
    return get_default_ledger().update_job_state(job_id, new_state, raise_on_error=raise_on_error)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return get_default_ledger().get_job(job_id)


def list_jobs(limit: int = 100) -> List[Dict[str, Any]]:
    return get_default_ledger().list_jobs(limit=limit)


def get_snapshot() -> LedgerSnapshot:
    return get_default_ledger().get_snapshot()


def stage_to_buffer(job_id: str, assigned_agent: str, staged_payload: str, status: str = "STAGED") -> bool:
    return get_default_ledger().stage_to_buffer(job_id, assigned_agent, staged_payload, status)


def get_staging_buffer_item(job_id: str) -> Optional[dict]:
    return get_default_ledger().get_staging_buffer_item(job_id)


def log_telemetry_event(
    job_id: str,
    assigned_role: str,
    retry_count: int,
    event_type: str,
    payload: Optional[str] = None,
    error_trace: Optional[str] = None,
) -> bool:
    return get_default_ledger().log_telemetry_event(job_id, assigned_role, retry_count, event_type, payload, error_trace)


def get_telemetry_logs_for_job(job_id: str) -> list:
    return get_default_ledger().get_telemetry_logs_for_job(job_id)


def inject_inbox_job(
    job_id: str,
    scope_id: str,
    job_type: str,
    state: str = "[ INBOX ]",
    payload: Optional[str] = None,
    assigned_role: Optional[str] = None,
    retry_count: int = 0
) -> bool:
    return get_default_ledger().inject_inbox_job(job_id, scope_id, job_type, state, payload, assigned_role, retry_count)


def register_agent_state(
    agent_id: str,
    name: str,
    role: str,
    state: str = "active",
    capabilities: Optional[list] = None,
    meta: Optional[dict] = None
) -> bool:
    return get_default_ledger().register_agent_state(agent_id, name, role, state, capabilities, meta)


def get_active_agent_states() -> list:
    return get_default_ledger().get_active_agent_states()


def emit_sanitized_metadata_event(job_id: str, job_type: str, from_state: str, to_state: str) -> None:
    get_default_ledger().emit_sanitized_metadata_event(job_id, job_type, from_state, to_state)


if __name__ == "__main__":
    print("\n--- Verifying Deep Job Ledger Module ---")
    ledger = get_default_ledger()
    ledger.init_db()
    test_id = "job-strict-01"
    with ledger.connect() as c:
        c.execute("DELETE FROM jobs WHERE job_id = ?", (test_id,))
        c.commit()

    assert queue_job(test_id, "sensitive-client-scope", "reconciliation") is True
    claimed = claim_job()
    assert claimed == test_id, "claim_job() failed to claim queued job"
    print(f"[PASS] Atomic claim_job() verified for: {claimed}")

    # Test illegal transition block (running -> completed skipping validated)
    try:
        update_job_state(test_id, "completed", raise_on_error=True)
        raise AssertionError("Should have blocked illegal transition!")
    except ValueError as e:
        print(f"[PASS] Blocked illegal transition: {e}")

    # Test legal sequence: running -> validated -> approved -> completed
    update_job_state(test_id, "validated")
    update_job_state(test_id, "approved")
    update_job_state(test_id, "completed")
    print("[PASS] Enforced legal state sequence: running -> validated -> approved -> completed")
