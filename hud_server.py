import os
import csv
import json
import sqlite3
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from collections import deque
from typing import Dict, Any, List, Optional
import sys
import socket
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

from hud.type_safe_router import (
    GLOBAL_OBSERVABILITY, RealTimeVisualizationEngine, TypeSafeRouter
)
from data_contracts import (
    StreamingSeriesResponse, CortexHierarchyPayload, SQLiteLedgerPayload,
    EncoreObservabilityMetrics
)


PROBE_LOCK = threading.Lock()
BUILD_ID = 'strict-probe-aligned-v1'
SERVER_STARTED = time.time()

# Strict policy for the AI OS dashboard page: no inline script/style, same-origin only.
OS_PAGE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
               "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

HUD_DIR = os.environ.get("HUD_DIR", os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.environ.get("JEV_PROJECT_ROOT", os.path.dirname(HUD_DIR))
OFFLINE_DIR = os.path.join(ROOT_DIR, "delivery-offline")
GTM_DIR = os.path.join(ROOT_DIR, "gtm-research")
OUTBOX_DIR = os.path.join(ROOT_DIR, "notification-outbox")

if HUD_DIR not in sys.path or sys.path[0] != HUD_DIR:
    sys.path.insert(0, HUD_DIR)
for p in (OFFLINE_DIR, GTM_DIR):
    if p not in sys.path:
        sys.path.append(p)

def _load_env_file(path: str):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

_load_env_file(os.path.join(HUD_DIR, ".env"))
_load_env_file(os.path.join(ROOT_DIR, ".env"))

def get_hermes_endpoint() -> str:
    return os.environ.get("HERMES_ENDPOINT", "http://127.0.0.1:8080/v1/chat/completions")

def get_hermes_model() -> str:
    return os.environ.get("HERMES_MODEL", "qwen3:4b")

def get_hermes_base_url() -> str:
    gw_url = os.environ.get("HERMES_GATEWAY_URL", "")
    if gw_url:
        try:
            u = urllib.parse.urlsplit(gw_url)
            return f"{u.scheme}://{u.netloc}"
        except Exception:
            pass
    endpoint = get_hermes_endpoint()
    try:
        u = urllib.parse.urlsplit(endpoint)
        return f"{u.scheme}://{u.netloc}"
    except Exception:
        return "http://127.0.0.1:8080"

def get_hermes_gateway_rpc_url() -> str:
    return os.environ.get("HERMES_GATEWAY_URL", f"{get_hermes_base_url()}/gateway/v1/rpc")

def get_hermes_gateway_health_url() -> str:
    return f"{get_hermes_base_url()}/gateway/v1/health"

def get_hermes_agent_url() -> str:
    return os.environ.get("HERMES_AGENT_URL", "http://127.0.0.1:32768")

def get_hermes_models_url() -> str:
    endpoint = get_hermes_endpoint()
    try:
        url = urllib.parse.urlsplit(endpoint)
        path = url.path
        if path.endswith("/chat/completions"):
            base_path = path[:-len("/chat/completions")]
            models_path = f"{base_path}/models"
        else:
            models_path = "/v1/models"
        return f"{url.scheme}://{url.netloc}{models_path}"
    except Exception:
        return f"{get_hermes_base_url()}/v1/models"

def probe_hermes_live() -> dict:
    url = get_hermes_models_url()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=1.5) as resp:
            return {"reachable": resp.status == 200, "http_status": resp.status}
    except Exception as e:
        return {"reachable": False, "error": str(e)}

