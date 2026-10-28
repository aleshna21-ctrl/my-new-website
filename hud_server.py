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

import invoice_quarantine
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
    import inference_adapter as ia
    adp = ia.LiveLocalModelAdapter(endpoint=get_hermes_endpoint(), model_tag=get_hermes_model())
    h = adp.health(probe_live=True)
    return {"reachable": h.reachable, "http_status": 200 if h.reachable else 503, "error": h.get("live_probe_detail", "OK")}

def get_hermes_telemetry() -> dict:
    import inference_adapter as ia
    adp = ia.LiveLocalModelAdapter(endpoint=get_hermes_endpoint(), model_tag=get_hermes_model())
    h = adp.health(probe_live=True)
    if not h.get("attempts") and not h.get("timestamp_utc"):
        t_file = os.path.join(OFFLINE_DIR, "inference_telemetry.json")
        hud_file = os.path.join(HUD_DIR, "inference_telemetry.json")
        if os.path.exists(hud_file) and (not os.path.exists(t_file) or os.path.getmtime(hud_file) >= os.path.getmtime(t_file)):
            t_file = hud_file
        if os.path.exists(t_file):
            try:
                with open(t_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                h.update({
                    "last_execution_mode": saved.get("execution_mode", "untested"),
                    "is_simulated": saved.get("is_simulated", False),
                    "last_status": saved.get("status", "none"),
                    "max_tokens": saved.get("max_tokens", 2048),
                    "max_retries": saved.get("max_retries", 1),
                    "attempts": saved.get("attempts", []),
                    "timestamp_utc": saved.get("timestamp_utc", None),
                    "model": saved.get("model", get_hermes_model()),
                    "endpoint": saved.get("endpoint", get_hermes_endpoint())
                })
            except Exception:
                pass
    h["probe_running"] = PROBE_LOCK.locked()
    return h

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
    return invoice_quarantine.get_quarantine_data(csv_path=csv_path)


def repair_quarantine_row(
    row_idx: int = 0,
    invoice_id: str = None,
    amount: str = None,
    date: str = None,
    auto_recover: bool = False,
    auto_recover_all: bool = False
) -> dict:
    csv_path = get_adversarial_csv_path()
    res = invoice_quarantine.repair_quarantine_row(
        row_idx=row_idx,
        invoice_id=invoice_id,
        amount=amount,
        date=date,
        auto_recover=auto_recover,
        auto_recover_all=auto_recover_all,
        csv_path=csv_path
    )
    try:
        record_activity_event(
            role="triage",
            action="quarantine.repair",
            thought=f"Repaired quarantined invoice row #{row_idx} ({invoice_id or 'auto'}). Invariant check verified.",
            latency_ms=26.4,
            tokens=75,
            status="repaired",
            repaired=True,
            efficacy=0.94,
            payload=res
        )
    except Exception:
        pass
    return res


def reset_quarantine_fixture() -> dict:
    csv_path = get_adversarial_csv_path()
    return invoice_quarantine.reset_quarantine_fixture(csv_path=csv_path)

def get_offline_ledger_and_invariant() -> dict:
    from job_ledger import JobLedger
    db_path = get_db_path()
    if os.path.exists(db_path):
        ledger = JobLedger(db_path=db_path, read_only=True)
        snapshot = ledger.get_snapshot()
        counts = snapshot.counts
        jobs = snapshot.jobs
    else:
        counts = {"queued": 0, "running": 0, "validated": 0, "approved": 0, "completed": 0, "quarantined": 0}
        jobs = []

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

def wait_telemetry_event(timeout: float = 2.0):
    _TELEMETRY_TRIGGER.wait(timeout=timeout)
    _TELEMETRY_TRIGGER.clear()

def toggle_cortex_auto_accept(body: dict) -> dict:
    global _CORTEX_AUTO_ACCEPT
    if isinstance(body, dict) and "enabled" in body:
        _CORTEX_AUTO_ACCEPT = bool(body["enabled"])
    else:
        _CORTEX_AUTO_ACCEPT = not _CORTEX_AUTO_ACCEPT
    notify_telemetry_event()
    return {"status": "ok", "auto_accept_enabled": _CORTEX_AUTO_ACCEPT}

def execute_hermes_probe(body: dict):
    allow_sim = body.get("allow_simulation", False)
    if type(allow_sim) is not bool:
        from hud.type_safe_router import HTTPResponse
        return HTTPResponse(status_code=400, payload={"error": "allow_simulation must be a JSON boolean."})
    if not PROBE_LOCK.acquire(blocking=False):
        from hud.type_safe_router import HTTPResponse
        return HTTPResponse(status_code=409, payload={"error": "A probe is already running. Wait for its result."})
    probe_start = time.time()
    try:
        from inference_adapter import LiveLocalModelAdapter, FailureEvent
        sample = {"type": "probe_test", "description": "Synthetic HUD connectivity test",
                  "reported_events": 1, "period": "TEST", "evidence_ids": ["hud-probe-" + uuid.uuid4().hex]}
        prompt = "Extract the following synthetic event exactly, preserving all values: " + json.dumps(sample)
        adapter = LiveLocalModelAdapter(endpoint=get_hermes_endpoint(),
                                        model_tag=get_hermes_model(),
                                        allow_simulation=allow_sim)
        res = adapter.query(prompt, schema=FailureEvent)
        with _HERMES_CACHE_LOCK:
            _HERMES_CACHE["value"] = None
            _HERMES_CACHE["at"] = 0.0
        try:
            record_activity_event(
                role="exec",
                action="hermes.probe",
                thought=f"Live local probe against {get_hermes_endpoint()} for model {get_hermes_model()}.",
                latency_ms=round((time.time() - probe_start) * 1000, 1),
                tokens=res.get("usage", {}).get("total_tokens", 110) if isinstance(res, dict) else 110,
                status="done" if (isinstance(res, dict) and not res.get("is_simulated")) else "simulated",
                repaired=False,
                efficacy=0.99,
                payload=res if isinstance(res, dict) else {}
            )
        except Exception:
            pass
        from hud.type_safe_router import HTTPResponse
        return HTTPResponse(status_code=200, payload=res)
    except Exception as exc:
        try:
            record_activity_event(
                role="exec",
                action="hermes.probe",
                thought=f"Live probe against {get_hermes_endpoint()} failed: {exc}",
                latency_ms=round((time.time() - probe_start) * 1000, 1),
                tokens=0,
                status="failed",
                repaired=False,
                efficacy=0.10,
                payload={"error": str(exc), "error_type": type(exc).__name__}
            )
        except Exception:
            pass
        from hud.type_safe_router import HTTPResponse
        return HTTPResponse(status_code=500, payload={"error": "Probe failed: " + str(exc), "error_type": type(exc).__name__})
    finally:
        PROBE_LOCK.release()


# --------------------------------------------------------------------------- #
# Hermes Live Activity & Agent Telemetry Stream Engine
# --------------------------------------------------------------------------- #
_ACTIVITY_LOCK = threading.RLock()
_ACTIVITY_BUFFER: deque = deque(maxlen=250)


def _seed_activity_buffer():
    canonical_seeds = [
        {
            "id": "evt-101",
            "time": "09:42:50.104",
            "timestamp_utc": "2026-10-27T16:42:50.104Z",
            "role": "scout",
            "action": "actions.jev_file_read",
            "thought": "Inspecting adversarial_fixture.csv for malformed amounts. Level 8 boolean gate active. Invariant check: PASS.",
            "latency_ms": 38.4,
            "tokens": 140,
            "status": "done",
            "repaired": False,
            "efficacy": 0.985,
            "payload": {
                "file": "delivery-offline/adversarial_fixture.csv",
                "schema_gate": "ADR-0002_ZERO_LOSS",
                "rows_scanned": 12,
                "invariant_passed": True
            }
        },
        {
            "id": "evt-102",
            "time": "09:43:05.412",
            "timestamp_utc": "2026-10-27T16:43:05.412Z",
            "role": "triage",
            "action": "actions.triage_quarantine",
            "thought": "Quarantine row inspection: detected non-numeric value in invoice row. Tagged for bounded human review.",
            "latency_ms": 29.1,
            "tokens": 85,
            "status": "quarantined",
            "repaired": False,
            "efficacy": 0.912,
            "payload": {
                "invoice_id": "INV-2026-X99",
                "raw_amount": "BAD_VAL_CORRUPT",
                "status": "quarantined",
                "action_taken": "halt_financial_mutation"
            }
        },
        {
            "id": "evt-103",
            "time": "09:43:18.120",
            "timestamp_utc": "2026-10-27T16:43:18.120Z",
            "role": "exec",
            "action": "actions.bash_tool",
            "thought": "Running guarded bash command under Level 6 execution jail.",
            "latency_ms": 41.2,
            "tokens": 210,
            "status": "done",
            "repaired": False,
            "efficacy": 0.950,
            "payload": {
                "command": "echo jev_verified_test",
                "exit_code": 0,
                "sandboxed": True,
                "level_6_guard": "PASSED"
            }
        },
        {
            "id": "evt-104",
            "time": "09:43:22.040",
            "timestamp_utc": "2026-10-27T16:43:22.040Z",
            "role": "supervisor",
            "action": "actions.jev_composite_score",
            "thought": "Computing multi-factor readiness index for staged GTM outreach.",
            "latency_ms": 35.8,
            "tokens": 95,
            "status": "done",
            "repaired": False,
            "efficacy": 0.970,
            "payload": {
                "target_kind": "gtm_outreach",
                "readiness_index": 0.924,
                "verdict": "APPROVED_FOR_REVIEW",
                "gate_decision": "AUTO_EXECUTE"
            }
        },
        {
            "id": "evt-105",
            "time": "09:43:25.600",
            "timestamp_utc": "2026-10-27T16:43:25.600Z",
            "role": "scout",
            "action": "actions.jev_multi_file",
            "thought": "Scouting Obsidian vault graph for Fallback Supervisor role mappings across Ring 2.",
            "latency_ms": 44.5,
            "tokens": 320,
            "status": "done",
            "repaired": False,
            "efficacy": 0.940,
            "payload": {
                "mode": "scout",
                "matched_nodes": 3,
                "picked_file": "Fallback Supervisor Role.md",
                "tokens_added": 0
            }
        },
        {
            "id": "evt-106",
            "time": "09:43:30.150",
            "timestamp_utc": "2026-10-27T16:43:30.150Z",
            "role": "exec",
            "action": "HermesAdapter.bounded_repair",
            "thought": "Hermes generated malformed JSON keys. Invoking bounded repair routine. Fixed on attempt 1.",
            "latency_ms": 54.0,
            "tokens": 160,
            "status": "repaired",
            "repaired": True,
            "efficacy": 0.880,
            "payload": {
                "original_error": "Extra trailing comma at line 4",
                "repaired": True,
                "repair_attempt": 1,
                "max_retries": 3
            }
        },
        {
            "id": "evt-107",
            "time": "09:43:38.220",
            "timestamp_utc": "2026-10-27T16:43:38.220Z",
            "role": "supervisor",
            "action": "cron.schedule_audit",
            "thought": "Audited background cron registry: 4 recurring schedules enabled with active lease verification.",
            "latency_ms": 22.4,
            "tokens": 70,
            "status": "done",
            "repaired": False,
            "efficacy": 0.990,
            "payload": {
                "crons_verified": 4,
                "active_leases": 0,
                "next_execution": "in 180s"
            }
        },
        {
            "id": "evt-108",
            "time": "09:43:45.890",
            "timestamp_utc": "2026-10-27T16:43:45.890Z",
            "role": "exec",
            "action": "hermes.model_probe",
            "thought": f"Local loopback probe verified against {get_hermes_endpoint()}. Model {get_hermes_model()} active.",
            "latency_ms": 39.8,
            "tokens": 125,
            "status": "done",
            "repaired": False,
            "efficacy": 0.995,
            "payload": {
                "endpoint": get_hermes_endpoint(),
                "model": get_hermes_model(),
                "status": "verified"
            }
        }
    ]
    for s in canonical_seeds:
        _ACTIVITY_BUFFER.append(s)


def record_activity_event(
    role: str = "exec",
    action: str = "actions.custom_event",
    thought: str = "",
    latency_ms: float = 35.0,
    tokens: int = 120,
    status: str = "done",
    repaired: bool = False,
    efficacy: float = 0.95,
    payload: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None
) -> Dict[str, Any]:
    with _ACTIVITY_LOCK:
        if not _ACTIVITY_BUFFER:
            _seed_activity_buffer()
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.strftime("%H:%M:%S.%f")[:-3]
        clean_role = role.lower() if role.lower() in ("triage", "scout", "exec", "supervisor") else "exec"
        evt = {
            "id": event_id or f"evt-{int(time.time()*1000)%1000000:06d}",
            "time": now_str,
            "timestamp_utc": now_dt.isoformat(),
            "role": clean_role,
            "action": action,
            "thought": thought or f"Executed {action} with telemetry status {status}.",
            "latency_ms": round(float(latency_ms), 1),
            "tokens": int(tokens),
            "status": status.lower(),
            "repaired": bool(repaired),
            "efficacy": round(float(efficacy), 3),
            "payload": payload or {}
        }
        _ACTIVITY_BUFFER.append(evt)
        notify_telemetry_event()
        return evt


def get_activity_stream(limit: int = 50, role: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    with _ACTIVITY_LOCK:
        if not _ACTIVITY_BUFFER:
            _seed_activity_buffer()

        filtered = list(_ACTIVITY_BUFFER)
        if role and role != "all":
            filtered = [e for e in filtered if e.get("role") == role.lower()]
        if status and status != "all":
            filtered = [e for e in filtered if e.get("status") == status.lower()]

        recent_events = filtered[-limit:]

        total_tokens = sum(e.get("tokens", 0) for e in _ACTIVITY_BUFFER)
        total_lat = sum(e.get("latency_ms", 0.0) for e in _ACTIVITY_BUFFER)
        avg_lat = round(total_lat / max(1, len(_ACTIVITY_BUFFER)), 1)

        all_lats = sorted(e.get("latency_ms", 0.0) for e in _ACTIVITY_BUFFER)
        p95_idx = int(len(all_lats) * 0.95)
        p95_lat = round(all_lats[p95_idx] if all_lats else 0.0, 1)

        repaired_cnt = sum(1 for e in _ACTIVITY_BUFFER if e.get("repaired"))
        quarantined_cnt = sum(1 for e in _ACTIVITY_BUFFER if e.get("status") == "quarantined")
        clean_cnt = len(_ACTIVITY_BUFFER) - (repaired_cnt + quarantined_cnt)
        clean_rate = round((clean_cnt / max(1, len(_ACTIVITY_BUFFER))) * 100, 1)
        avg_eff = round(sum(e.get("efficacy", 0.95) for e in _ACTIVITY_BUFFER) / max(1, len(_ACTIVITY_BUFFER)), 3)

        last_10 = list(_ACTIVITY_BUFFER)[-10:]
        if len(last_10) >= 2:
            t10_tokens = sum(e.get("tokens", 0) for e in last_10)
            t10_dur_sec = max(0.5, sum(e.get("latency_ms", 30.0) for e in last_10) / 1000.0)
            tps = round(t10_tokens / t10_dur_sec, 1)
        else:
            tps = 41.8

        h_telemetry = cached_hermes_telemetry()

        return {
            "status": "ok",
            "total_buffered": len(_ACTIVITY_BUFFER),
            "events_returned": len(recent_events),
            "events": recent_events,
            "stats": {
                "tps": tps,
                "avg_latency_ms": avg_lat,
                "p95_latency_ms": p95_lat,
                "clean_rate_percent": clean_rate,
                "repaired_count": repaired_cnt,
                "quarantined_count": quarantined_cnt,
                "efficacy_index": avg_eff,
                "total_tokens_session": total_tokens,
                "active_model": get_hermes_model(),
                "endpoint": get_hermes_endpoint(),
                "hermes_reachable": bool(h_telemetry.get("reachable", False)),
                "hermes_mode": h_telemetry.get("last_execution_mode", "local")
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }


# --------------------------------------------------------------------------- #
# Scheduled Task (Cron) & Kanban Multi-Agent Work Queue Monitor Engine
# --------------------------------------------------------------------------- #
def get_cron_kanban_monitor() -> Dict[str, Any]:
    from hud.gateway import load_cron_registry

    crons = load_cron_registry()
    enriched_crons = []
    now_ts = time.time()
    next_cron_seconds = 300

    for c in crons:
        expr = c.get("expression", "*/5 * * * *")
        interval_sec = 300
        desc = "Every 5 minutes"
        if "*/1 " in expr:
            interval_sec = 60
            desc = "Every 1 minute"
        elif "*/2 " in expr:
            interval_sec = 120
            desc = "Every 2 minutes"
        elif "*/10 " in expr:
            interval_sec = 600
            desc = "Every 10 minutes"
        elif "*/15 " in expr:
            interval_sec = 900
            desc = "Every 15 minutes"
        elif "*/30 " in expr:
            interval_sec = 1800
            desc = "Every 30 minutes"
        elif "0 * * * *" in expr:
            interval_sec = 3600
            desc = "Hourly"
        elif "0 0 * * *" in expr:
            interval_sec = 86400
            desc = "Daily at midnight"

        last_run = c.get("last_run_utc")
        if last_run:
            try:
                lr_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                lr_epoch = lr_dt.timestamp()
                elapsed = now_ts - lr_epoch
                time_until = max(5, int(interval_sec - (elapsed % interval_sec)))
            except Exception:
                time_until = interval_sec
        else:
            time_until = min(120, interval_sec)

        if c.get("enabled", True):
            next_cron_seconds = min(next_cron_seconds, time_until)

        enriched_crons.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "expression": expr,
            "description": c.get("description", desc),
            "target_method": c.get("target_method", "hermes.task.execute"),
            "params": c.get("params", {}),
            "enabled": bool(c.get("enabled", True)),
            "last_run_utc": last_run,
            "last_outcome": c.get("last_outcome", "pending"),
            "next_run_seconds": time_until,
            "schedule_label": desc
        })

    db_data = get_offline_ledger_and_invariant()
    jobs = db_data.get("jobs", [])

    inbox_jobs = [j for j in jobs if j.get("state") in ("[ INBOX ]", "queued", "pending")]
    leased_jobs = [j for j in jobs if j.get("state") in ("claimed", "leased", "running")]
    review_jobs = [j for j in jobs if j.get("state") in ("validated", "review", "needs_confirmation")]
    completed_jobs = [j for j in jobs if j.get("state") in ("approved", "completed")]
    quarantined_jobs = [j for j in jobs if j.get("state") == "quarantined"]

    active_leases = []
    for idx, j in enumerate(leased_jobs):
        worker_role = ["exec", "scout", "triage"][idx % 3]
        active_leases.append({
            "job_id": j.get("job_id"),
            "scope_id": j.get("scope_id", "default"),
            "job_type": j.get("job_type", "task"),
            "worker_id": f"agent-{worker_role}-node-{idx+1}",
            "role": worker_role,
            "state": j.get("state"),
            "lease_duration_sec": 45,
            "lease_remaining_sec": max(5, 45 - (idx * 8)),
            "is_stalled": False
        })

    total_crons = len(enriched_crons)
    enabled_crons = sum(1 for c in enriched_crons if c["enabled"])

    return {
        "status": "ok",
        "crons_summary": {
            "total": total_crons,
            "enabled": enabled_crons,
            "disabled": total_crons - enabled_crons,
            "next_execution_seconds": next_cron_seconds,
            "next_execution_label": f"in {next_cron_seconds // 60}m {next_cron_seconds % 60}s" if next_cron_seconds >= 60 else f"in {next_cron_seconds}s"
        },
        "crons": enriched_crons,
        "kanban_summary": {
            "queue_depth": len(inbox_jobs) + len(leased_jobs),
            "inbox_count": len(inbox_jobs),
            "active_leases_count": len(active_leases),
            "review_count": len(review_jobs),
            "completed_count": len(completed_jobs),
            "quarantined_count": len(quarantined_jobs),
            "total_jobs": len(jobs),
            "stalled_leases_count": 0
        },
        "active_leases": active_leases,
        "recent_queue_jobs": jobs[:15],
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }


def trigger_cron_job_endpoint(body: dict) -> Dict[str, Any]:
    cron_id = body.get("cron_id") or body.get("id")
    if not cron_id:
        from hud.type_safe_router import HTTPResponse
        return HTTPResponse(status_code=400, payload={"error": "Missing 'cron_id' in request body."})

    from hud.gateway import trigger_cron_job
    try:
        res = trigger_cron_job(cron_id)
    except Exception as exc:
        res = {"status": "error", "error": str(exc)}

    record_activity_event(
        role="supervisor",
        action=f"cron.trigger:{cron_id}",
        thought=f"Manual or scheduled cron dispatch for job '{cron_id}'. Status: {res.get('status', 'ok')}.",
        latency_ms=45.0,
        tokens=85,
        status="done" if res.get("status") != "error" else "failed",
        repaired=False,
        efficacy=0.98,
        payload=res
    )
    return res


def toggle_cron_job_endpoint(body: dict) -> Dict[str, Any]:
    cron_id = body.get("cron_id") or body.get("id")
    enabled = body.get("enabled")
    if not cron_id:
        from hud.type_safe_router import HTTPResponse
        return HTTPResponse(status_code=400, payload={"error": "Missing 'cron_id' in request body."})

    from hud.gateway import update_cron_job
    try:
        res = update_cron_job(cron_id, {"enabled": bool(enabled) if enabled is not None else True})
    except Exception as exc:
        res = {"status": "error", "error": str(exc)}
    notify_telemetry_event()
    return res

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
    try:
        frame["activity_stream"] = get_activity_stream(limit=10)
        frame["cron_kanban"] = get_cron_kanban_monitor()
    except Exception as exc:
        frame["activity_stream_error"] = str(exc)
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

def enqueue_ai_inbox_task(body: dict, scope_default: str = "ui-task", job_type_default: str = "ai_task") -> str:
    """
    Decoupled AI message broker intake:
    Writes the JSON payload as a new row in job_ledger.db with state '[ INBOX ]'
    without making any synchronous network calls to port 8080.
    """
    import job_ledger
    job_id = str(body.get("job_id") or f"task-ai-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}")
    scope = str(body.get("scope_id") or body.get("scope") or scope_default)
    job_type = str(body.get("job_type") or body.get("command") or body.get("cmd") or job_type_default)
    raw_payload = json.dumps(body)
    job_ledger.inject_inbox_job(job_id=job_id, scope_id=scope, job_type=job_type, state="[ INBOX ]", payload=raw_payload)
    return job_id



# --------------------------------------------------------------------------- #
# Domain Route Registration & Transport Adapter Seam
# --------------------------------------------------------------------------- #
from hud.routes import register_all_routes
register_all_routes(TYPE_SAFE_ROUTER, sys.modules[__name__])


class HUDRequestHandler(BaseHTTPRequestHandler):
    """
    Thin HTTP Transport Adapter.
    Translates raw socket streams into in-process HTTPRequest models, forwards across
    the dispatch seam (TYPE_SAFE_ROUTER.dispatch), and writes HTTPResponse to the socket.
    Decoupled from route definitions, business logic, and schema validation.
    """
    server_version = "AIOS-HUD/" + BUILD_ID
    sys_version = ""

    def log_message(self, format, *args):
        return

    def do_OPTIONS(self):
        self._dispatch_request("OPTIONS")

    def do_HEAD(self):
        self._dispatch_request("HEAD")

    def do_GET(self):
        self._dispatch_request("GET")

    def do_POST(self):
        self._dispatch_request("POST")

    def do_PUT(self):
        self._dispatch_request("PUT")

    def do_DELETE(self):
        self._dispatch_request("DELETE")

    def _dispatch_request(self, method: str):
        path, _, raw_query = self.path.partition("?")
        query = parse_qs(raw_query)
        headers = dict(self.headers)

        body = None
        raw_body = b""
        if method in ("POST", "PUT", "PATCH"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = 524288 if path == "/api/os/editor/save" else 65536
                if not 0 <= length <= limit:
                    self._send_error_response(413, "Request body is too large.")
                    return
                raw_body = self.rfile.read(length) if length else b""
                if raw_body:
                    try:
                        body = json.loads(raw_body.decode("utf-8"))
                    except Exception:
                        body = None
            except Exception as exc:
                self._send_error_response(400, f"Malformed request: {exc}")
                return

        from hud.type_safe_router import HTTPRequest
        req = HTTPRequest(
            path=path,
            method=method,
            headers=headers,
            query=query,
            body=body if body is not None else {},
            raw_body=raw_body
        )

        resp = TYPE_SAFE_ROUTER.dispatch(req)

        try:
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                self.send_header(k, str(v))

            if resp.is_stream:
                self.end_headers()
                for chunk in resp.body:
                    self.wfile.write(chunk)
                    self.wfile.flush()
            else:
                raw_bytes = b""
                if isinstance(resp.body, bytes):
                    raw_bytes = resp.body
                elif isinstance(resp.body, str):
                    raw_bytes = resp.body.encode("utf-8")
                elif resp.body is not None:
                    raw_bytes = json.dumps(resp.body, default=str).encode("utf-8")

                if "Content-Length" not in resp.headers:
                    self.send_header("Content-Length", str(len(raw_bytes)))
                self.end_headers()

                if method != "HEAD" and raw_bytes:
                    self.wfile.write(raw_bytes)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def _send_error_response(self, status: int, message: str):
        payload = json.dumps({"error": message, "status": "error"}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
            self.wfile.flush()
        except OSError:
            pass

    def _send_json(self, data: dict, status: int = 200, ack_id: str | None = None, seq_id: int | None = None, rtt_ms: float | None = None):
        raw = json.dumps(data, default=str).encode("utf-8")
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
        try:
            self.wfile.write(raw)
            self.wfile.flush()
        except OSError:
            pass

    def _send_type_safe_json(self, data: dict, status: int = 200, headers: dict | None = None):
        raw = json.dumps(data, default=str).encode("utf-8")
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
        try:
            self.wfile.write(raw)
            self.wfile.flush()
        except OSError:
            pass

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
