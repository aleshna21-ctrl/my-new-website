import os
import re
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Set

BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = r"C:\Users\alesh\jev-workspace\delivery-offline"
if not os.path.isdir(TARGET_DIR):
    TARGET_DIR = str(BASE_DIR / "data")
elif os.getcwd() != TARGET_DIR:
    try:
        os.chdir(TARGET_DIR)
    except Exception:
        pass

DB_FILE = os.path.join(TARGET_DIR, "job_ledger.db")
if not os.path.isfile(DB_FILE):
    DB_FILE = str(BASE_DIR / "data" / "job_ledger.db")

OUTBOX_FILE = r"C:\Users\alesh\jev-workspace\notification-outbox\metadata_outbox.json"
if not os.path.isfile(OUTBOX_FILE):
    OUTBOX_FILE = str(BASE_DIR / "data" / "metadata_outbox.json")

# Strict State Machine Transition Graph (Module 11 + Dynamic Inbox Intake + HOTL Ejection)
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "[ INBOX ]": {"queued", "running", "validated", "quarantined", "[ DONE ]", "[ STAGED / REVIEW ]", "[ NEEDS_REVIEW ]"},
    "inbox": {"queued", "running", "validated", "quarantined", "[ DONE ]", "[ STAGED / REVIEW ]", "[ NEEDS_REVIEW ]"},
    "queued": {"running", "quarantined", "[ NEEDS_REVIEW ]"},
    "running": {"validated", "quarantined", "[ DONE ]", "[ NEEDS_REVIEW ]"},
    "validated": {"approved", "completed", "quarantined", "[ NEEDS_REVIEW ]"},
    "approved": {"completed", "quarantined", "[ NEEDS_REVIEW ]"},
    "completed": set(),
    "[ DONE ]": set(),
    "[ STAGED / REVIEW ]": {"[ DONE ]", "[ NEEDS_REVIEW ]", "approved", "completed"},
    "[ NEEDS_REVIEW ]": {"queued", "running", "[ INBOX ]", "[ DONE ]", "quarantined", "approved"},
    "quarantined": {"queued"}
}

NOTIFY_STATES = {"validated", "approved", "completed", "quarantined", "[ NEEDS_REVIEW ]"}
SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def emit_sanitized_metadata_event(job_id: str, job_type: str, from_state: str, to_state: str) -> None:
    """
    One-Way Metadata Diode: Exports ONLY opaque state transition metadata.
    Never exports scope_id, financial amounts, or client strings.
    """
    if to_state not in NOTIFY_STATES:
        return
    if not SAFE_ID_PATTERN.match(job_id) or not SAFE_ID_PATTERN.match(job_type):
        raise ValueError("Security violation: Non-opaque identifier blocked from metadata diode.")

    os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
    events = []
    if os.path.exists(OUTBOX_FILE):
        try:
            with open(OUTBOX_FILE, "r", encoding="utf-8") as f:
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
    with open(OUTBOX_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)

def init_db() -> None:
    with sqlite3.connect(DB_FILE) as conn:
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
        # Ensure payload, model_output, assigned_role, and retry_count columns exist on jobs
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

def stage_to_buffer(job_id: str, assigned_agent: str, staged_payload: str, status: str = "STAGED") -> bool:
    """Stages a generated payload into staging_buffer for desktop agent pickup."""
    init_db()
    now = utc_now_iso()
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO staging_buffer (buffer_id, job_id, assigned_agent, staged_payload, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"buf-{job_id}", job_id, assigned_agent, staged_payload, status, now))
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            return False

def get_staging_buffer_item(job_id: str) -> Optional[dict]:
    """Retrieves staged payload by job_id from staging_buffer table."""
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM staging_buffer WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def log_telemetry_event(
    job_id: str,
    assigned_role: str,
    retry_count: int,
    event_type: str,
    payload: Optional[str] = None,
    error_trace: Optional[str] = None,
) -> bool:
    """Inserts a structured telemetry failure/routing event into telemetry_log."""
    init_db()
    now = utc_now_iso()
    log_id = f"telem-{job_id}-{int(time.time() * 1000)}"
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("""
                INSERT INTO telemetry_log (log_id, job_id, assigned_role, retry_count, event_type, payload, error_trace, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (log_id, job_id, assigned_role, retry_count, event_type, payload, error_trace, now))
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            return False

def get_telemetry_logs_for_job(job_id: str) -> list:
    """Retrieves all telemetry events for a given job_id."""
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM telemetry_log WHERE job_id = ? ORDER BY created_at ASC", (job_id,))
        return [dict(r) for r in cur.fetchall()]

def inject_inbox_job(
    job_id: str,
    scope_id: str,
    job_type: str,
    state: str = "[ INBOX ]",
    payload: Optional[str] = None,
    assigned_role: Optional[str] = None,
    retry_count: int = 0
) -> bool:
    """Injects an intake payload into the [ INBOX ] state of the ledger assigned to an agent."""
    init_db()
    now = utc_now_iso()
    role = assigned_role or scope_id or "aios-systems-architect"
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO jobs (
                    job_id, scope_id, job_type, state, attempt_count, created_at, updated_at,
                    payload, assigned_role, retry_count
                )
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """, (job_id, scope_id, job_type, state, now, now, payload, role, retry_count))
            success = (cursor.rowcount >= 1)
            conn.execute("COMMIT")
            return success
        except Exception:
            conn.execute("ROLLBACK")
            return False

