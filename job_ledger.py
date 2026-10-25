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

# Strict State Machine Transition Graph (Module 11)
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "queued": {"running", "quarantined"},
    "running": {"validated", "quarantined"},
    "validated": {"approved", "completed", "quarantined"},
    "approved": {"completed", "quarantined"},
    "completed": set(),
    "quarantined": {"queued"}
}

NOTIFY_STATES = {"validated", "approved", "completed", "quarantined"}
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
        "requires_review": to_state in {"quarantined", "validated"},
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
        conn.commit()

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
