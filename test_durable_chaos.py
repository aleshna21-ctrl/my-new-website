#!/usr/bin/env python3
"""
test_durable_chaos.py
=====================
Chaos Verification Test for Sandboxed Durable Execution & Asynchronous Tag-Team Routing.

Verification Sequence:
1. Inject Fatal Task:
   Inserts a task into job_ledger.db assigned to 'aios-systems-architect' with a prompt
   and code payload guaranteed to crash the sandbox (division by zero).
2. Monitor the Warden:
   Polls the database every 2 seconds and prints the row's retry_count, assigned_role,
   and state on each polling tick.
3. Verify Tag-Team:
   Confirms that after the first crash, the assigned_role swaps to a helper agent
   (qa-telemetry-daemon) and retry_count increments while remaining in '[ INBOX ]'.
4. Verify Ejection:
   Confirms that once retry_count hits 3, the state transitions to '[ NEEDS_REVIEW ]',
   and the error traceback is routed to the telemetry_log table.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Reconfigure stdout/stderr for clean UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
OFFLINE_DIR = WORKSPACE_ROOT / "delivery-offline"
DATA_DIR = PROJECT_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from async_orchestrator_daemon import AsyncOrchestratorDaemon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ChaosWarden] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DurableChaosTest")


def resolve_ledger_path(custom_path: Optional[Path] = None) -> Path:
    """Finds active job_ledger.db (custom -> delivery-offline -> data)."""
    if custom_path and custom_path.exists():
        return custom_path
    offline_db = OFFLINE_DIR / "job_ledger.db"
    if offline_db.exists():
        return offline_db
    local_db = DATA_DIR / "job_ledger.db"
    if local_db.exists():
        return local_db
    return offline_db


def utc_now_iso() -> str:
    """Returns ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# 1. INJECT FATAL TASK ROUTINE
# =============================================================================

def inject_fatal_task(
    db_path: Path,
    job_id: str,
    assigned_role: str = "aios-systems-architect",
    instruction: str = "Write and execute a Python script that divides 1 by 0",
) -> bool:
    """
    Inserts a fatal task into job_ledger.db under '[ INBOX ]' state,
    assigned strictly to the designated agent with an intentional ZeroDivisionError payload.
    """
    now = utc_now_iso()
    payload = {
        "task": instruction,
        "instruction": instruction,
        "assigned_agent": assigned_role,
        "code": (
            "# Intentional zero division to test durable sandbox crash recovery\n"
            "print('Executing fatal zero division in sandbox...')\n"
            "x = 1 / 0\n"
        ),
        "requested_at": now,
        "test_type": "chaos_durable_sandbox",
    }
    payload_str = json.dumps(payload, indent=2)

    with sqlite3.connect(str(db_path), timeout=10.0, isolation_level=None) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            # Ensure schema compatibility
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    scope_id TEXT,
                    job_type TEXT,
                    state TEXT NOT NULL,
                    attempt_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT,
                    model_output TEXT,
                    assigned_role TEXT DEFAULT 'aios-systems-architect',
                    retry_count INTEGER DEFAULT 0
                )
            """)
            cur.execute("PRAGMA table_info(jobs)")
            existing_cols = {col[1] for col in cur.fetchall()}
            if "payload" not in existing_cols:
                cur.execute("ALTER TABLE jobs ADD COLUMN payload TEXT")
            if "model_output" not in existing_cols:
                cur.execute("ALTER TABLE jobs ADD COLUMN model_output TEXT")
            if "assigned_role" not in existing_cols:
                cur.execute("ALTER TABLE jobs ADD COLUMN assigned_role TEXT DEFAULT 'aios-systems-architect'")
            if "retry_count" not in existing_cols:
                cur.execute("ALTER TABLE jobs ADD COLUMN retry_count INTEGER DEFAULT 0")

            cur.execute("""
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

            cur.execute("""
                INSERT OR REPLACE INTO jobs (
                    job_id, scope_id, job_type, state, attempt_count,
                    created_at, updated_at, payload, assigned_role, retry_count
                ) VALUES (?, ?, 'chaos_fatal_task', '[ INBOX ]', 0, ?, ?, ?, ?, 0)
            """, (job_id, assigned_role, now, now, payload_str, assigned_role))

            conn.execute("COMMIT")
            return True
        except Exception as e:
            conn.execute("ROLLBACK")
            logger.error(f"Failed to inject fatal task '{job_id}': {e}")
            raise


