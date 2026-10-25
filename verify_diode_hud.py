import os
import sqlite3
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

LEDGER_PATH = Path(r"..\delivery-offline\job_ledger.db")
if not LEDGER_PATH.exists():
    LEDGER_PATH = BASE_DIR / "data" / "job_ledger.db"

OUTBOX_PATH = Path(r"..\notification-outbox\metadata_outbox.json")
if not OUTBOX_PATH.exists():
    OUTBOX_PATH = BASE_DIR / "data" / "metadata_outbox.json"

def verify_diode_and_hud():
    print("=== JEV Engine Diode & HUD Verification ===")
    
    # 1. Verify Metadata Diode Integrity
    if OUTBOX_PATH.exists():
        with open(OUTBOX_PATH, "r", encoding="utf-8") as f:
            events = json.load(f)
        print(f"\n[DIODE CHECK] Total Events in Outbox: {len(events)}")
        
        allowed_keys = {
            "job_id", "job_type", "from_state", "to_state", "timestamp_utc",
            "event_id", "source_env", "dispatched_via_smtp", "requires_review"
        }
        
        for ev in events:
            actual_keys = set(ev.keys())
            assert actual_keys.issubset(allowed_keys), f"Diode event contains unauthorized keys: {actual_keys - allowed_keys}"
            
        print("[DIODE CHECK SUCCESS] All outbox events conform strictly to authorized metadata schema.")
    else:
        print("\n[DIODE CHECK] Outbox not found.")
        
    # 2. Verify HUD Read-Only Database Connection
    if LEDGER_PATH.exists():
        print(f"\n[HUD SERVER CHECK] Connecting to {LEDGER_PATH} in read-only mode (?mode=ro)...")
        conn = sqlite3.connect(f"file:{LEDGER_PATH.resolve()}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
        table_count = cur.fetchone()[0]
        conn.close()
        print(f"[HUD SERVER SUCCESS] Read-only inspection verified ({table_count} tables accessible).")
    else:
        print(f"\n[HUD SERVER CHECK] Ledger not found at {LEDGER_PATH}")

if __name__ == "__main__":
    verify_diode_and_hud()
