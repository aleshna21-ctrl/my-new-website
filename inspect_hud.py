import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)

LEDGER_PATH = Path(r"..\delivery-offline\job_ledger.db")
if not LEDGER_PATH.exists():
    LEDGER_PATH = BASE_DIR / "data" / "job_ledger.db"

OUTBOX_PATH = Path(r"..\notification-outbox\metadata_outbox.json")
if not OUTBOX_PATH.exists():
    OUTBOX_PATH = BASE_DIR / "data" / "metadata_outbox.json"

def inspect_hud_state():
    print("=== JEV Engine HUD & Ledger Inspection ===")
    
    if LEDGER_PATH.exists():
        print(f"\n[LEDGER] Inspecting {LEDGER_PATH} (Read-Only Mode):")
        try:
            conn = sqlite3.connect(f"file:{LEDGER_PATH.resolve()}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"  -> Tables found in ledger: {tables}")
            
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table});")
                cols = [col[1] for col in cursor.fetchall()]
                print(f"     * Table '{table}' columns: {cols}")
                
                try:
                    cursor.execute(f"SELECT * FROM {table} LIMIT 5;")
                    rows = cursor.fetchall()
                    print(f"       -> Sample rows ({len(rows)}):")
                    for r in rows:
                        print(f"          {r}")
                except Exception as ex:
                    print(f"       -> Could not query {table}: {ex}")
                
            conn.close()
        except Exception as e:
            print(f"  -> Error inspecting SQLite ledger: {e}")
    else:
        print(f"\n[LEDGER] Ledger not found at {LEDGER_PATH}")
        
    if OUTBOX_PATH.exists():
        print(f"\n[OUTBOX] Inspecting Metadata Diode Outbox ({OUTBOX_PATH}):")
        try:
            import json
            with open(OUTBOX_PATH, "r", encoding="utf-8") as f:
                events = json.load(f)
            print(f"  -> Total Diode Events Emitted: {len(events)}")
            for ev in events[-5:]:  # show last 5
                print(f"     * [{ev.get('timestamp_utc')}] Job: {ev.get('job_id')} ({ev.get('job_type')}) {ev.get('from_state')} -> {ev.get('to_state')}")
        except Exception as e:
            print(f"  -> Error reading metadata outbox: {e}")
    else:
        print(f"\n[OUTBOX] Metadata outbox not found at {OUTBOX_PATH}")

if __name__ == "__main__":
    inspect_hud_state()