def get_hermes_telemetry() -> dict:
    live = probe_hermes_live()
    t_file = os.path.join(OFFLINE_DIR, "inference_telemetry.json")
    hud_file = os.path.join(HUD_DIR, "inference_telemetry.json")
    if os.path.exists(hud_file):
        if not os.path.exists(t_file) or os.path.getmtime(hud_file) >= os.path.getmtime(t_file):
            t_file = hud_file
    saved = {}
    if os.path.exists(t_file):
        try:
            with open(t_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = {}
    exec_mode = saved.get("execution_mode", "untested")
    is_sim = saved.get("is_simulated", False)
    return {
        "live_loopback_reachable": live["reachable"],
        "live_probe_detail": live.get("error", "OK"),
        "last_execution_mode": exec_mode,
        "is_simulated": is_sim,
        "last_status": saved.get("status", "none"),
        "max_tokens": saved.get("max_tokens", 2048),
        "max_retries": saved.get("max_retries", 1),
        "attempts": saved.get("attempts", []),
        "timestamp_utc": saved.get("timestamp_utc", None),
        "model": saved.get("model", get_hermes_model()),
        "endpoint": saved.get("endpoint", get_hermes_endpoint()),
        "probe_running": PROBE_LOCK.locked(),
        "server_pid": os.getpid(),
        "build_id": BUILD_ID
    }

def get_db_path() -> str:
    db_path = os.path.join(OFFLINE_DIR, "job_ledger.db")
    if not os.path.exists(db_path):
        fallback_db = os.path.join(HUD_DIR, "data", "job_ledger.db")
        if os.path.exists(fallback_db):
            db_path = fallback_db
    return db_path

def get_adversarial_csv_path() -> str:
    csv_path = os.path.join(OFFLINE_DIR, "adversarial_fixture.csv")
    if not os.path.exists(csv_path):
        fallback_csv = os.path.join(HUD_DIR, "data", "adversarial_fixture.csv")
        if os.path.exists(fallback_csv):
            csv_path = fallback_csv
    return csv_path

def get_quarantine_data() -> dict:
    csv_path = get_adversarial_csv_path()
    rows = []
    metrics = {"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0}
    seen = set()
    quarantined_samples = []

    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = [name.strip() if name else name for name in (reader.fieldnames or [])]
            for idx, raw_row in enumerate(reader, start=1):
                clean_row = {k.strip(): (v or "").strip() for k, v in raw_row.items() if k}
                metrics["received"] += 1
                inv_id = clean_row.get("InvoiceID", "")
                amt_str = clean_row.get("Amount", "")
                dt_str = clean_row.get("Date", "")
                is_dup = inv_id in seen
                is_malformed = False
                reason = None
                status = "accepted"

                if is_dup:
                    metrics["duplicates"] += 1
                    status = "duplicate"
                    reason = f"Duplicate InvoiceID ({inv_id})"
                elif not inv_id:
                    metrics["quarantined"] += 1
                    status = "quarantined"
                    is_malformed = True
                    reason = "Missing InvoiceID"
                elif not amt_str:
                    metrics["quarantined"] += 1
                    status = "quarantined"
                    is_malformed = True
                    reason = "Missing Amount"
                elif amt_str.startswith("-"):
                    metrics["quarantined"] += 1
                    status = "quarantined"
                    is_malformed = True
                    reason = f"Negative StrictStr amount ({amt_str})"
                elif not amt_str.replace(".", "", 1).isdigit():
                    metrics["quarantined"] += 1
                    status = "quarantined"
                    is_malformed = True
                    reason = f"Non-numeric amount string ({amt_str})"
                else:
                    parts = amt_str.split(".")
                    if len(parts) == 2 and len(parts[1]) > 2:
                        metrics["quarantined"] += 1
                        status = "quarantined"
                        is_malformed = True
                        reason = f"Sub-penny fractional precision ({amt_str}, {len(parts[1])} decimal places)"
                    else:
                        seen.add(inv_id)
                        metrics["accepted"] += 1

                row_dict = {
                    "row_idx": idx,
                    "row": idx,
                    "invoice_id": inv_id or "MISSING",
                    "amount": amt_str,
                    "raw_amount": amt_str,
                    "date": dt_str,
                    "status": status,
                    "is_malformed": is_malformed,
                    "reason": reason
                }
                rows.append(row_dict)
                if status == "quarantined":
                    quarantined_samples.append(row_dict)

    invariant_ok = (metrics["received"] == (metrics["accepted"] + metrics["quarantined"] + metrics["duplicates"]))
    return {
        "fixture": os.path.basename(csv_path),
        "path": csv_path,
        "metrics": metrics,
        "invariant": {
            "passed": invariant_ok,
            "formula": f"{metrics['received']} == {metrics['accepted']} + {metrics['quarantined']} + {metrics['duplicates']}",
            "metrics": metrics,
            "quarantined_samples": quarantined_samples[:10]
        },
        "rows": rows
    }

def repair_quarantine_row(row_idx: int = 0, invoice_id: str = None, amount: str = None, date: str = None,
                          auto_recover: bool = False, auto_recover_all: bool = False) -> dict:
    csv_path = get_adversarial_csv_path()
    if not os.path.exists(csv_path):
        return {"error": f"Fixture file not found at {csv_path}", "status": "error"}

    orig_path = csv_path + ".original"
    if not os.path.exists(orig_path):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as src, open(orig_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        except Exception:
            pass

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = list(csv.reader(f))

    if not reader:
        return {"error": "Empty CSV fixture", "status": "error"}

    header = reader[0]
    data_rows = reader[1:]
    repaired_records = []

    if auto_recover_all:
        seen = set()
        for idx, r in enumerate(data_rows, start=1):
            if len(r) >= 2:
                inv = r[0].strip()
                amt = r[1].strip()
                # Clean malformed/negative/sub-penny amount
                if amt.startswith("-") or not amt.replace(".", "", 1).isdigit() or (len(amt.split(".")) == 2 and len(amt.split(".")[1]) > 2):
                    cleaned_amt = amt.lstrip("-").strip()
                    if cleaned_amt.replace(".", "", 1).isdigit():
                        parts = cleaned_amt.split(".")
                        if len(parts) == 2 and len(parts[1]) > 2:
                            cleaned_amt = f"{parts[0]}.{parts[1][:2]}"
                        elif len(parts) == 1:
                            cleaned_amt = f"{parts[0]}.00"
                        r[1] = cleaned_amt
                        repaired_records.append({"row_idx": idx, "invoice_id": inv, "repaired_amount": cleaned_amt})
                if inv in seen:
                    fixed_inv = f"{inv}-REC"
                    r[0] = fixed_inv
                    repaired_records.append({"row_idx": idx, "repaired_invoice_id": fixed_inv})
                else:
                    seen.add(inv)
    else:
        if row_idx < 1 or row_idx > len(data_rows):
            return {"error": f"Row index {row_idx} out of range (1..{len(data_rows)})", "status": "error"}

        target_row = data_rows[row_idx - 1]
        cur_inv = target_row[0].strip() if len(target_row) >= 1 else ""
        cur_amt = target_row[1].strip() if len(target_row) >= 2 else ""

        if auto_recover:
            cleaned_amt = cur_amt.lstrip("-").strip()
            if cleaned_amt.replace(".", "", 1).isdigit():
                parts = cleaned_amt.split(".")
                if len(parts) == 2 and len(parts[1]) > 2:
                    cleaned_amt = f"{parts[0]}.{parts[1][:2]}"
                elif len(parts) == 1:
                    cleaned_amt = f"{parts[0]}.00"
            else:
                cleaned_amt = "0.00"
            target_row[1] = cleaned_amt
            repaired_records.append({"row_idx": row_idx, "invoice_id": cur_inv, "repaired_amount": cleaned_amt})
        else:
            if invoice_id is not None:
                target_row[0] = str(invoice_id).strip()
            if amount is not None:
                amt_str = str(amount).strip()
                if not amt_str.replace(".", "", 1).isdigit() or amt_str.startswith("-"):
                    return {"error": f"Invalid StrictStr amount '{amt_str}'. Must be a positive decimal.", "status": "error"}
                target_row[1] = amt_str
            if date is not None and len(target_row) >= 3:
                target_row[2] = str(date).strip()

            repaired_records.append({
                "row_idx": row_idx,
                "invoice_id": target_row[0],
                "amount": target_row[1],
                "date": target_row[2] if len(target_row) >= 3 else ""
            })

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    other_path = os.path.join(HUD_DIR, "data", "adversarial_fixture.csv")
    if os.path.abspath(other_path) != os.path.abspath(csv_path) and os.path.exists(other_path):
        try:
            with open(csv_path, "r", encoding="utf-8") as src, open(other_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        except Exception:
            pass

    updated = get_quarantine_data()
    return {
        "status": "ok",
        "repaired_records": repaired_records,
        "metrics": updated["metrics"],
        "invariant": updated["invariant"],
        "quarantined_count": updated["metrics"]["quarantined"],
        "duplicates_count": updated["metrics"]["duplicates"],
        "rows": updated["rows"]
    }

def reset_quarantine_fixture() -> dict:
    csv_path = get_adversarial_csv_path()
    orig_path = csv_path + ".original"
    baseline_text = (
        "InvoiceID,Amount ,Date\n"
        "INV-3250-VTFZ,173.51,2026-04-25\n"
        "INV-2772-UOKV,105.78,2026-07-16\n"
        "INV-7401-WQWB,242.75,2026-10-05\n"
        "INV-9783-WNNC,46,2026-02-10\n"
        "INV-2059-IYIG,226.74,2026-03-09\n"
        "INV-5960-WCJS,206.3,2026-05-25\n"
        "INV-8931-WZNB,330.66,2026-06-26\n"
        "INV-3083-MRUI,267.23,2026-04-21\n"
        "INV-2337-OTPK,202.48,2026-01-18\n"
        "INV-7234-GIXD,121.38,2026-09-03\n"
        "INV-2059-IYIG,226.74,2026-03-09\n"
        "INV-4459-QZJZ,-999.995,2026-05-16\n"
    )
    content = baseline_text
    if os.path.exists(orig_path):
        try:
            with open(orig_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            content = baseline_text

    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(content)

    other_path = os.path.join(HUD_DIR, "data", "adversarial_fixture.csv")
    if os.path.abspath(other_path) != os.path.abspath(csv_path) and os.path.exists(other_path):
        try:
            with open(other_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    return {
        "status": "ok",
        "message": "Reset adversarial_fixture.csv to baseline state",
        "data": get_quarantine_data()
    }

def get_offline_ledger_and_invariant() -> dict:
    counts = {"queued": 0, "running": 0, "validated": 0, "approved": 0, "completed": 0, "quarantined": 0}
    jobs = []
    db_path = get_db_path()
    if os.path.exists(db_path):
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT job_id, job_type, state, attempt_count, updated_at FROM jobs ORDER BY updated_at DESC")
                for row in cur.fetchall():
                    d = dict(row)
                    jobs.append(d)
                    st = d.get("state", "")
                    if st in counts:
                        counts[st] += 1
        except Exception:
            pass

    q_data = get_quarantine_data()
    return {
        "counts": counts,
        "jobs": jobs,
        "invariant": q_data["invariant"]
    }

def get_gtm_queue() -> dict:
    stage_path = os.path.join(GTM_DIR, "staged_outreach.json")
    if not os.path.exists(stage_path):
        fallback_stage = os.path.join(HUD_DIR, "data", "staged_outreach.json")
        if os.path.exists(fallback_stage):
            stage_path = fallback_stage
    drafts = []
    if os.path.exists(stage_path):
        try:
            with open(stage_path, "r", encoding="utf-8") as f:
                drafts = json.load(f)
        except Exception:
            drafts = []
    return {
        "total": len(drafts),
        "needs_review": sum(1 for d in drafts if d.get("status") == "needs_review"),
        "approved": sum(1 for d in drafts if d.get("status") == "approved"),
        "rejected": sum(1 for d in drafts if d.get("status") == "rejected"),
        "drafts": drafts
    }

def get_alerts_status() -> dict:
    outbox_path = os.path.join(OUTBOX_DIR, "metadata_outbox.json")
    if not os.path.exists(outbox_path):
        fallback_outbox = os.path.join(HUD_DIR, "data", "metadata_outbox.json")
        if os.path.exists(fallback_outbox):
            outbox_path = fallback_outbox
    log_path = os.path.join(GTM_DIR, "alert_dispatch_log.json")
    if not os.path.exists(log_path):
        fallback_log = os.path.join(HUD_DIR, "data", "alert_dispatch_log.json")
        if os.path.exists(fallback_log):
            log_path = fallback_log
    outbox = []
    logs = []
    if os.path.exists(outbox_path):
        try:
            with open(outbox_path, "r", encoding="utf-8") as f:
                outbox = json.load(f)
        except Exception:
            outbox = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    pending = sum(1 for e in outbox if not e.get("dispatched_via_smtp", False))
    return {
        "pending_outbox_events": pending,
        "total_outbox_events": len(outbox),
        "recent_outbox": outbox[-8:][::-1],
        "dispatch_logs": logs[-5:][::-1]
    }

def get_gateway_status() -> dict:
    from hud.gateway import load_cron_registry, load_task_history, GLOBAL_NONCE_CACHE
    import urllib.request
    hermes_online = False
    hermes_svc = None
    rpc_url = get_hermes_gateway_rpc_url()
    health_url = get_hermes_gateway_health_url()
    try:
        req = urllib.request.Request(health_url)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=1.2) as resp:
            if resp.status == 200:
                h_data = json.loads(resp.read().decode("utf-8"))
                hermes_online = True
                hermes_svc = h_data.get("service")
    except Exception:
        hermes_online = False

    # Check Hostinger Hermes Agent loopback / proxy reachability
    hermes_agent_online = False
    agent_url = get_hermes_agent_url()
    try:
        req_agent = urllib.request.Request(agent_url)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req_agent, timeout=0.8) as resp_ag:
            hermes_agent_online = resp_ag.status in (200, 302)
    except Exception:
        hermes_agent_online = False

    from hud.gateway import GLOBAL_SYNC_TRACKER, GLOBAL_FEEDBACK_LOOP
    crons = load_cron_registry()
    tasks = load_task_history()
    seq_id = GLOBAL_SYNC_TRACKER.current_seq()
    feedback = GLOBAL_FEEDBACK_LOOP.get_metrics()
    return {
        "status": "ok",
        "service": "aios-gateway-host",
        "protocol": "JSON-RPC 2.0 / REST Webhook",
        "auth_method": "HMAC-SHA256 (Anti-Replay Nonce + Timestamp)",
        "hermes_online": hermes_online,
        "hermes_service": hermes_svc or "hermes-8080",
        "hermes_agent_online": hermes_agent_online,
        "hermes_agent_url": agent_url,
        "endpoint_hermes": rpc_url,
        "endpoint_aios": os.environ.get("AIOS_GATEWAY_URL", "http://127.0.0.1:5050/api/gateway/hermes"),
        "crons_total": len(crons),
        "crons_enabled": sum(1 for c in crons if c.get("enabled")),
        "tasks_executed": len(tasks),
        "recent_tasks": tasks[-5:][::-1],
        "replay_cache_size": GLOBAL_NONCE_CACHE.size(),
        "sync_sequence_id": seq_id,
        "feedback": feedback,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

# --------------------------------------------------------------------------- #
# Next Cortex Anti-Gravity Dashboard Engine (Credits, Tasks, Hierarchy & Streaming)
# --------------------------------------------------------------------------- #
_CORTEX_LOCK = threading.RLock()
_CORTEX_AUTO_ACCEPT = True
_CORTEX_STREAMING_SERIES: deque = deque(maxlen=60)
_CORTEX_START_TIME = time.time()
_CORTEX_TOTAL_BUDGET = 100000

def get_cortex_credits() -> Dict[str, Any]:
    """Calculates local quota, remaining credits, model rates, and reset countdown."""
    uptime_sec = time.time() - _CORTEX_START_TIME
    db_data = get_offline_ledger_and_invariant()
    total_jobs = len(db_data.get("jobs", []))

    # Calculate token/credit burn based on executed jobs and gateway ops
    from hud.gateway import GLOBAL_SYNC_TRACKER
    seq = GLOBAL_SYNC_TRACKER.current_seq()

    # 1 job = ~350 credit units, 1 gateway task = ~120 credit units
    credits_consumed = min(_CORTEX_TOTAL_BUDGET, (total_jobs * 350) + (seq * 120))
    credits_remaining = max(0, _CORTEX_TOTAL_BUDGET - credits_consumed)
    usage_percent = round((credits_consumed / _CORTEX_TOTAL_BUDGET) * 100, 2)

    # Reset countdown (24-hour rolling replenishment window)
    now = datetime.now(timezone.utc)
    seconds_until_midnight = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
    burn_rate_min = round(float(credits_consumed) / max(1.0, uptime_sec / 60.0), 1)

    return {
        "total_budget": _CORTEX_TOTAL_BUDGET,
        "credits_remaining": credits_remaining,
        "credits_consumed": credits_consumed,
        "usage_percent": usage_percent,
        "reset_countdown_seconds": seconds_until_midnight,
        "reset_time_utc": (now + timedelta(seconds=seconds_until_midnight)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_model": "qwen3:4b (Local Hermes / Unmetered)",
        "burn_rate_credits_per_min": burn_rate_min,
        "unmetered_local_calls": seq,
        "metered_cloud_calls": 0,
        "quota_status": "HEALTHY" if usage_percent < 80 else ("WARNING" if usage_percent < 95 else "CRITICAL")
    }

def get_cortex_automated_tasks() -> Dict[str, Any]:
    """Tracks automated task execution history, auto-accept status, and pending approvals."""
    from hud.gateway import load_task_history
    tasks = load_task_history(limit=50)

    auto_tasks = []
    for t in tasks:
        cmd = t.get("command", "")
        is_safe = cmd in ("ping", "audit_invariants", "sync_board_tasks", "second_brain_scan", "reconciliation")
        auto_tasks.append({
            "task_id": t.get("task_id", ""),
            "command": cmd,
            "status": "auto_approved" if (_CORTEX_AUTO_ACCEPT and is_safe) else t.get("status", "completed"),
            "duration_ms": t.get("duration_ms", 0.0),
            "executed_at": t.get("executed_at", ""),
            "requires_operator_signoff": not is_safe,
            "sequence_id": t.get("sequence_id", 1)
        })

    return {
        "auto_accept_enabled": _CORTEX_AUTO_ACCEPT,
        "total_automated_tasks": len(auto_tasks),
        "auto_approved_count": sum(1 for t in auto_tasks if t.get("status") == "auto_approved"),
        "pending_review_count": sum(1 for t in auto_tasks if t.get("requires_operator_signoff")),
        "tasks": auto_tasks
    }

VISUALIZATION_ENGINE = RealTimeVisualizationEngine(db_path_resolver=lambda: get_db_path())
TYPE_SAFE_ROUTER = TypeSafeRouter(observability=GLOBAL_OBSERVABILITY)

def get_sqlite_ledger_data(trace_id: Optional[str] = None) -> Dict[str, Any]:
    """Reads raw and aggregated data from SQLite job_ledger.db across tables in read-only mode."""
    return VISUALIZATION_ENGINE.get_sqlite_ledger(trace_id=trace_id).model_dump()

def get_cortex_hierarchy(trace_id: Optional[str] = None) -> Dict[str, Any]:
    """Builds a multi-level DAG hierarchy graph (Tiers 1-4) from SQLite ledger and AIOS governance."""
    return VISUALIZATION_ENGINE.generate_dag_hierarchy(trace_id=trace_id).model_dump()

def record_cortex_streaming_point() -> Dict[str, Any]:
    """Appends a new time-series metric sample into the rolling streaming series."""
    with _CORTEX_LOCK:
        credits_info = get_cortex_credits()
        from hud.gateway import GLOBAL_FEEDBACK_LOOP
        fb = GLOBAL_FEEDBACK_LOOP.get_metrics()

        db_data = get_offline_ledger_and_invariant()
        jobs_active = sum(1 for j in db_data.get("jobs", []) if j.get("state") in ("queued", "running"))
        jobs_completed = sum(1 for j in db_data.get("jobs", []) if j.get("state") == "completed")

        pt = VISUALIZATION_ENGINE.record_streaming_point(
            credits_remaining=credits_info.get("credits_remaining", 100000),
            credits_consumed=credits_info.get("credits_consumed", 0),
            burn_rate=credits_info.get("burn_rate_credits_per_min", 0.0),
            rtt_ms=fb.get("latest_rtt_ms", 0.0),
            jobs_active=jobs_active,
            jobs_completed=jobs_completed,
            total_probes=fb.get("total_probes", 0)
        )
        return pt.model_dump()

def get_cortex_streaming_series(trace_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns the rolling 60-second time-series buffer for streaming charts."""
    with _CORTEX_LOCK:
        resp = VISUALIZATION_ENGINE.get_streaming_series(trace_id=trace_id)
        if not resp.series:
            record_cortex_streaming_point()
            resp = VISUALIZATION_ENGINE.get_streaming_series(trace_id=trace_id)
        return [pt.model_dump() for pt in resp.series]

# Register Type-Safe Routes for Real-Time Visualization, Ledger & Observability
TYPE_SAFE_ROUTER.register(
    "/api/cortex/streaming-series", "GET",
    lambda trace_id=None, **_: StreamingSeriesResponse(
        status="ok",
        series=get_cortex_streaming_series(trace_id=trace_id),
        buffer_size=len(get_cortex_streaming_series(trace_id=trace_id)),
        window_seconds=60,
        trace_id=trace_id
    ),
    response_model=StreamingSeriesResponse,
    service="aios-visualization"
)
TYPE_SAFE_ROUTER.register(
    "/api/cortex/hierarchy", "GET",
    lambda trace_id=None, **_: VISUALIZATION_ENGINE.generate_dag_hierarchy(trace_id=trace_id),
    response_model=CortexHierarchyPayload,
    service="aios-visualization"
)
TYPE_SAFE_ROUTER.register(
    "/api/sqlite/ledger", "GET",
    lambda trace_id=None, **_: VISUALIZATION_ENGINE.get_sqlite_ledger(trace_id=trace_id),
    response_model=SQLiteLedgerPayload,
    service="aios-ledger-diode"
)
TYPE_SAFE_ROUTER.register(
    "/api/cortex/credits", "GET",
    lambda **_: get_cortex_credits(),
    service="aios-governance"
)
TYPE_SAFE_ROUTER.register(
    "/api/cortex/tasks", "GET",
    lambda **_: get_cortex_automated_tasks(),
    service="aios-governance"
)
TYPE_SAFE_ROUTER.register(
    "/api/observability/metrics", "GET",
    lambda **_: GLOBAL_OBSERVABILITY.get_metrics(),
    response_model=EncoreObservabilityMetrics,
    service="aios-observability"
)
TYPE_SAFE_ROUTER.register(
    "/api/observability/traces", "GET",
    lambda **_: {"status": "ok", "traces": GLOBAL_OBSERVABILITY.get_recent_spans()},
    service="aios-observability"
)
TYPE_SAFE_ROUTER.register(
    "/api/observability/health", "GET",
    lambda **_: {"status": "healthy", "service": "aios-hud-server", "framework": "encore", "version": "1.58.8"},
    service="aios-observability"
)

# --------------------------------------------------------------------------- #
# AI OS dashboard: telemetry frame + board helpers (logic lives in hud/os_dashboard.py)
# --------------------------------------------------------------------------- #
_HERMES_CACHE = {"at": 0.0, "value": None}
_HERMES_CACHE_LOCK = threading.Lock()
_TELEMETRY_TRIGGER = threading.Event()


def notify_telemetry_event():
    """Wakes up all active SSE streams immediately to flush new frame deltas with 0 buffering lag."""
    with _HERMES_CACHE_LOCK:
        _HERMES_CACHE["value"] = None
        _HERMES_CACHE["at"] = 0.0
    _TELEMETRY_TRIGGER.set()


def cached_hermes_telemetry(ttl: float = 15.0) -> dict:
    """The loopback probe can take 1.5 s; share one result across stream clients."""
    with _HERMES_CACHE_LOCK:
        if _HERMES_CACHE["value"] is not None and time.monotonic() - _HERMES_CACHE["at"] < ttl:
            return _HERMES_CACHE["value"]
        value = get_hermes_telemetry()
        _HERMES_CACHE.update(at=time.monotonic(), value=value)
        return value


def _read_json_file(path: str, default):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def _mtime(path: str):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


INBOX_SNAPSHOT = os.path.join(HUD_DIR, "inbox", "offline_snapshot.json")


def os_board_payload() -> dict:
    from hud import os_dashboard as osd
    board = osd.load_board()
    now = datetime.now()
    ics = osd.read_ics_events()
    plan = osd.plan_day(board, osd.plan_target_day(board, now), now, ics)
    horizon = (now.date().isoformat(), (now.date().fromordinal(now.date().toordinal() + 7)).isoformat())
    upcoming = sorted(
        [dict(e, source=e.get("source", "board")) for e in board["events"] + ics
         if horizon[0] <= e.get("date", "") <= horizon[1]],
        key=lambda e: (e["date"], e.get("start", "")))
    return {"board": board, "plan": plan, "upcoming": upcoming[:40],
            "calendar_dir": str(osd.CALENDAR_DIR), "ics_events": len(ics),
            "now": now.isoformat(timespec="minutes")}


def os_frame() -> dict:
    from hud import os_dashboard as osd
    from hud.jev_guard import GUARDRAIL_LOG
    from hud.jev_e2e_pipeline import E2E_LOG_PATH, get_recent_e2e_events
    board = osd.load_board()
    now = datetime.now()
    plan = osd.plan_day(board, osd.plan_target_day(board, now), now, osd.read_ics_events())
    mtimes = {
        "inbox": _mtime(INBOX_SNAPSHOT),
        "ledger": _mtime(os.path.join(OFFLINE_DIR, "job_ledger.db")),
        "gtm": _mtime(os.path.join(GTM_DIR, "staged_outreach.json")),
        "notify": _mtime(os.path.join(OUTBOX_DIR, "metadata_outbox.json")),
        "hermes": _mtime(os.path.join(OFFLINE_DIR, "inference_telemetry.json")),
        "guard": _mtime(str(GUARDRAIL_LOG)),
        "e2e": _mtime(str(E2E_LOG_PATH)),
    }
    frame = osd.compose_frame(
        hermes=cached_hermes_telemetry(), ledger=get_offline_ledger_and_invariant(),
        gtm=get_gtm_queue(), alerts_status=get_alerts_status(),
        inbox=_read_json_file(INBOX_SNAPSHOT, {}), guard_events=_read_json_file(str(GUARDRAIL_LOG), []),
        e2e_events=get_recent_e2e_events(1), board=board, plan=plan, stats=osd.static_stats(),
        mtimes=mtimes, now=now,
        server={"pid": os.getpid(), "build": BUILD_ID, "uptime_min": int((time.time() - SERVER_STARTED) // 60)},
        gateway=get_gateway_status(),
    )
    st_pt = record_cortex_streaming_point()
    frame["cortex"] = {
        "credits": get_cortex_credits(),
        "tasks": get_cortex_automated_tasks(),
        "latest_stream_point": st_pt
    }
    frame["observability"] = GLOBAL_OBSERVABILITY.get_metrics().model_dump()
    try:
        from hud.shared_memory import get_shared_memory_store
        frame["memory"] = get_shared_memory_store().get_state_summary()
    except Exception as exc:
        frame["memory"] = {"error": str(exc)}
    return frame


def os_inbox_payload() -> dict:
    snap = _read_json_file(INBOX_SNAPSHOT, {})
    ledger = snap.get("ledger") if isinstance(snap.get("ledger"), dict) else {}
    return {"exported_at": snap.get("exported_at"), "errors": snap.get("errors") or {},
            "events": snap.get("events") or [], "jobs": ledger.get("jobs") or [],
            "source": "inbox/offline_snapshot.json"}


def os_outbox_payload() -> dict:
    from hud.gtm import view_queue
    stage_path = os.path.join(GTM_DIR, "staged_outreach.json")
    drafts, revision, error = [], None, None
    if os.path.exists(stage_path):
        try:
            view = view_queue(stage_path)
            revision = view["revision"]
            for d in view["drafts"]:
                drafts.append({
                    "id": d["id"], "company": d.get("company_name") or d.get("company") or "(unknown)",
                    "contact": d.get("contact_name") or "", "vertical": d.get("vertical") or "",
                    "subject": d.get("subject") or d.get("staged_email_subject") or "",
                    "body": d.get("body") or d.get("staged_email_body") or "",
                    "status": d["effective_status"],
                })
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    notify = _read_json_file(os.path.join(OUTBOX_DIR, "metadata_outbox.json"), [])
    archive = _read_json_file(os.path.join(OUTBOX_DIR, "metadata_outbox.archive.json"), [])
    return {"revision": revision, "drafts": drafts, "error": error,
            "notice": "Approve records a human decision only. No outreach is dispatched.",
            "notify_pending": notify if isinstance(notify, list) else [],
            "notify_archived": len(archive) if isinstance(archive, list) else 0}


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>JEV Dual-Core Command HUD</title>
<style>
  :root {
    --bg: #0b0f17; --card: #131b2e; --border: #23314f;
    --text: #e2e8f0; --muted: #94a3b8;
    --green: #10b981; --amber: #f59e0b; --red: #ef4444;
  }
  * { box-sizing: border-box; font-family: Consolas, 'Courier New', monospace; }
  body { margin: 0; background: var(--bg); color: var(--text); }
  .hud-ribbon {
    position: sticky; top: 0; z-index: 100;
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
    padding: 12px 18px; background: #070a10; border-bottom: 2px solid var(--border);
  }
  .hud-pill {
    padding: 10px 12px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--card); font-size: 12px;
  }
  .hud-pill .label { color: var(--muted); font-size: 11px; text-transform: uppercase; }
  .hud-pill .val { font-size: 14px; font-weight: bold; margin-top: 4px; }
  .ok { color: var(--green); } .warn { color: var(--amber); } .err { color: var(--red); }
  .grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 18px;
  }
  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px; display: flex; flex-direction: column; gap: 10px;
  }
  .card h2 { margin: 0; font-size: 15px; color: #60a5fa; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { text-align: left; padding: 6px; border-bottom: 1px solid #1e293b; }
  th { color: var(--muted); }
  .btn {
    background: #1e293b; color: var(--text); border: 1px solid #475569;
    padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
  }
  .btn:hover { background: #334155; }
  .btn-approve { border-color: var(--green); color: var(--green); }
  .btn-reject { border-color: var(--red); color: var(--red); }
  .badge { padding: 2px 6px; border-radius: 4px; font-size: 11px; background: #1e293b; }
  pre { background: #090d16; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 11px; margin: 0; }
</style>
</head>
<body>
  <div class="hud-ribbon">
    <div class="hud-pill">
      <div class="label">1. Hermes Runtime & Provenance</div>
      <div id="hud-hermes" class="val">Loading...</div>
    </div>
    <div class="hud-pill">
      <div class="label">2. Zero-Loss Invariant (delivery-offline)</div>
      <div id="hud-invariant" class="val">Loading...</div>
    </div>
    <div class="hud-pill">
      <div class="label">3. SQLite Job Ledger Pulse</div>
      <div id="hud-ledger" class="val">Loading...</div>
    </div>
    <div class="hud-pill">
      <div class="label">4. Metadata Diode & GTM Gate</div>
      <div id="hud-alerts" class="val">Loading...</div>
    </div>
  </div>

  <div id="action-status" role="status" aria-live="polite" style="padding:8px 18px"></div>
  <div class="grid">
    <div class="card">
      <h2>Module A: Hermes Runtime & 1-Retry Repair Monitor</h2>
      <div>
        <button class="btn" data-probe onclick="triggerAction('/api/hermes/probe', {allow_simulation: false})">Run Strict Probe (No Sim)</button>
        <button class="btn" data-probe onclick="triggerAction('/api/hermes/probe', {allow_simulation: true})">Run Fallback Sim Probe</button>
      </div>
      <div id="mod-hermes">Loading...</div>
    </div>

    <div class="card">
      <h2>Module B: Offline Financial Vault & Quarantine Inspector</h2>
      <div>
        <button class="btn" onclick="triggerAction('/api/offline-ledger/cycle', {})">Queue & Execute Atomic Job Cycle</button>
      </div>
      <div id="mod-ledger">Loading...</div>
    </div>

    <div class="card">
      <h2>Module C: GTM Human-Review Gate (staged_outreach.json)</h2>
      <div id="mod-gtm">Loading...</div>
    </div>

    <div class="card">
      <h2>Module D: Air-Gap Metadata Diode & SMTP Alert Relay</h2>
      <div>
        <button class="btn" onclick="triggerAction('/api/alerts/dispatch', {})">Flush Metadata Outbox via Isolated Relay</button>
      </div>
      <div id="mod-alerts">Loading...</div>
    </div>
  </div>

<script>
function escapeHTML(value) {
  const el = document.createElement('span');
  el.textContent = String(value == null ? '' : value);
  return el.innerHTML;
}

async function fetchJSON(url, options = {}, timeout = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, {...options, signal: controller.signal, cache: 'no-store'});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || body.detail || ('HTTP ' + response.status));
    return body;
  } finally {
    clearTimeout(timer);
  }
}

async function triggerAction(url, payload) {
  const message = document.getElementById('action-status');
  const probe = url === '/api/hermes/probe';
  const buttons = probe ? document.querySelectorAll('button[data-probe]') : [];
  buttons.forEach(button => { button.disabled = true; });
  message.textContent = probe ? 'Running local probe. Simulation ' + (payload.allow_simulation ? 'permitted.' : 'disabled.') : 'Working...';
  try {
    const result = await fetchJSON(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}, 105000);
    message.textContent = probe ? 'Probe finished: ' + result.status + ' (' + result.execution_mode + ').' : 'Action completed.';
  } catch (error) {
    message.textContent = 'Action failed: ' + error.message;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
    try { await refreshAll(); } catch (error) { message.textContent += ' Status refresh failed: ' + error.message; }
  }
}

async function refreshAll() {
  const [hermes, ledger, gtm, alerts] = await Promise.all([
    fetchJSON('/api/hermes'),
    fetchJSON('/api/offline-ledger'),
    fetchJSON('/api/gtm-queue'),
    fetchJSON('/api/alerts')
  ]);

  const hEl = document.getElementById('hud-hermes');
  const state = hermes.live_loopback_reachable ? 'OLLAMA CONNECTED' : 'OLLAMA UNREACHABLE';
  hEl.innerHTML = '<span class="' + (hermes.live_loopback_reachable ? 'ok' : 'err') + '">' + state + '</span> ' + escapeHTML(hermes.model)
    + '<div>Last probe: ' + escapeHTML(hermes.last_status) + (hermes.is_simulated ? ' (SIMULATED)' : '') + '</div>';

  const invEl = document.getElementById('hud-invariant');
  if (ledger.invariant.passed) {
    invEl.innerHTML = `<span class="ok">PASS</span> (${ledger.invariant.formula})`;
  } else {
    invEl.innerHTML = `<span class="err">BREACH</span> (${ledger.invariant.formula})`;
  }

  const c = ledger.counts;
  document.getElementById('hud-ledger').innerHTML =
    `Q:${c.queued} | Run:${c.running} | Val:${c.validated} | <span class="ok">Comp:${c.completed}</span> | <span class="warn">Quar:${c.quarantined}</span>`;

  document.getElementById('hud-alerts').innerHTML =
    `<span class="warn">GTM Review: ${gtm.needs_review}</span> | Outbox Pending: ${alerts.pending_outbox_events}`;

  const latestAttempt = hermes.attempts[hermes.attempts.length - 1] || {};
  const usedTokens = latestAttempt.usage && latestAttempt.usage.completion_tokens;
  document.getElementById('mod-hermes').innerHTML =
    '<div>Loopback: <b>' + (hermes.live_loopback_reachable ? 'REACHABLE' : 'UNREACHABLE') + '</b> | Mode: ' + escapeHTML(hermes.last_execution_mode) + '</div>'
    + '<div>Output tokens: ' + (Number.isInteger(usedTokens) ? usedTokens : 'not recorded') + ' / ' + hermes.max_tokens + ' | Max repair retries: ' + hermes.max_retries + '</div>'
    + '<div>Last result: ' + escapeHTML(hermes.timestamp_utc || 'not yet tested') + (hermes.probe_running ? ' | PROBE RUNNING' : '') + '</div>'
    + '<pre>' + escapeHTML(JSON.stringify(hermes.attempts, null, 2)) + '</pre>';

  const qRows = ledger.invariant.quarantined_samples.map(q =>
    `<tr><td>Row ${q.row}</td><td>${q.invoice_id}</td><td class="err">${q.raw_amount}</td></tr>`
  ).join('');
  const jobRows = ledger.jobs.slice(0, 6).map(j =>
    `<tr><td>${j.job_id}</td><td>${j.job_type}</td><td><b>${j.state}</b></td><td>${j.attempt_count}</td></tr>`
  ).join('');
  document.getElementById('mod-ledger').innerHTML = `
    <div><b>Recent SQLite Jobs (Enforced State Graph + rowcount==1):</b></div>
    <table><tr><th>Job ID</th><th>Type</th><th>State</th><th>Attempts</th></tr>${jobRows}</table>
    <div style="margin-top:6px;"><b>Quarantined CSV Rows (Verbatim String Inspection):</b></div>
    <table><tr><th>CSV Row</th><th>Invoice ID</th><th>Malformed Amount (StrictStr)</th></tr>${qRows}</table>
  `;

  const gtmCards = gtm.drafts.map((d, i) => `
    <div style="border:1px solid #23314f; padding:8px; border-radius:4px; margin-bottom:6px;">
      <div><b>${d.company_name}</b> (${d.recipient_ref}) 窶・Status: <span class="badge">${d.status}</span></div>
      <div style="color:#94a3b8; font-size:11px; margin:4px 0;">${d.subject}</div>
      <button class="btn btn-approve" onclick="triggerAction('/api/gtm-queue/review', {index: ${i}, status: 'approved'})">Approve</button>
      <button class="btn btn-reject" onclick="triggerAction('/api/gtm-queue/review', {index: ${i}, status: 'rejected'})">Reject</button>
      <button class="btn" onclick="triggerAction('/api/gtm-queue/review', {index: ${i}, status: 'needs_review'})">Reset Gate</button>
    </div>
  `).join('');
  document.getElementById('mod-gtm').innerHTML = gtmCards || '<div>No staged outreach found.</div>';

  document.getElementById('mod-alerts').innerHTML = `
    <div><b>Sanitized Metadata Outbox (notification-outbox/metadata_outbox.json):</b></div>
    <pre>${JSON.stringify(alerts.recent_outbox, null, 2)}</pre>
    <div><b>Recent Relay Dispatches:</b></div>
    <pre>${JSON.stringify(alerts.dispatch_logs, null, 2)}</pre>
  `;
}

refreshAll();
setInterval(refreshAll, 5000);
</script>
</body>
</html>
"""

class HUDRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, data: dict, status: int = 200, ack_id: str | None = None, seq_id: int | None = None, rtt_ms: float | None = None):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache, no-transform, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
        trace_id = GLOBAL_OBSERVABILITY.generate_trace_id()
        span_id = GLOBAL_OBSERVABILITY.generate_span_id()
        self.send_header("X-Encore-Trace-ID", trace_id)
        self.send_header("X-Encore-Span-ID", span_id)
        self.send_header("traceparent", GLOBAL_OBSERVABILITY.build_traceparent(trace_id, span_id))
        self.send_header("X-Encore-Service", "aios-hud-server")
        if ack_id:
            self.send_header("X-Gateway-Ack", str(ack_id))
        if seq_id is not None:
            self.send_header("X-Gateway-Seq", str(seq_id))
        if rtt_ms is not None:
            self.send_header("X-Gateway-RTT", str(rtt_ms))
        self.end_headers()
        self.wfile.write(raw)
        self.wfile.flush()

    def _send_type_safe_json(self, data: dict, status: int = 200, headers: dict | None = None):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache, no-transform, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
        if headers:
            for k, v in headers.items():
                if k.lower() not in ("content-type", "content-length", "cache-control", "x-accel-buffering", "content-security-policy"):
                    self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(raw)
        self.wfile.flush()

    def _send_static(self, rel_path: str, csp: str | None = None):
        """Serve a file under hud-interface/static only (no traversal)."""
        root = os.path.realpath(os.path.join(HUD_DIR, "static"))
        fpath = os.path.realpath(os.path.join(root, rel_path))
        if os.path.commonpath([root, fpath]) != root or not os.path.isfile(fpath):
            self._send_json({"error": "Not found"}, 404)
            return
        types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json"}
        ctype = types.get(os.path.splitext(fpath)[1].lower(), "application/octet-stream")
        with open(fpath, "rb") as f:
            raw = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if csp:
            self.send_header("Content-Security-Policy", csp)
            self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    # ------------------------------------------------------------------ #
    # AI OS dashboard routes
    # ------------------------------------------------------------------ #
    def _send_os_error(self, exc: Exception):
        from hud.gtm import Conflict
        if isinstance(exc, Conflict) or isinstance(exc, RuntimeError):
            status = 409
        elif isinstance(exc, (KeyError, FileNotFoundError)):
            status = 404
        elif isinstance(exc, TimeoutError):
            status = 503
        elif isinstance(exc, (ValueError, TypeError)):
            status = 400
        else:
            status = 500
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        self._send_json({"error": message, "error_type": type(exc).__name__}, status)

    def _stream_os_telemetry(self):
        """Server-Sent Events: one compact frame when anything changes, a ping every 15 s.
        Each connection lives 10 minutes, then the browser's EventSource reconnects.
        Enforces zero-buffering headers and event-triggered fast-path wakeups."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform, no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        last_hash, last_sent, seq = None, 0.0, 0
        deadline = time.monotonic() + 600
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            while time.monotonic() < deadline:
                try:
                    frame = os_frame()
                except Exception as exc:  # report, do not kill the stream
                    frame = {"error": f"{type(exc).__name__}: {exc}", "hash": "error"}
                if frame.get("hash") != last_hash:
                    seq += 1
                    frame["seq"] = seq
                    payload = json.dumps(frame, default=str)
                    self.wfile.write(f"event: telemetry\nid: {seq}\ndata: {payload}\n\n".encode("utf-8"))
                    last_hash, last_sent = frame.get("hash"), time.monotonic()
                elif time.monotonic() - last_sent >= 15:
                    ping = json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seq": seq})
                    self.wfile.write(f"event: ping\ndata: {ping}\n\n".encode("utf-8"))
                    last_sent = time.monotonic()
                self.wfile.flush()
                # Fast-path event wait: wakes immediately upon state change or every 2 seconds
                _TELEMETRY_TRIGGER.wait(timeout=2.0)
                _TELEMETRY_TRIGGER.clear()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def _handle_os_get(self, path: str, query: dict):
        from hud import os_dashboard as osd
        q = lambda key: (query.get(key) or [""])[0]
        try:
            if path == "/api/os/stream":
                self._stream_os_telemetry()
            elif path == "/api/os/telemetry":
                self._send_json(os_frame())
            elif path == "/api/os/obsidian":
                if q("rescan") in ("1", "true", "yes"):
                    osd.invalidate_vault_cache()
                self._send_json(os_frame().get("obsidian", {}))
            elif path == "/api/os/board":
                self._send_json(os_board_payload())
            elif path == "/api/os/inbox":
                self._send_json(os_inbox_payload())
            elif path == "/api/os/outbox":
                self._send_json(os_outbox_payload())
            elif path == "/api/os/docs":
                self._send_json({"docs": osd.list_docs()})
            elif path == "/api/os/doc":
                self._send_json(osd.read_doc(q("id")))
            elif path == "/api/os/editor/files":
                self._send_json(osd.editor_list())
            elif path == "/api/os/editor/file":
                self._send_json(osd.editor_read(q("name")))
            else:
                self._send_json({"error": "Not found"}, 404)
        except Exception as exc:
            self._send_os_error(exc)

    def _handle_os_post(self, path: str, body: dict):
        from hud import os_dashboard as osd
        try:
            if path == "/api/os/board":
                osd.apply_board_op(body)
                notify_telemetry_event()
                self._send_json(os_board_payload())
            elif path == "/api/os/editor/save":
                self._send_json(osd.editor_save(str(body.get("name", "")), body.get("text"), body.get("base_sha256") or None))
            elif path == "/api/os/obsidian/note":
                self._send_json(osd.create_vault_note(body))
                notify_telemetry_event()
            elif path == "/api/os/obsidian/rescan":
                osd.invalidate_vault_cache()
                notify_telemetry_event()
                self._send_json(os_frame().get("obsidian", {}))
            elif path == "/api/os/outbox/decide":
                from hud.gtm import decide
                decide(os.path.join(GTM_DIR, "staged_outreach.json"), str(body.get("id", "")),
                       str(body.get("revision", "")), str(body.get("decision", "")))
                notify_telemetry_event()
                self._send_json(os_outbox_payload())
            else:
                self._send_json({"error": "Unknown endpoint"}, 404)
        except Exception as exc:
            self._send_os_error(exc)

    def do_GET(self):
        path, _, raw_query = self.path.partition("?")
        if (path, "GET") in TYPE_SAFE_ROUTER._routes or path.startswith("/api/observability/"):
            res, status_code, extra_headers = TYPE_SAFE_ROUTER.dispatch(path, "GET", dict(self.headers), query=parse_qs(raw_query))
            self._send_type_safe_json(res, status_code, extra_headers)
            return
        if path.startswith("/api/os/"):
            self._handle_os_get(path, parse_qs(raw_query))
            return
        if path in ("/", "/os"):
            # Primary view: AI OS dashboard (static/os.html).
            self._send_static("os.html", csp=OS_PAGE_CSP)
        elif path in ("/cockpit", "/index.html"):
            # Synchronized cockpit (Prototype III), previously the default view.
            self._send_static("index.html")
        elif path.startswith("/static/"):
            self._send_static(path[len("/static/"):])
        elif path == "/legacy":
            raw = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == "/api/hermes":
            self._send_json(get_hermes_telemetry())
        elif self.path == "/api/offline-ledger":
            self._send_json(get_offline_ledger_and_invariant())
        elif self.path == "/api/quarantine":
            self._send_json(get_quarantine_data())
        elif self.path == "/api/gtm-queue":
            self._send_json(get_gtm_queue())
        elif self.path == "/api/alerts":
            self._send_json(get_alerts_status())
        elif self.path == "/api/omnibus":
            from hud.omnibus import get_omnibus_bundle
            self._send_json(get_omnibus_bundle())
        elif self.path == "/api/guardrail/events":
            from hud.jev_guard import GUARDRAIL_LOG
            if os.path.exists(GUARDRAIL_LOG):
                try:
                    with open(GUARDRAIL_LOG, "r", encoding="utf-8") as f:
                        self._send_json(json.load(f))
                        return
                except Exception:
                    pass
            self._send_json([])
        elif self.path == "/api/jev-cheap-read/fixtures":
            from hud.jev_cheap_read import list_cheap_read_fixtures
            self._send_json(list_cheap_read_fixtures())
        elif self.path == "/api/jev-agentic/events":
            from hud.jev_agentic import AGENTIC_JEV_LOG
            if os.path.exists(AGENTIC_JEV_LOG):
                try:
                    with open(AGENTIC_JEV_LOG, "r", encoding="utf-8") as f:
                        self._send_json(json.load(f))
                        return
                except Exception:
                    pass
            self._send_json([])
        elif self.path == "/api/jev-composite-gate/presets":
            from hud.jev_composite_gate import GTM_OUTREACH_WEIGHTS, CODE_REVIEW_WEIGHTS, IDEA_VERDICT_WEIGHTS
            self._send_json({
                "weights": {
                    "gtm_outreach": GTM_OUTREACH_WEIGHTS,
                    "code_review": CODE_REVIEW_WEIGHTS,
                    "idea_verdict": IDEA_VERDICT_WEIGHTS,
                },
                "confidence_thresholds": {"floor": 0.50, "ceiling": 0.90},
            })
        elif self.path == "/api/jev-e2e/events":
            from hud.jev_e2e_pipeline import get_recent_e2e_events
            self._send_json(get_recent_e2e_events())
        elif self.path == "/api/session":
            self._send_json({"token": "local-session-token", "authenticated": True})
        elif self.path == "/api/gateway/status":
            self._send_json(get_gateway_status())
        elif self.path in ("/api/gateway/feedback", "/api/gateway/sync"):
            from hud.gateway import GLOBAL_SYNC_TRACKER, GLOBAL_FEEDBACK_LOOP
            self._send_json({
                "status": "ok",
                "sequence_id": GLOBAL_SYNC_TRACKER.current_seq(),
                "feedback": GLOBAL_FEEDBACK_LOOP.get_metrics(),
                "history": GLOBAL_SYNC_TRACKER.get_history(limit=25),
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        elif self.path == "/api/gateway/crons":
            from hud.gateway import load_cron_registry
            self._send_json({"status": "ok", "crons": load_cron_registry()})
        elif self.path == "/api/gateway/tasks":
            from hud.gateway import load_task_history
            self._send_json({"status": "ok", "tasks": load_task_history()})
        elif self.path == "/api/cortex/credits":
            self._send_json(get_cortex_credits())
        elif self.path == "/api/cortex/tasks":
            self._send_json(get_cortex_automated_tasks())
        elif self.path == "/api/cortex/hierarchy":
            self._send_json(get_cortex_hierarchy())
        elif self.path == "/api/cortex/streaming-series":
            self._send_json({"status": "ok", "series": get_cortex_streaming_series()})
        elif self.path == "/api/sqlite/ledger":
            self._send_json(get_sqlite_ledger_data())
        elif self.path == "/api/memory/state":
            from hud.shared_memory import get_shared_memory_store
            self._send_json(get_shared_memory_store().get_state_summary())
        elif self.path.startswith("/api/memory/tasks"):
            from hud.shared_memory import get_shared_memory_store
            self._send_json({"status": "ok", "tasks": get_shared_memory_store().get_completed_tasks()})
        elif self.path.startswith("/api/memory/blackboard"):
            from hud.shared_memory import get_shared_memory_store
            store = get_shared_memory_store()
            q_parsed = parse_qs(urlparse(self.path).query)
            key = (q_parsed.get("key") or [""])[0]
            if key:
                self._send_json({"key": key, "value": store.get_blackboard_key(key)})
            else:
                self._send_json({"status": "ok", "entries": store.get_all_blackboard_entries()})
        elif self.path == "/api/memory/obsidian-status":
            from hud.shared_memory import get_shared_memory_store, PRIMARY_VAULT_DIR, LOCAL_VAULT_DIR
            store = get_shared_memory_store()
            self._send_json({
                "status": store._vault_sync_status,
                "last_vault_sync_utc": store._last_vault_sync_utc,
                "primary_vault_dir": str(PRIMARY_VAULT_DIR),
                "primary_vault_exists": PRIMARY_VAULT_DIR.exists(),
                "local_vault_dir": str(LOCAL_VAULT_DIR),
                "local_vault_exists": LOCAL_VAULT_DIR.exists()
            })
        elif self.path == "/api/hud":
            self._send_json({
                "hermes": get_hermes_telemetry(),
                "ledger": get_offline_ledger_and_invariant(),
                "alerts": get_alerts_status()
            })
        elif self.path in ("/prototype-1-ring-command.html", "/prototype-2-minimal-3d.html", "/prototype-3-cockpit-split.html", "/static/jev-omnibus.js"):
            fpath = os.path.join(HUD_DIR, self.path.lstrip("/"))
            if os.path.isfile(fpath):
                raw = open(fpath, "rb").read()
                ctype = "text/javascript; charset=utf-8" if fpath.endswith(".js") else "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            else:
                self._send_json({"error": "Not found"}, 404)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            # The scratch editor may save up to 128 KB of UTF-8 text (JSON-escaped -> allow 512 KB).
            limit = 524288 if self.path == "/api/os/editor/save" else 16384
            if not 0 <= length <= limit:
                self._send_json({"error": "Request body is too large."}, 413)
                return
            raw_body = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw_body.decode("utf-8")) if length else {}
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object.")
        except (ValueError, UnicodeError) as exc:
            self._send_json({"error": str(exc)}, 400)
            return

        if (self.path, "POST") in TYPE_SAFE_ROUTER._routes:
            res, status_code, extra_headers = TYPE_SAFE_ROUTER.dispatch(self.path, "POST", dict(self.headers), body=body)
            self._send_type_safe_json(res, status_code, extra_headers)
            return

        if self.path.startswith("/api/os/"):
            self._handle_os_post(self.path, body)
            return

        if self.path == "/api/hermes/probe":
            allow_sim = body.get("allow_simulation", False)
            if type(allow_sim) is not bool:
                self._send_json({"error": "allow_simulation must be a JSON boolean."}, 400)
                return
            if not PROBE_LOCK.acquire(blocking=False):
                self._send_json({"error": "A probe is already running. Wait for its result."}, 409)
                return
            try:
                from inference_adapter import LiveLocalModelAdapter, FailureEvent
                sample = {"type": "probe_test", "description": "Synthetic HUD connectivity test",
                          "reported_events": 1, "period": "TEST", "evidence_ids": ["hud-probe-" + uuid.uuid4().hex]}
                prompt = "Extract the following synthetic event exactly, preserving all values: " + json.dumps(sample)
                adapter = LiveLocalModelAdapter(endpoint=get_hermes_endpoint(),
                                                model_tag=get_hermes_model(),
                                                allow_simulation=allow_sim)
                res = adapter.enforce_schema_and_quarantine(prompt, FailureEvent)
                with _HERMES_CACHE_LOCK:
                    _HERMES_CACHE["value"] = None
                    _HERMES_CACHE["at"] = 0.0
                self._send_json(res)
            except Exception as exc:
                self._send_json({"error": "Probe failed: " + str(exc), "error_type": type(exc).__name__}, 500)
            finally:
                PROBE_LOCK.release()

        elif self.path == "/api/offline-ledger/cycle":
            from job_ledger import queue_job, claim_job, update_job_state
            jid = f"job-hud-{int(datetime.now(timezone.utc).timestamp())}"
            queue_job(jid, "hud-operator-scope", "reconciliation")
            claimed = claim_job()
            if claimed:
                update_job_state(claimed, "validated")
                update_job_state(claimed, "approved")
                update_job_state(claimed, "completed")
            self._send_json({"job_id": jid, "claimed": claimed, "final_state": "completed"})

        elif self.path == "/api/quarantine/repair":
            row_idx = int(body.get("row_idx", body.get("row", 0)))
            inv_id = body.get("invoice_id")
            amt = body.get("amount")
            dt = body.get("date")
            auto_rec = bool(body.get("auto_recover", False))
            auto_all = bool(body.get("auto_recover_all", False))
            res = repair_quarantine_row(row_idx, invoice_id=inv_id, amount=amt, date=dt,
                                        auto_recover=auto_rec, auto_recover_all=auto_all)
            status_code = 400 if res.get("status") == "error" else 200
            self._send_json(res, status_code)

        elif self.path == "/api/quarantine/reset":
            self._send_json(reset_quarantine_fixture())

        elif self.path == "/api/gtm-queue/review":
            stage_path = os.path.join(GTM_DIR, "staged_outreach.json")
            idx = int(body.get("index", -1))
            new_status = body.get("status", "needs_review")
            if new_status in {"needs_review", "approved", "rejected"} and os.path.exists(stage_path):
                with open(stage_path, "r", encoding="utf-8") as f:
                    drafts = json.load(f)
                if 0 <= idx < len(drafts):
                    drafts[idx]["status"] = new_status
                    with open(stage_path, "w", encoding="utf-8") as f:
                        json.dump(drafts, f, indent=2)
            self._send_json({"updated": True})

        elif self.path == "/api/alerts/dispatch":
            from smtp_alert_relay import dispatch_pending_alerts
            res = dispatch_pending_alerts()
            self._send_json(res)
        elif self.path == "/api/assistant":
            from hud.omnibus import query_project_assistant
            self._send_json(query_project_assistant(str(body.get("query", "")), str(body.get("scope", "all"))))
        elif self.path == "/api/jev-decide":
            from hud.omnibus import evaluate_jev_system_one
            self._send_json(evaluate_jev_system_one(body.get("state", {}), body.get("questions", {})))
        elif self.path == "/api/jev-rung":
            from hud.omnibus import evaluate_jev_trading_rung
            self._send_json(evaluate_jev_trading_rung(body.get("judgments", {}), bool(body.get("hard_risk_breach", False))))
        elif self.path == "/api/guardrail/bash":
            from hud.jev_guard import check_bash_command
            cmd = str(body.get("command", ""))
            verdict = check_bash_command(cmd)
            self._send_json({
                "allowed": verdict.allowed,
                "command": verdict.command,
                "risk_score": verdict.risk_score,
                "reason": verdict.reason,
                "irreversible": verdict.irreversible,
                "notice": verdict.notice,
            })
        elif self.path == "/api/jev-cheap-read":
            from hud.jev_cheap_read import ask_jev_file_bool, ask_jev_file_choice, ask_jev_file_score
            mode = str(body.get("mode", "bool")).strip().lower()
            path = str(body.get("path", ""))
            question = str(body.get("question", ""))
            if mode == "bool":
                self._send_json(ask_jev_file_bool(path, question, str(body.get("yes_criteria", "")), str(body.get("no_criteria", ""))))
            elif mode == "choice":
                opts = body.get("options", [])
                self._send_json(ask_jev_file_choice(path, question, [str(x) for x in opts] if isinstance(opts, list) else []))
            elif mode == "score":
                lvs = body.get("levels", ["low", "moderate", "high", "strict"])
                self._send_json(ask_jev_file_score(path, question, [str(x) for x in lvs] if isinstance(lvs, list) else ["low", "high"]))
            else:
                self._send_json({"error": "Unsupported cheap-read mode"}, 400)
        elif self.path == "/api/jev-multi-file":
            from hud.jev_multi_file import ask_jev_files, pick_first_file, scout_and_pick
            mode = str(body.get("mode", "scout")).strip().lower()
            targets = body.get("targets", "second-brain")
            question = str(body.get("question", ""))
            if mode == "ask_files":
                self._send_json(ask_jev_files(targets, body.get("questions") or question))
            elif mode == "pick_first":
                cands = targets if isinstance(targets, list) else [t.strip() for t in str(targets).split(",") if t.strip()]
                self._send_json(pick_first_file([str(x) for x in cands], question))
            elif mode == "scout":
                self._send_json(scout_and_pick(targets, question))
            else:
                self._send_json({"error": "Unsupported multi-file mode"}, 400)
        elif self.path == "/api/jev-agentic":
            from hud.jev_agentic import ask_jev, triage_failure, judge_diff, gate_plan
            mode = str(body.get("mode", "default")).strip().lower()
            state = body.get("state")
            paths = body.get("paths")
            command = body.get("command")
            questions = body.get("questions")
            if mode == "triage":
                self._send_json(triage_failure(state or "execution_failure", command=command, candidate_paths=paths))
            elif mode == "judge_diff":
                self._send_json(judge_diff(str(state or ""), target_files=paths))
            elif mode == "gate_plan":
                self._send_json(gate_plan(str(state or ""), target_paths=paths))
            else:
                self._send_json(ask_jev(state=state, paths=paths, command=command, questions=questions))
        elif self.path == "/api/jev-composite-score":
            from hud.jev_composite_gate import evaluate_composite_score
            self._send_json(evaluate_composite_score(
                target_kind=str(body.get("target_kind", "gtm_outreach")),
                target_data=body.get("target_data"),
                weights_override=body.get("weights"),
            ))
        elif self.path == "/api/jev-confidence-gate":
            from hud.jev_composite_gate import evaluate_confidence_gate
            self._send_json(evaluate_confidence_gate(
                action_type=str(body.get("action_type", "bash_gate")),
                command_or_target=str(body.get("target") or body.get("command") or "ls -la"),
                context=body.get("context"),
            ))
        elif self.path == "/api/jev-e2e":
            from hud.jev_e2e_pipeline import run_e2e_invoice_to_gtm_pipeline
            self._send_json(run_e2e_invoice_to_gtm_pipeline(
                invoice_fixture=str(body.get("invoice_fixture", "adversarial_fixture.csv")),
                stage_to_outbox=bool(body.get("stage_to_outbox", True)),
            ))
        elif self.path == "/api/cortex/auto-accept":
            global _CORTEX_AUTO_ACCEPT
            if isinstance(body, dict) and "enabled" in body:
                _CORTEX_AUTO_ACCEPT = bool(body["enabled"])
            else:
                _CORTEX_AUTO_ACCEPT = not _CORTEX_AUTO_ACCEPT
            notify_telemetry_event()
            self._send_json({"status": "ok", "auto_accept_enabled": _CORTEX_AUTO_ACCEPT})
        elif self.path == "/api/memory/task/complete":
            from hud.shared_memory import get_shared_memory_store
            store = get_shared_memory_store()
            rec = store.record_task_completion(
                agent_id=str(body.get("agent_id", "sub-agent")),
                task_id=str(body.get("task_id", f"task-sstm-{int(time.time()*1000)}")),
                task_type=str(body.get("task_type", "general")),
                status=str(body.get("status", "completed")),
                input_summary=body.get("input_summary", {}),
                output_summary=body.get("output_summary", {}),
                artifacts=body.get("artifacts", []),
                duration_ms=float(body.get("duration_ms", 0.0)),
                sync_vault_now=bool(body.get("sync_vault_now", True))
            )
            notify_telemetry_event()
            self._send_json({"status": "recorded", "task": rec.to_dict()})
        elif self.path == "/api/memory/agent/heartbeat":
            from hud.shared_memory import get_shared_memory_store
            store = get_shared_memory_store()
            ag = store.update_agent_heartbeat(
                agent_id=str(body.get("agent_id", "sub-agent")),
                role=body.get("role"),
                operational_state=str(body.get("operational_state", "idle")),
                current_task_id=body.get("current_task_id"),
                capabilities=body.get("capabilities"),
                meta=body.get("meta")
            )
            notify_telemetry_event()
            self._send_json({"status": "updated", "agent": ag.to_dict()})
        elif self.path == "/api/memory/blackboard":
            from hud.shared_memory import get_shared_memory_store
            store = get_shared_memory_store()
            entry = store.set_blackboard_key(
                key=str(body.get("key", "")),
                value=body.get("value"),
                writer_agent_id=str(body.get("writer_agent_id", "operator")),
                ttl_seconds=float(body["ttl_seconds"]) if body.get("ttl_seconds") is not None else None
            )
            notify_telemetry_event()
            self._send_json({"status": "set", "entry": entry.to_dict()})
        elif self.path == "/api/memory/sync-obsidian":
            from hud.shared_memory import get_shared_memory_store
            store = get_shared_memory_store()
            res = store.sync_to_obsidian_vault()
            notify_telemetry_event()
            self._send_json(res)
        elif self.path.startswith("/api/gateway/"):
            from hud.gateway import (
                verify_gateway_request, GatewayAuthError,
                execute_gateway_rpc, execute_task_command,
                load_cron_registry, update_cron_job, trigger_cron_job, delete_cron_job,
                send_signed_rpc
            )
            start_t = time.monotonic()
            idemp_key = self.headers.get("X-Idempotency-Key") or body.get("idempotency_key")
            if idemp_key and "idempotency_key" not in body:
                body["idempotency_key"] = idemp_key

            # Inbound Hermes Webhook / RPC Callback requires strict signature verification
            if self.path == "/api/gateway/hermes":
                try:
                    verify_gateway_request(dict(self.headers), "POST", self.path, raw_body)
                except GatewayAuthError as gae:
                    self._send_json({
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": f"Unauthorized: {gae}"},
                        "status": "unauthorized"
                    }, 401)
                    return
                method = body.get("method", "")
                params = body.get("params", {})
                req_id = body.get("id")
                if idemp_key and "idempotency_key" not in params:
                    params["idempotency_key"] = idemp_key
                rpc_res = execute_gateway_rpc(method, params)
                notify_telemetry_event()
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                ack = rpc_res.get("ack")
                out = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": rpc_res.get("result"),
                    "error": rpc_res.get("error"),
                    "status": "error" if rpc_res.get("error") else "ok",
                    "ack": ack,
                    "round_trip_ms": rtt_ms
                }
                status_code = 400 if rpc_res.get("error") else 200
                ack_id = ack.get("ack_id") if ack else None
                seq_id = ack.get("sequence_id") if ack else None
                self._send_json(out, status_code, ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                return

            elif self.path == "/api/gateway/tasks":
                cmd = body.get("command") or body.get("cmd", "ping")
                params = body.get("params", body)
                if idemp_key and "idempotency_key" not in params:
                    params["idempotency_key"] = idemp_key
                dispatch_remote = bool(body.get("remote", False))

                if dispatch_remote:
                    res = send_signed_rpc(get_hermes_gateway_rpc_url(), "hermes.task.execute", {"command": cmd, **params}, idempotency_key=idemp_key)
                    notify_telemetry_event()
                    ack = res.get("ack")
                    ack_id = ack.get("ack_id") if isinstance(ack, dict) else None
                    seq_id = ack.get("sequence_id") if isinstance(ack, dict) else None
                    rtt_ms = res.get("round_trip_ms")
                    try:
                        from hud.shared_memory import get_shared_memory_store
                        get_shared_memory_store().record_task_completion(
                            agent_id="agent-hermes-gateway",
                            task_id=f"task-hermes-{seq_id or int(time.time()*1000)}",
                            task_type=cmd,
                            status="completed" if not res.get("error") else "failed",
                            input_summary={"command": cmd, "remote": True},
                            output_summary={"result": str(res.get("result", res))[:200]},
                            duration_ms=float(rtt_ms or 0.0)
                        )
                    except Exception:
                        pass
                    self._send_json(res, ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                else:
                    task_res = execute_task_command(cmd, params)
                    notify_telemetry_event()
                    rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                    ack = task_res.get("ack")
                    ack_id = ack.get("ack_id") if isinstance(ack, dict) else None
                    seq_id = ack.get("sequence_id") if isinstance(ack, dict) else None
                    try:
                        from hud.shared_memory import get_shared_memory_store
                        get_shared_memory_store().record_task_completion(
                            agent_id="agent-supervisor",
                            task_id=f"task-local-{seq_id or int(time.time()*1000)}",
                            task_type=cmd,
                            status="completed" if not task_res.get("error") else "failed",
                            input_summary={"command": cmd, "remote": False},
                            output_summary={"result": str(task_res.get("result", task_res))[:200]},
                            duration_ms=float(rtt_ms or 0.0)
                        )
                    except Exception:
                        pass
                    self._send_json({"status": "ok", "task": task_res, "ack": ack, "round_trip_ms": rtt_ms},
                                    ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                return

            elif self.path == "/api/gateway/crons":
                action = body.get("action", "update")
                cron_id = body.get("id") or body.get("cron_id") or body.get("job_id")
                try:
                    if action == "trigger":
                        dispatch_remote = bool(body.get("remote", False))
                        if dispatch_remote:
                            res = send_signed_rpc(get_hermes_gateway_rpc_url(), "hermes.cron.trigger", {"id": cron_id}, idempotency_key=idemp_key)
                            notify_telemetry_event()
                            self._send_json(res)
                        else:
                            outcome = trigger_cron_job(cron_id)
                            notify_telemetry_event()
                            rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                            seq_id = outcome.get("sequence_id")
                            self._send_json({"status": "ok", "triggered": outcome, "round_trip_ms": rtt_ms}, seq_id=seq_id, rtt_ms=rtt_ms)
                    elif action == "delete":
                        del_ok = delete_cron_job(cron_id)
                        notify_telemetry_event()
                        rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                        self._send_json({"status": "ok" if del_ok else "not_found", "deleted": del_ok, "round_trip_ms": rtt_ms}, rtt_ms=rtt_ms)
                    else:
                        upd = update_cron_job(cron_id, body)
                        notify_telemetry_event()
                        rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                        seq_id = upd.get("sequence_id")
                        self._send_json({"status": "ok", "cron": upd, "round_trip_ms": rtt_ms}, seq_id=seq_id, rtt_ms=rtt_ms)
                except Exception as err:
                    self._send_json({"error": str(err), "status": "error"}, 400)
                return

            elif self.path == "/api/gateway/board/sync":
                dispatch_remote = bool(body.get("remote", False))
                if idemp_key and "idempotency_key" not in body:
                    body["idempotency_key"] = idemp_key
                if dispatch_remote:
                    res = send_signed_rpc(get_hermes_gateway_rpc_url(), "hermes.board.sync", body, idempotency_key=idemp_key)
                    notify_telemetry_event()
                    ack = res.get("ack")
                    ack_id = ack.get("ack_id") if isinstance(ack, dict) else None
                    seq_id = ack.get("sequence_id") if isinstance(ack, dict) else None
                    rtt_ms = res.get("round_trip_ms")
                    self._send_json(res, ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                else:
                    rpc_res = execute_gateway_rpc("hermes.board.sync", body)
                    notify_telemetry_event()
                    rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                    ack = rpc_res.get("ack")
                    ack_id = ack.get("ack_id") if isinstance(ack, dict) else None
                    seq_id = ack.get("sequence_id") if isinstance(ack, dict) else None
                    out = rpc_res.get("result", rpc_res)
                    if isinstance(out, dict):
                        out["round_trip_ms"] = rtt_ms
                        if ack:
                            out["ack"] = ack
                    self._send_json(out, ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                return

            self._send_json({"error": "Unknown gateway endpoint"}, 404)
            return
        else:
            self._send_json({"error": "Unknown endpoint"}, 404)

class HUDHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == "__main__":
    host = os.environ.get("HUD_HOST", "127.0.0.1" if os.name == "nt" else "0.0.0.0")
    port = int(os.environ.get("HUD_PORT", "5050"))
    with HUDHTTPServer((host, port), HUDRequestHandler) as server:
        print("JEV Modular HUD: http://%s:%s | %s | pid=%s" % (host, port, BUILD_ID, os.getpid()), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
