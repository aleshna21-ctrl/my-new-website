import os
import csv
import json
import sqlite3
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import sys
import socket
import threading
import time
import uuid
from urllib.parse import parse_qs

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

for p in (OFFLINE_DIR, GTM_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

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
        return "http://127.0.0.1:8080/v1/models"

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
    if not os.path.exists(t_file):
        t_file = os.path.join(HUD_DIR, "inference_telemetry.json")
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

def get_offline_ledger_and_invariant() -> dict:
    db_path = os.path.join(OFFLINE_DIR, "job_ledger.db")
    jobs = []
    counts = {"queued": 0, "running": 0, "validated": 0, "approved": 0, "completed": 0, "quarantined": 0}
    if os.path.exists(db_path):
        uri = f"file:{db_path}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT job_id, scope_id, job_type, state, attempt_count, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 25")
                for r in cur.fetchall():
                    d = dict(r)
                    jobs.append(d)
                    st = d.get("state", "")
                    if st in counts:
                        counts[st] += 1
        except Exception:
            pass

    csv_path = os.path.join(OFFLINE_DIR, "adversarial_fixture.csv")
    metrics = {"received": 0, "accepted": 0, "quarantined": 0, "duplicates": 0}
    quarantined_rows = []
    if os.path.exists(csv_path):
        seen = set()
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [name.strip() if name else name for name in reader.fieldnames]
            for idx, row in enumerate(reader, start=1):
                metrics["received"] += 1
                inv_id = (row.get("InvoiceID") or "").strip()
                amt_str = (row.get("Amount") or "").strip()
                if inv_id in seen:
                    metrics["duplicates"] += 1
                    continue
                if not inv_id or not amt_str or amt_str.startswith("-") or not amt_str.replace(".", "", 1).isdigit():
                    metrics["quarantined"] += 1
                    quarantined_rows.append({"row": idx, "invoice_id": inv_id or "MISSING", "raw_amount": amt_str})
                else:
                    seen.add(inv_id)
                    metrics["accepted"] += 1

    invariant_ok = (metrics["received"] == (metrics["accepted"] + metrics["quarantined"] + metrics["duplicates"]))
    return {
        "counts": counts,
        "jobs": jobs,
        "invariant": {
            "passed": invariant_ok,
            "formula": f"{metrics['received']} == {metrics['accepted']} + {metrics['quarantined']} + {metrics['duplicates']}",
            "metrics": metrics,
            "quarantined_samples": quarantined_rows[:10]
        }
    }

def get_gtm_queue() -> dict:
    stage_path = os.path.join(GTM_DIR, "staged_outreach.json")
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
    log_path = os.path.join(GTM_DIR, "alert_dispatch_log.json")
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

# --------------------------------------------------------------------------- #
# AI OS dashboard: telemetry frame + board helpers (logic lives in hud/os_dashboard.py)
# --------------------------------------------------------------------------- #
_HERMES_CACHE = {"at": 0.0, "value": None}
_HERMES_CACHE_LOCK = threading.Lock()


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
    return osd.compose_frame(
        hermes=cached_hermes_telemetry(), ledger=get_offline_ledger_and_invariant(),
        gtm=get_gtm_queue(), alerts_status=get_alerts_status(),
        inbox=_read_json_file(INBOX_SNAPSHOT, {}), guard_events=_read_json_file(str(GUARDRAIL_LOG), []),
        e2e_events=get_recent_e2e_events(1), board=board, plan=plan, stats=osd.static_stats(),
        mtimes=mtimes, now=now,
        server={"pid": os.getpid(), "build": BUILD_ID, "uptime_min": int((time.time() - SERVER_STARTED) // 60)},
    )


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

    def _send_json(self, data: dict, status: int = 200):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(raw)

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
        Each connection lives 10 minutes, then the browser's EventSource reconnects."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
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
                time.sleep(2)
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
                self._send_json(os_board_payload())
            elif path == "/api/os/editor/save":
                self._send_json(osd.editor_save(str(body.get("name", "")), body.get("text"), body.get("base_sha256") or None))
            elif path == "/api/os/obsidian/note":
                self._send_json(osd.create_vault_note(body))
            elif path == "/api/os/obsidian/rescan":
                osd.invalidate_vault_cache()
                self._send_json(os_frame().get("obsidian", {}))
            elif path == "/api/os/outbox/decide":
                from hud.gtm import decide
                decide(os.path.join(GTM_DIR, "staged_outreach.json"), str(body.get("id", "")),
                       str(body.get("revision", "")), str(body.get("decision", "")))
                self._send_json(os_outbox_payload())
            else:
                self._send_json({"error": "Unknown endpoint"}, 404)
        except Exception as exc:
            self._send_os_error(exc)

    def do_GET(self):
        path, _, raw_query = self.path.partition("?")
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
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object.")
        except (ValueError, UnicodeError) as exc:
            self._send_json({"error": str(exc)}, 400)
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