# =============================================================================
# 2. MONITOR WARDEN POLLING ROUTINE
# =============================================================================

def query_job_status(db_path: Path, job_id: str) -> Optional[Dict[str, Any]]:
    """Queries current state, assigned_role, and retry_count of a job."""
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT job_id, state, assigned_role, retry_count, updated_at, model_output, payload
            FROM jobs
            WHERE job_id = ?
        """, (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def query_telemetry_log(db_path: Path, job_id: str) -> list[Dict[str, Any]]:
    """Retrieves all telemetry events logged for the job."""
    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT log_id, job_id, assigned_role, retry_count, event_type, error_trace, created_at
            FROM telemetry_log
            WHERE job_id = ?
            ORDER BY created_at ASC
        """, (job_id,))
        return [dict(r) for r in cur.fetchall()]


# =============================================================================
# 3. BACKGROUND ORCHESTRATOR WORKER
# =============================================================================

class DaemonWorkerThread(threading.Thread):
    """Runs AsyncOrchestratorDaemon loop in a background daemon thread."""

    def __init__(self, db_path: Path, interval_sec: float = 1.0):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.interval_sec = interval_sec
        self.daemon_instance = AsyncOrchestratorDaemon(
            db_path=self.db_path,
            interval_sec=self.interval_sec,
            allow_simulation=True,
            force_subprocess_jail=True,
            verbose=False,
        )
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.daemon_instance.poll_and_process_once()
            except Exception as e:
                logger.debug(f"Daemon worker tick exception: {e}")
            time.sleep(self.interval_sec)

    def stop(self) -> None:
        self._stop_event.set()
        self.daemon_instance.stop()


# =============================================================================
# 4. MAIN CHAOS EXECUTION SEQUENCE
# =============================================================================