def register_agent_state(
    agent_id: str,
    name: str,
    role: str,
    state: str = "active",
    capabilities: Optional[list] = None,
    meta: Optional[dict] = None
) -> bool:
    """Dynamically populates or updates active agent operational states in job_ledger.db."""
    init_db()
    now = utc_now_iso()
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("""
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

def get_active_agent_states() -> list:
    """Retrieves all dynamically registered agent states from job_ledger.db."""
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
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

def queue_job(job_id: str, scope_id: str, job_type: str) -> bool:
    init_db()
    now = utc_now_iso()
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, attempt_count, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', 0, ?, ?)
            """, (job_id, scope_id, job_type, now, now))
            success = (cursor.rowcount == 1)
            conn.execute("COMMIT")
            return success
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK")
            return False

def claim_job() -> Optional[str]:
    """Atomically claims the oldest queued job and verifies cursor.rowcount == 1."""
    init_db()
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("""
                SELECT job_id, job_type FROM jobs
                WHERE state = 'queued'
                ORDER BY created_at ASC LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                conn.execute("COMMIT")
                return None

            job_id = row["job_id"]
            now = utc_now_iso()
            cursor.execute("""
                UPDATE jobs
                SET state = 'running', attempt_count = attempt_count + 1, updated_at = ?
                WHERE job_id = ? AND state = 'queued'
            """, (now, job_id))

            if cursor.rowcount != 1:
                conn.execute("ROLLBACK")
                return None

            conn.execute("COMMIT")
            return job_id
        except Exception:
            conn.execute("ROLLBACK")
            raise

def update_job_state(job_id: str, new_state: str) -> bool:
    """Enforces VALID_TRANSITIONS and verifies conditional update rowcount == 1."""
    init_db()
    with sqlite3.connect(DB_FILE, isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            cursor.execute("SELECT state, job_type FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                conn.execute("ROLLBACK")
                raise KeyError(f"Job '{job_id}' does not exist in ledger.")

            current_state = row["state"]
            job_type = row["job_type"]
            allowed = VALID_TRANSITIONS.get(current_state, set())
            if new_state not in allowed:
                conn.execute("ROLLBACK")
                raise ValueError(
                    f"Illegal state transition for {job_id}: '{current_state}' -> '{new_state}'. "
                    f"Allowed transitions: {sorted(allowed)}"
                )

            now = utc_now_iso()
            cursor.execute("""
                UPDATE jobs
                SET state = ?, updated_at = ?
                WHERE job_id = ? AND state = ?
            """, (new_state, now, job_id, current_state))

            if cursor.rowcount != 1:
                conn.execute("ROLLBACK")
                raise RuntimeError(f"Concurrent state modification detected for job {job_id}.")

            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    emit_sanitized_metadata_event(job_id, job_type, current_state, new_state)
    return True

if __name__ == "__main__":
    print("\n--- Verifying Remediated SQLite Job Ledger ---")
    init_db()
    test_id = "job-strict-01"
    with sqlite3.connect(DB_FILE) as c:
        c.execute("DELETE FROM jobs WHERE job_id = ?", (test_id,))
        c.commit()

    assert queue_job(test_id, "sensitive-client-scope", "reconciliation") is True
    claimed = claim_job()
    assert claimed == test_id, "claim_job() failed to claim queued job"
    print(f"[PASS] Atomic claim_job() verified rowcount == 1 for: {claimed}")

    # Test illegal transition block (running -> completed skipping validated)
    try:
        update_job_state(test_id, "completed")
        raise AssertionError("Should have blocked illegal transition!")
    except ValueError as e:
        print(f"[PASS] Blocked illegal transition: {e}")

    # Test legal sequence: running -> validated -> approved -> completed
    update_job_state(test_id, "validated")
    update_job_state(test_id, "approved")
    update_job_state(test_id, "completed")
    print("[PASS] Enforced legal state sequence: running -> validated -> approved -> completed")