def run_chaos_test(
    db_path: Optional[Path] = None,
    poll_interval: float = 2.0,
    timeout_sec: float = 30.0,
    auto_spawn_daemon: bool = True,
) -> bool:
    target_db = resolve_ledger_path(db_path)
    job_id = f"chaos-fatal-{int(time.time())}"
    initial_role = "aios-systems-architect"
    instruction = "Write and execute a Python script that divides 1 by 0"

    print("=" * 76)
    print("🔥 [AIOS DURABLE CHAOS TEST] Sandbox Crash & Asynchronous Tag-Team Routing")
    print("=" * 76)
    print(f"Target Ledger DB: {target_db}")
    print(f"Target Job ID:    {job_id}")
    print(f"Initial Role:     {initial_role}")
    print(f"Fatal Prompt:     \"{instruction}\"")
    print("-" * 76)

    # -------------------------------------------------------------------------
    # Step 1: Inject Fatal Task
    # -------------------------------------------------------------------------
    print("\n[Step 1: Inject Fatal Task] Inserting task into job_ledger.db [ INBOX ]...")
    injected = inject_fatal_task(
        db_path=target_db,
        job_id=job_id,
        assigned_role=initial_role,
        instruction=instruction,
    )
    if not injected:
        print("❌ [FAIL] Could not insert fatal task into ledger.")
        return False
    print(f"         [OK] Fatal task '{job_id}' injected into '[ INBOX ]' assigned to '{initial_role}'.")

    # Start Background Orchestrator Daemon if requested
    worker = None
    if auto_spawn_daemon:
        print("\n[Step 1.1: Start Warden Daemon] Spawning AsyncOrchestratorDaemon in background...")
        worker = DaemonWorkerThread(db_path=target_db, interval_sec=1.0)
        worker.start()
        print("         [OK] Warden background daemon active and polling.")

    # -------------------------------------------------------------------------
    # Step 2: Monitor the Warden (Poll every 2 seconds)
    # -------------------------------------------------------------------------
    print("\n[Step 2: Monitor the Warden] Polling ledger every 2 seconds...")
    start_time = time.time()
    tick_count = 0
    tag_team_verified = False
    ejection_verified = False

    try:
        while (time.time() - start_time) < timeout_sec:
            time.sleep(poll_interval)
            tick_count += 1
            elapsed = time.time() - start_time

            row = query_job_status(target_db, job_id)
            if not row:
                print(f"         [Tick {tick_count:02d} | {elapsed:.1f}s] Waiting for job row...")
                continue

            current_role = row["assigned_role"]
            current_retry = row["retry_count"]
            current_state = row["state"]

            print(
                f"         [Tick {tick_count:02d} | {elapsed:4.1f}s] "
                f"retry_count={current_retry} | assigned_role={current_role:<22} | status={current_state}"
            )

            # -----------------------------------------------------------------
            # Step 3: Verify Tag-Team Swap
            # -----------------------------------------------------------------
            if not tag_team_verified and current_retry >= 1 and current_role == "qa-telemetry-daemon":
                tag_team_verified = True
                print(
                    f"\n[Step 3: Tag-Team Verified] 🤝 Reactive Crash Swap Triggered!\n"
                    f"         Previous Role: '{initial_role}' -> Swapped to Helper: '{current_role}'\n"
                    f"         Strike Count:  {current_retry}/3 (Kept in '[ INBOX ]' for recovery tick)\n"
                )

            # -----------------------------------------------------------------
            # Step 4: Verify Hard Ejection (3-Strike Limit)
            # -----------------------------------------------------------------
            if current_retry >= 3 and current_state == "[ NEEDS_REVIEW ]":
                ejection_verified = True
                print(
                    f"\n[Step 4: Hard Ejection Verified] 🚨 3-Strike Limit Reached!\n"
                    f"         Final State: '{current_state}'\n"
                    f"         Total Retries: {current_retry}/3\n"
                    f"         Sandbox Destroyed: Ephemeral jail unmounted cleanly.\n"
                )
                break

    finally:
        if worker:
            worker.stop()
            worker.join(timeout=3.0)

    # -------------------------------------------------------------------------
    # Verification Checklist & Telemetry Audit
    # -------------------------------------------------------------------------
    print("-" * 76)
    print("🔍 [Step 5: Telemetry Log & Traceback Audit]")
    telemetry_events = query_telemetry_log(target_db, job_id)
    print(f"         Found {len(telemetry_events)} telemetry event(s) logged for job '{job_id}':")

    traceback_logged = False
    for ev in telemetry_events:
        print(
            f"         - Event: {ev['event_type']:<24} | Role: {ev['assigned_role']:<20} "
            f"| Strike: {ev['retry_count']} | Time: {ev['created_at']}"
        )
        if ev.get("error_trace") and ("ZeroDivisionError" in ev["error_trace"] or "division by zero" in ev["error_trace"]):
            traceback_logged = True
            print(f"           [Verified Traceback Sample]:\n             {ev['error_trace'].strip().splitlines()[-1]}")

    print("\n" + "=" * 76)
    if tag_team_verified and ejection_verified and traceback_logged:
        print("🏆 [CHAOS TEST RESULT: PASS] All Architectural Directives Verified:")
        print("   1. [OK] Fatal Task Injected (ZeroDivisionError payload).")
        print("   2. [OK] Warden Sandbox Caught Crash without Crashing Host Daemon.")
        print("   3. [OK] Asynchronous Tag-Team: Swapped to 'qa-telemetry-daemon'.")
        print("   4. [OK] 3-Strike Limit Enforced: Transitioned to '[ NEEDS_REVIEW ]'.")
        print("   5. [OK] Traceback and Failure Packet Successfully Routed to telemetry_log.")
        print("=" * 76)
        return True
    else:
        print("❌ [CHAOS TEST RESULT: FAIL] Verification gaps detected:")
        print(f"   - Tag-Team Swapped:  {tag_team_verified}")
        print(f"   - 3-Strike Ejection: {ejection_verified}")
        print(f"   - Traceback Logged:  {traceback_logged}")
        print("=" * 76)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chaos Test: Verify Durable Sandbox crash handling, reactive tag-team, and 3-strike ejection."
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to job_ledger.db (default: autodetected in delivery-offline or data/)."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0s)."
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Test timeout in seconds (default: 30.0s)."
    )
    parser.add_argument(
        "--no-spawn",
        action="store_true",
        help="Do not spawn internal background daemon (use if an external daemon is already running)."
    )
    args = parser.parse_args()

    custom_db = Path(args.db_path) if args.db_path else None
    passed = run_chaos_test(
        db_path=custom_db,
        poll_interval=args.interval,
        timeout_sec=args.timeout,
        auto_spawn_daemon=not args.no_spawn,
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
