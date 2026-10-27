"""
hud/os_dashboard.py - backend for the primary AI OS dashboard (static/os.html).

Owns:
  * the daily board: vital tasks, task tracker, goals + milestones, calendar events
  * the local auto-scheduler that places open tasks into free time today
  * read-only .ics import from hud-interface/calendar/ (export of any calendar app)
  * alert derivation for the HUD alert widget
  * documentation shortcuts (allowlisted ids, never caller-supplied paths)
  * the quick code editor, which can write ONLY inside hud-interface/scratch/
  * the lightweight telemetry frame behind the live flowchart (SSE stream)

Boundaries:
  * Nothing here opens a network connection. The one probe (Hermes loopback on
    127.0.0.1:8080) lives in hud_server.py and is cached there.
  * Telemetry frames carry counts and states only: no draft bodies, no email
    addresses, no financial amounts.
  * Binary floats are never written; the board uses ints and strings only.
  * This is an operational assistant / command center, not a trading bot.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .storage import atomic_json, file_lock, read_json

HUD_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("HUD_DATA_DIR", str(HUD_ROOT / "data")))
BOARD_PATH = DATA_DIR / "os_board.json"
CALENDAR_DIR = Path(os.environ.get("HUD_CALENDAR_DIR", str(HUD_ROOT / "calendar")))
SCRATCH_DIR = Path(os.environ.get("HUD_SCRATCH_DIR", str(HUD_ROOT / "scratch")))
SECOND_BRAIN_DIR = Path(os.environ.get("SECOND_BRAIN_DIR", r"G:\My Drive\second-brain" if os.name == "nt" else str(HUD_ROOT / "vault")))
MARK_LVI_DIR = Path(os.environ.get("MARK_LVI_DIR", r"C:\Users\alesh\Downloads\Mark-LVI-main" if os.name == "nt" else str(HUD_ROOT / "mark-lvi")))

_BOARD_LOCK = threading.Lock()
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
STATUSES = ("todo", "doing", "done")
HORIZONS = ("week", "month", "quarter", "year")


# --------------------------------------------------------------------------- #
# Small validators
# --------------------------------------------------------------------------- #
def _text(value: Any, limit: int = 200, required: bool = True) -> str:
    text = _CTRL.sub("", str(value if value is not None else "")).strip()[:limit]
    if required and not text:
        raise ValueError("A non-empty title is required")
    return text


def _hhmm(value: Any) -> str:
    text = str(value or "").strip()
    if not _HHMM.match(text):
        raise ValueError("Time must be HH:MM (24h)")
    return text


def _iso_date(value: Any, allow_empty: bool = True) -> str:
    text = str(value or "").strip()
    if not text and allow_empty:
        return ""
    return date.fromisoformat(text).isoformat()


def _int(value: Any, lo: int, hi: int, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Board persistence
# --------------------------------------------------------------------------- #
def _seed_board(today: date) -> dict[str, Any]:
    """First-run starter board. Every item is marked seed=True so it is obvious
    these were placed by the dashboard, not written by the user."""
    goal_id = _new_id("goal")
    return {
        "schema_version": 1,
        "revision": 0,
        "settings": {"workday_start": "09:00", "workday_end": "18:00", "buffer_min": 5},
        "tasks": [
            {"id": _new_id("task"), "title": "Review staged outreach drafts in the Outbox",
             "status": "todo", "priority": 1, "vital": True, "estimate_min": 30,
             "due": today.isoformat(), "goal_id": goal_id, "seed": True, "created_at": _utc(), "done_at": ""},
            {"id": _new_id("task"), "title": "Start the local Hermes model on 127.0.0.1:8080",
             "status": "todo", "priority": 2, "vital": True, "estimate_min": 20,
             "due": "", "goal_id": "", "seed": True, "created_at": _utc(), "done_at": ""},
            {"id": _new_id("task"), "title": "Run the unit test suite after today's changes",
             "status": "todo", "priority": 2, "vital": False, "estimate_min": 15,
             "due": "", "goal_id": "", "seed": True, "created_at": _utc(), "done_at": ""},
        ],
        "goals": [
            {"id": goal_id, "title": "Offline reconciliation product: Milestone 1 sign-off",
             "horizon": "month", "seed": True,
             "milestones": [
                 {"id": _new_id("ms"), "title": "Quarantine packet reviewed", "done": False},
                 {"id": _new_id("ms"), "title": "Zero-loss invariant passing on live batch", "done": False},
                 {"id": _new_id("ms"), "title": "Human-approved outreach for first prospect", "done": False},
             ]},
        ],
        "events": [],
    }


def _normalise(board: Any) -> dict[str, Any]:
    if not isinstance(board, dict):
        raise ValueError("Board must be a JSON object")
    board.setdefault("schema_version", 1)
    board.setdefault("revision", 0)
    settings = board.setdefault("settings", {})
    settings.setdefault("workday_start", "09:00")
    settings.setdefault("workday_end", "18:00")
    settings.setdefault("buffer_min", 5)
    for key in ("tasks", "goals", "events"):
        if not isinstance(board.get(key), list):
            board[key] = []
    return board


def load_board(path: Path = BOARD_PATH, today: date | None = None) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        board = _seed_board(today or date.today())
        atomic_json(path, board)
        return board
    return _normalise(read_json(path))


def _save(board: dict[str, Any], path: Path) -> dict[str, Any]:
    board["revision"] = int(board.get("revision", 0)) + 1
    board["updated_at"] = _utc()
    atomic_json(path, board)
    return board


def _find(items: list[dict[str, Any]], item_id: Any) -> dict[str, Any]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise KeyError(f"No item with id {item_id!r}")


def apply_board_op(op: dict[str, Any], path: Path = BOARD_PATH) -> dict[str, Any]:
    """Single mutation entry point. Every write is validated, locked and atomic."""
    if not isinstance(op, dict):
        raise ValueError("Operation must be a JSON object")
    kind = str(op.get("op", ""))
    path = Path(path)
    with _BOARD_LOCK, file_lock(path):
        board = load_board(path)
        expected = op.get("revision")
        if expected is not None and int(expected) != int(board.get("revision", 0)):
            raise RuntimeError("Board changed in another window. Reload and retry.")
        tasks, goals, events = board["tasks"], board["goals"], board["events"]

        if kind == "task.add":
            goal_id = str(op.get("goal_id") or "")
            if goal_id:
                _find(goals, goal_id)
            tasks.append({
                "id": _new_id("task"), "title": _text(op.get("title")),
                "status": "todo", "priority": _int(op.get("priority"), 1, 3, 2),
                "vital": bool(op.get("vital", False)),
                "estimate_min": _int(op.get("estimate_min"), 5, 480, 30),
                "due": _iso_date(op.get("due")), "goal_id": goal_id,
                "created_at": _utc(), "done_at": "",
            })
        elif kind == "task.update":
            task = _find(tasks, op.get("id"))
            if "title" in op:
                task["title"] = _text(op["title"])
            if "status" in op:
                status = str(op["status"])
                if status not in STATUSES:
                    raise ValueError("Status must be todo, doing or done")
                task["status"] = status
                task["done_at"] = _utc() if status == "done" else ""
            if "priority" in op:
                task["priority"] = _int(op["priority"], 1, 3, task.get("priority", 2))
            if "vital" in op:
                task["vital"] = bool(op["vital"])
            if "estimate_min" in op:
                task["estimate_min"] = _int(op["estimate_min"], 5, 480, task.get("estimate_min", 30))
            if "due" in op:
                task["due"] = _iso_date(op["due"])
            task.pop("seed", None)
        elif kind == "task.delete":
            board["tasks"] = [t for t in tasks if t.get("id") != op.get("id")]
        elif kind == "goal.add":
            horizon = str(op.get("horizon") or "month")
            goals.append({"id": _new_id("goal"), "title": _text(op.get("title")),
                          "horizon": horizon if horizon in HORIZONS else "month", "milestones": []})
        elif kind == "goal.delete":
            board["goals"] = [g for g in goals if g.get("id") != op.get("id")]
            for task in tasks:
                if task.get("goal_id") == op.get("id"):
                    task["goal_id"] = ""
        elif kind == "milestone.add":
            goal = _find(goals, op.get("goal_id"))
            goal.setdefault("milestones", []).append(
                {"id": _new_id("ms"), "title": _text(op.get("title")), "done": False})
            goal.pop("seed", None)
        elif kind == "milestone.toggle":
            goal = _find(goals, op.get("goal_id"))
            ms = _find(goal.get("milestones", []), op.get("id"))
            ms["done"] = not bool(ms.get("done"))
        elif kind == "milestone.delete":
            goal = _find(goals, op.get("goal_id"))
            goal["milestones"] = [m for m in goal.get("milestones", []) if m.get("id") != op.get("id")]
        elif kind == "event.add":
            start, end = _hhmm(op.get("start")), _hhmm(op.get("end"))
            if _minutes(end) <= _minutes(start):
                raise ValueError("Event must end after it starts")
            events.append({"id": _new_id("evt"), "title": _text(op.get("title")),
                           "date": _iso_date(op.get("date"), allow_empty=False),
                           "start": start, "end": end})
        elif kind == "event.delete":
            board["events"] = [e for e in events if e.get("id") != op.get("id")]
        elif kind == "settings.update":
            settings = board["settings"]
            start = _hhmm(op.get("workday_start", settings["workday_start"]))
            end = _hhmm(op.get("workday_end", settings["workday_end"]))
            if _minutes(end) <= _minutes(start):
                raise ValueError("Workday must end after it starts")
            settings.update(workday_start=start, workday_end=end,
                            buffer_min=_int(op.get("buffer_min", settings["buffer_min"]), 0, 60, 5))
        else:
            raise ValueError(f"Unknown board operation: {kind!r}")
        return _save(board, path)


# --------------------------------------------------------------------------- #
# Calendar: read-only .ics import
# --------------------------------------------------------------------------- #
_ICS_CACHE: dict[str, Any] = {"key": None, "events": []}


def _parse_ics_datetime(value: str) -> tuple[datetime | None, bool]:
    value = value.strip()
    try:
        if re.fullmatch(r"\d{8}", value):
            return datetime.strptime(value, "%Y%m%d"), True
        if value.endswith("Z"):
            utc = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            return utc.astimezone().replace(tzinfo=None), False
        # Floating or TZID-qualified local time: treated as this machine's local time.
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S"), False
    except ValueError:
        return None, False


def _unescape_ics(text: str) -> str:
    return text.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_ics(text: str, source: str = "calendar.ics") -> list[dict[str, Any]]:
    """Minimal VEVENT reader: SUMMARY, DTSTART, DTEND. Recurrence rules are not expanded."""
    unfolded = re.sub(r"\r?\n[ \t]", "", text)
    events: list[dict[str, Any]] = []
    current: dict[str, str] | None = None
    for line in unfolded.splitlines():
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            current = {}
            continue
        if upper == "END:VEVENT":
            if current is not None:
                start, all_day = _parse_ics_datetime(current.get("DTSTART", ""))
                end, _ = _parse_ics_datetime(current.get("DTEND", ""))
                if start:
                    if end is None or end <= start:
                        end = start + (timedelta(days=1) if all_day else timedelta(minutes=30))
                    events.append({
                        "id": "ics_" + hashlib.sha256((source + current.get("UID", "") + start.isoformat()).encode()).hexdigest()[:10],
                        "title": _text(_unescape_ics(current.get("SUMMARY", "(untitled)")), 200, required=False) or "(untitled)",
                        "date": start.date().isoformat(),
                        "start": start.strftime("%H:%M"), "end": end.strftime("%H:%M") if end.date() == start.date() else "23:59",
                        "all_day": all_day, "recurring": "RRULE" in current, "source": source,
                    })
            current = None
            continue
        if current is not None and ":" in line:
            name, value = line.split(":", 1)
            current[name.split(";", 1)[0].strip().upper()] = value
    return events


def read_ics_events(cal_dir: Path = CALENDAR_DIR, max_bytes: int = 1_000_000) -> list[dict[str, Any]]:
    cal_dir = Path(cal_dir)
    if not cal_dir.is_dir():
        return []
    files = sorted(cal_dir.glob("*.ics"))
    key = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in files)
    if _ICS_CACHE["key"] == key:
        return list(_ICS_CACHE["events"])
    events: list[dict[str, Any]] = []
    for f in files:
        if f.stat().st_size > max_bytes:
            continue
        events.extend(parse_ics(f.read_text(encoding="utf-8", errors="replace"), f.name))
    _ICS_CACHE.update(key=key, events=events)
    return list(events)


# --------------------------------------------------------------------------- #
# Auto-scheduler
# --------------------------------------------------------------------------- #
def _subtract(free: list[tuple[int, int]], busy: tuple[int, int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    b0, b1 = busy
    for f0, f1 in free:
        if b1 <= f0 or b0 >= f1:
            out.append((f0, f1))
            continue
        if f0 < b0:
            out.append((f0, b0))
        if b1 < f1:
            out.append((b1, f1))
    return out


def _fmt(minute: int) -> str:
    minute = max(0, min(24 * 60 - 1, minute))
    return f"{minute // 60:02d}:{minute % 60:02d}"


def task_order_key(task: dict[str, Any]) -> tuple:
    return (
        0 if task.get("vital") else 1,
        0 if task.get("status") == "doing" else 1,
        _int(task.get("priority"), 1, 3, 2),
        task.get("due") or "9999-12-31",
        task.get("created_at") or "",
    )


def plan_target_day(board: dict[str, Any], now: datetime) -> date:
    """Today while the workday is still running, otherwise tomorrow."""
    end = _minutes(board.get("settings", {}).get("workday_end", "18:00"))
    return now.date() if now.hour * 60 + now.minute < end else now.date() + timedelta(days=1)


def plan_day(board: dict[str, Any], day: date, now: datetime,
             ics_events: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Place open tasks into today's free time around fixed events.

    Deterministic: same board + same clock -> same plan. Vital tasks first, then
    in-progress, then priority, due date and age. First-fit into free gaps, with a
    buffer after every block. Anything that does not fit is reported, not dropped.
    """
    settings = board.get("settings", {})
    ws, we = _minutes(settings.get("workday_start", "09:00")), _minutes(settings.get("workday_end", "18:00"))
    buffer = _int(settings.get("buffer_min"), 0, 60, 5)
    iso = day.isoformat()

    fixed: list[dict[str, Any]] = []
    all_day: list[dict[str, Any]] = []
    for ev in list(board.get("events", [])) + list(ics_events):
        if ev.get("date") != iso:
            continue
        if ev.get("all_day"):
            all_day.append({"title": ev.get("title"), "source": ev.get("source", "board")})
            continue
        s, e = _minutes(ev["start"]), _minutes(ev["end"])
        fixed.append({"kind": "ics" if ev.get("source") else "event", "id": ev.get("id"),
                      "title": ev.get("title"), "start_min": s, "end_min": e,
                      "source": ev.get("source", "board")})

    if day < now.date():
        cursor = we
    elif day == now.date():
        now_min = now.hour * 60 + now.minute
        cursor = max(ws, ((now_min + 4) // 5) * 5)
    else:
        cursor = ws

    free = [(cursor, we)] if cursor < we else []
    for block in fixed:
        free = _subtract(free, (block["start_min"] - buffer, block["end_min"] + buffer))

    blocks: list[dict[str, Any]] = list(fixed)
    unscheduled: list[dict[str, Any]] = []
    open_tasks = sorted((t for t in board.get("tasks", []) if t.get("status") != "done"), key=task_order_key)
    for task in open_tasks:
        need = _int(task.get("estimate_min"), 5, 480, 30)
        slot = next(((f0, f1) for f0, f1 in free if f1 - f0 >= need), None)
        if slot is None:
            reason = "workday is over" if cursor >= we else f"no free slot of {need} min before {_fmt(we)}"
            unscheduled.append({"id": task["id"], "title": task["title"], "estimate_min": need,
                                "vital": bool(task.get("vital")), "reason": reason})
            continue
        start = slot[0]
        blocks.append({"kind": "task", "id": task["id"], "title": task["title"],
                       "start_min": start, "end_min": start + need, "vital": bool(task.get("vital")),
                       "priority": _int(task.get("priority"), 1, 3, 2), "status": task.get("status")})
        free = _subtract(free, (start, start + need + buffer))

    blocks.sort(key=lambda b: (b["start_min"], b["end_min"]))
    for b in blocks:
        b["start"], b["end"] = _fmt(b["start_min"]), _fmt(b["end_min"])
    span = max(1, we - ws)
    busy = sum(max(0, min(b["end_min"], we) - max(b["start_min"], ws)) for b in blocks)
    return {
        "date": iso,
        "is_today": day == now.date(),
        "workday": {"start": _fmt(ws), "end": _fmt(we), "start_min": ws, "end_min": we},
        "now_min": now.hour * 60 + now.minute if day == now.date() else None,
        "blocks": blocks, "all_day": all_day, "unscheduled": unscheduled,
        "free_min": sum(f1 - f0 for f0, f1 in free),
        "load_pct": min(100, (busy * 100) // span),
        "algorithm": "first-fit: vital > doing > priority > due > age; buffer after each block",
    }


# --------------------------------------------------------------------------- #
# Alerts
# --------------------------------------------------------------------------- #
_SEVERITY_RANK = {"crit": 0, "warn": 1, "info": 2}


def build_alerts(frame_nodes: dict[str, Any], board: dict[str, Any], plan: dict[str, Any],
                 now: datetime, guard_recent: int = 0) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    def add(aid: str, severity: str, title: str, detail: str, target: str) -> None:
        alerts.append({"id": aid, "severity": severity, "title": title, "detail": detail, "target": target})

    n = frame_nodes
    if n.get("harness", {}).get("status") == "err":
        add("invariant", "crit", "Zero-loss invariant breached", n["harness"].get("detail", ""), "flow")
    if n.get("model", {}).get("status") == "err":
        add("hermes-down", "warn", "Hermes local model unreachable",
            "Nothing is answering on 127.0.0.1:8080. Offline extraction falls back or stops.", "flow")
    if n.get("hermes", {}).get("status") == "warn":
        add("hermes-sim", "info", "Last Hermes run was simulated", n["hermes"].get("detail", ""), "flow")
    if guard_recent:
        add("guard", "warn", f"{guard_recent} guardrail block(s) in the last 24h",
            "Level 6 stopped a destructive or credential command. Review the log.", "flow")
    review = n.get("gtm", {}).get("count", 0)
    if review:
        add("gtm-review", "info", f"{review} outbox draft(s) need your review",
            "Approval records a decision only. Nothing is sent automatically.", "outbox")
    pending = n.get("notify", {}).get("count", 0)
    if pending:
        add("notify-pending", "info", f"{pending} notification event(s) pending",
            "Metadata only. Flush happens when you trigger the relay.", "outbox")

    today = now.date().isoformat()
    for task in board.get("tasks", []):
        if task.get("status") != "done" and task.get("due") and task["due"] < today:
            add("overdue-" + task["id"], "warn", "Overdue: " + task["title"], f"Was due {task['due']}.", "today")
    plan_label = "today" if plan.get("is_today") else plan.get("date", "the next workday")
    for item in plan.get("unscheduled", []):
        if item.get("vital"):
            add("unsched-" + item["id"], "warn", f"Vital task does not fit {plan_label}: " + item["title"],
                item["reason"] + ". Shorten it, move an event, or extend the workday.", "calendar")
    now_min = now.hour * 60 + now.minute
    for block in plan.get("blocks", []) if plan.get("is_today") else []:
        if block["kind"] in ("event", "ics") and 0 <= block["start_min"] - now_min <= 15:
            add("soon-" + str(block.get("id")), "info", f"Starts at {block['start']}: {block['title']}",
                "Within the next 15 minutes.", "calendar")

    alerts.sort(key=lambda a: _SEVERITY_RANK.get(a["severity"], 9))
    return alerts


# --------------------------------------------------------------------------- #
# Documentation shortcuts (allowlist + read-only vault discovery)
# --------------------------------------------------------------------------- #
def _base_doc_shortcuts(second_brain: Path = SECOND_BRAIN_DIR) -> list[dict[str, Any]]:
    return [
        {"id": "hud-readme", "group": "HUD", "title": "HUD README", "path": HUD_ROOT / "README.md"},
        {"id": "spec-0001", "group": "HUD", "title": "Spec 0001: Command Center", "path": HUD_ROOT / "docs" / "specs" / "0001-command-center.md"},
        {"id": "verification", "group": "HUD", "title": "Verification guide", "path": HUD_ROOT / "docs" / "verification.md"},
        {"id": "sb-core", "group": "Second Brain", "title": "core.md", "path": second_brain / "core.md"},
        {"id": "sb-source-gov", "group": "Second Brain", "title": "Source Governance", "path": second_brain / "modules" / "source-governance.md"},
        {"id": "sb-knowledge", "group": "Second Brain", "title": "Knowledge & Memory", "path": second_brain / "modules" / "knowledge-memory.md"},
        {"id": "sb-project-index", "group": "Second Brain", "title": "Project Index", "path": second_brain / "modules" / "project-index.md"},
        {"id": "sb-execution", "group": "Second Brain", "title": "Execution", "path": second_brain / "modules" / "execution.md"},
        {"id": "sb-verification", "group": "Second Brain", "title": "Verification", "path": second_brain / "modules" / "verification.md"},
        {"id": "sb-hermes", "group": "Second Brain", "title": "Hermes Delegation", "path": second_brain / "modules" / "hermes-delegation.md"},
        {"id": "sb-local-models", "group": "Second Brain", "title": "Local Models", "path": second_brain / "modules" / "local-models.md"},
        {"id": "sb-persona", "group": "Second Brain", "title": "Persona & Cognition", "path": second_brain / "modules" / "persona.md"},
        {"id": "sb-budgeting", "group": "Second Brain", "title": "Optional Budgeting (OFF)", "path": second_brain / "optional" / "budgeting.md"},
        {"id": "sow-keystone", "group": "Offline Product", "title": "SOW: Keystone Precision", "path": HUD_ROOT.parent / "delivery-offline" / "SOW_Keystone_Precision_Machining.md"},
        {"id": "mark-outcome", "group": "Mark LVI", "title": "core/outcome.py (5-word contract)", "path": MARK_LVI_DIR / "core" / "outcome.py"},
        {"id": "mark-readme", "group": "Mark LVI", "title": "Mark LVI README", "path": MARK_LVI_DIR / "README.md"},
    ]


def doc_shortcuts(second_brain: Path = SECOND_BRAIN_DIR, scratch: Path = SCRATCH_DIR) -> list[dict[str, Any]]:
    docs = list(_base_doc_shortcuts(second_brain))
    seen_paths = {str(d["path"]) for d in docs}
    seen_ids = {d["id"] for d in docs}
    scanned = scan_obsidian_vault(second_brain_dir=second_brain, scratch_dir=scratch)
    for extra in scanned.get("docs", []):
        p_str = str(extra["path"])
        if p_str not in seen_paths and extra["id"] not in seen_ids:
            docs.append(extra)
            seen_paths.add(p_str)
            seen_ids.add(extra["id"])
    return docs


def list_docs(second_brain: Path = SECOND_BRAIN_DIR, scratch: Path = SCRATCH_DIR) -> list[dict[str, Any]]:
    return [{"id": d["id"], "group": d["group"], "title": d["title"], "file": d["path"].name,
             "available": d["path"].is_file()} for d in doc_shortcuts(second_brain=second_brain, scratch=scratch)]


def read_doc(doc_id: str, limit: int = 200_000, second_brain: Path = SECOND_BRAIN_DIR, scratch: Path = SCRATCH_DIR) -> dict[str, Any]:
    entry = next((d for d in doc_shortcuts(second_brain=second_brain, scratch=scratch) if d["id"] == doc_id), None)
    if entry is None:
        raise KeyError("Unknown document id")
    path: Path = entry["path"]
    if not path.is_file():
        raise FileNotFoundError(f"{path.name} is not available on this machine")
    raw = path.read_bytes()
    return {"id": doc_id, "title": entry["title"], "file": path.name, "path": str(path),
            "bytes": len(raw), "truncated": len(raw) > limit,
            "text": raw[:limit].decode("utf-8", errors="replace")}


# --------------------------------------------------------------------------- #
# Quick code editor (scratch directory only)
# --------------------------------------------------------------------------- #
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
EDITOR_EXTS = {".py", ".js", ".ts", ".md", ".json", ".txt", ".css", ".html", ".ps1", ".sql", ".yaml", ".yml", ".toml", ".csv"}
EDITOR_MAX_BYTES = 128 * 1024


def _scratch_path(name: str, scratch: Path) -> Path:
    name = str(name or "").strip()
    if not _NAME.match(name) or ".." in name:
        raise ValueError("File name may use letters, digits, '.', '_' and '-' only (max 64)")
    if Path(name).suffix.lower() not in EDITOR_EXTS:
        raise ValueError("Extension not allowed in the scratch editor: " + (Path(name).suffix or "(none)"))
    root = Path(scratch).resolve()
    target = (root / name).resolve()
    if target.parent != root:
        raise ValueError("Scratch editor cannot leave its folder")
    return target


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def editor_list(scratch: Path = SCRATCH_DIR) -> dict[str, Any]:
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted(scratch.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix.lower() in EDITOR_EXTS and _NAME.match(f.name):
            files.append({"name": f.name, "bytes": f.stat().st_size,
                          "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
    return {"root": str(scratch), "files": files, "extensions": sorted(EDITOR_EXTS), "max_bytes": EDITOR_MAX_BYTES}


def editor_read(name: str, scratch: Path = SCRATCH_DIR) -> dict[str, Any]:
    path = _scratch_path(name, scratch)
    if not path.is_file():
        raise FileNotFoundError("No such scratch file")
    raw = path.read_bytes()
    return {"name": path.name, "text": raw.decode("utf-8", errors="replace"), "sha256": _sha(raw), "bytes": len(raw)}


def editor_save(name: str, text: Any, base_sha256: str | None, scratch: Path = SCRATCH_DIR) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    raw = text.encode("utf-8")
    if len(raw) > EDITOR_MAX_BYTES:
        raise ValueError(f"File exceeds {EDITOR_MAX_BYTES // 1024} KB editor limit")
    path = _scratch_path(name, scratch)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        if path.exists():
            current = _sha(path.read_bytes())
            if base_sha256 != current:
                raise RuntimeError("File changed on disk since you opened it. Reopen before saving.")
        elif base_sha256:
            raise RuntimeError("File was deleted since you opened it.")
        tmp = path.with_name(path.name + f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, path)
    invalidate_vault_cache()
    return {"name": path.name, "sha256": _sha(raw), "bytes": len(raw), "saved_at": _utc()}


# --------------------------------------------------------------------------- #
# Telemetry frame for the live flowchart
# --------------------------------------------------------------------------- #
_STATIC_CACHE: dict[str, Any] = {"at": 0.0, "value": None}


def static_stats(ttl: int = 300) -> dict[str, Any]:
    """Slow-changing counts (Mark LVI tools, Second Brain modules). Cached: G: is a sync drive."""
    if _STATIC_CACHE["value"] is not None and time.monotonic() - _STATIC_CACHE["at"] < ttl:
        return _STATIC_CACHE["value"]

    def count(folder: Path, pattern: str) -> int | None:
        try:
            return sum(1 for p in folder.glob(pattern) if p.is_file() and not p.name.startswith("_") and p.name.lower() not in _EXCLUDED_SB_FILES)
        except OSError:
            return None

    value = {
        "mark_actions": count(MARK_LVI_DIR / "actions", "*.py"),
        "mark_plugins": count(MARK_LVI_DIR / "plugins", "*.py"),
        "brain_modules": count(SECOND_BRAIN_DIR / "modules", "*.md"),
    }
    _STATIC_CACHE.update(at=time.monotonic(), value=value)
    return value


FLOW_GROUPS = [
    {"id": "aios", "label": "AI OS"},
    {"id": "hermes", "label": "HERMES"},
    {"id": "offline", "label": "OFFLINE PRODUCT"},
]

FLOW_EDGES = [
    ("brain", "jev", "policy"),
    ("mark", "jev", "tool calls"),
    ("jev", "hud", "verdicts"),
    ("hud", "assignments", "operator-directed"),
    ("jev", "assignments", "aios-directed"),
    ("inbox", "assignments", "event-driven"),
    ("brain", "assignments", "educate & memory"),
    ("assignments", "harness", "ledger state"),
    ("assignments", "hermes", "model handoff"),
    ("hud", "hermes", "probe"),
    ("hermes", "model", "loopback :8080"),
    ("hermes", "harness", "schema extract"),
    ("inbox", "harness", "snapshot"),
    ("harness", "quarantine", "bad rows"),
    ("harness", "gtm", "E2E draft"),
    ("jev", "gtm", "L3/L4 gate"),
    ("harness", "notify", "state events"),
    ("notify", "relay", "human flush"),
    ("gtm", "hud", "review"),
]


OBSIDIAN_NOTES = [
    {"id": "aios-root", "label": "AIOS Root Node", "ring": 0, "group": "core", "doc_id": "aios-root",
     "flow_node": "hud", "base_activity": 99,
     "summary": "Ring 0 AIOS Root Node: Primary system nucleus wiring all 5 active agent clusters directly."},
    {"id": "assignments", "label": "Assignments & Routing", "ring": 1, "group": "aios", "doc_id": "aios-assignments",
     "flow_node": "assignments", "base_activity": 95,
     "summary": "Dynamic assignment routing linking Kanban orchestrator, SQLite ledger, and educate. Accepts aios-directed, operator-directed, and event-driven triggers."},
    {"id": "gtm-outreach", "label": "GTM Outreach & Research", "ring": 1, "group": "gtm", "doc_id": "aios-gtm-outreach",
     "flow_node": "gtm", "base_activity": 94,
     "summary": "Primary GTM Governance Node (Ring 1 Child of AIOS Root): Dedicated client research nodes, problem context, and Hermes email drafting."},
    {"id": "core.md", "label": "core.md", "ring": 1, "group": "core", "doc_id": "sb-core",
     "flow_node": "brain", "base_activity": 96,
     "summary": "Ring 1 Child Node: Master Second Brain instructions, module states, and precedence governed under AIOS Root."},
    {"id": "source-governance", "label": "Source Governance", "ring": 1, "group": "governance", "doc_id": "sb-source-gov",
     "flow_node": "brain", "base_activity": 88,
     "summary": "Owns chronology, provenance, conflict resolution, and protection of synced reference sources."},
    {"id": "knowledge-memory", "label": "Knowledge & Memory", "ring": 1, "group": "governance", "doc_id": "sb-knowledge",
     "flow_node": "brain", "base_activity": 86,
     "summary": "Owns durable storage, vault indexing, and untrusted-content memory isolation."},
    {"id": "verification", "label": "Verification", "ring": 1, "group": "governance", "doc_id": "sb-verification",
     "flow_node": "jev", "base_activity": 95,
     "summary": "Enforces physical disk proof and Level 8/10 deterministic verification before claiming completion."},
    {"id": "execution", "label": "Execution", "ring": 1, "group": "governance", "doc_id": "sb-execution",
     "flow_node": "mark", "base_activity": 91,
     "summary": "Owns authorized tool invocation boundaries and Level 6 pre-execution safety hooks."},
    {"id": "hermes-delegation", "label": "Hermes Delegation", "ring": 1, "group": "hermes", "doc_id": "sb-hermes",
     "flow_node": "hermes", "base_activity": 90,
     "summary": "Routes work between local agents and human review gates without unapproved escalation."},
    {"id": "jev-gates", "label": "JEV Gates L1-L10", "ring": 1, "group": "governance", "doc_id": "verification",
     "flow_node": "jev", "base_activity": 89,
     "summary": "Operational governance gates: L6 Bash Guardrail, L8 Cheap File Read, L9 Vault Scout, L10 Agentic Judge, and L3/L4 Review Gates."},
    {"id": "local-models", "label": "Local Models", "ring": 1, "group": "hermes", "doc_id": "sb-local-models",
     "flow_node": "model", "base_activity": 84,
     "summary": "Manages local loopback inference on 127.0.0.1:8080, context ceilings, and schema repair."},
    {"id": "persona", "label": "Persona & Cognition", "ring": 1, "group": "governance", "doc_id": "sb-persona",
     "flow_node": "hud", "base_activity": 82,
     "summary": "Systems architect communication style: beginner-friendly clarity, deterministic vs probabilistic separation."},
    {"id": "project-index", "label": "Project Index", "ring": 1, "group": "governance", "doc_id": "sb-project-index",
     "flow_node": "hud", "base_activity": 93,
     "summary": "Central pointer registry connecting Second Brain, Hermes runtime, Mark LVI, and Offline Product queues."},
    {"id": "budgeting", "label": "Budgeting (OFF)", "ring": 1, "group": "disabled", "doc_id": "sb-budgeting",
     "flow_node": "brain", "base_activity": 14,
     "summary": "Optional module kept explicitly disabled per user directive; routine tasks require zero budget fields."},
    # Ring 2: Linked Workspace Diodes, SOWs & Contracts
    {"id": "mark-outcome", "label": "Mark LVI 5-Word Contract", "ring": 2, "group": "aios", "doc_id": "mark-outcome",
     "flow_node": "mark", "base_activity": 92,
     "summary": "core/outcome.py: done, unverified, failed, ask, started — blocks false-success hallucinations."},
    {"id": "sow-keystone", "label": "SOW: Keystone Precision", "ring": 2, "group": "offline", "doc_id": "sow-keystone",
     "flow_node": "harness", "base_activity": 90,
     "summary": "Offline reconciliation Statement of Work scouted by Level 9 and verified by Level 8."},
    {"id": "inbox-diode", "label": "Inbox Diode Snapshot", "ring": 2, "group": "offline", "doc_id": "spec-0001",
     "flow_node": "inbox", "base_activity": 87,
     "summary": "inbox/offline_snapshot.json: air-gapped one-way telemetry ingest into the HUD."},
    {"id": "reconcile-harness", "label": "Reconciliation & Quarantine", "ring": 2, "group": "offline", "doc_id": "verification",
     "flow_node": "quarantine", "base_activity": 94,
     "summary": "Zero-loss invariant ledger & CSV quarantine isolating malformed rows before AP posting."},
    {"id": "gtm-outbox", "label": "GTM Outbox Diode", "ring": 2, "group": "offline", "doc_id": "spec-0001",
     "flow_node": "gtm", "base_activity": 95,
     "summary": "staged_outreach.json: human-review gate where approval records a decision only (never auto-sends)."},
    {"id": "notify-relay", "label": "Notification Outbox & Relay", "ring": 2, "group": "offline", "doc_id": "hud-readme",
     "flow_node": "notify", "base_activity": 83,
     "summary": "metadata_outbox.json: zero-PII, zero-currency state alerts flushed only on human trigger."},
]

OBSIDIAN_LINKS = [
    # Ring 0 AIOS Root & Ring 1 core links
    ("aios-root", "core.md", 99, 5, "root-child"),
    ("aios-root", "assignments", 98, 5, "root-routing"),
    ("aios-root", "gtm-outreach", 98, 5, "root-governance"),
    ("aios-root", "project-index", 97, 5, "root-anchor"),
    ("gtm-outreach", "hermes-delegation", 96, 5, "delegation"),
    ("gtm-outreach", "gtm-outbox", 95, 5, "data-flow"),
    ("core.md", "source-governance", 98, 5, "governance"),
    ("core.md", "knowledge-memory", 95, 4, "governance"),
    ("core.md", "verification", 97, 5, "verification"),
    ("core.md", "execution", 94, 4, "governance"),
    ("core.md", "hermes-delegation", 92, 4, "delegation"),
    ("core.md", "jev-gates", 93, 4, "governance"),
    ("core.md", "local-models", 88, 3, "hermes"),
    ("core.md", "persona", 86, 3, "governance"),
    ("core.md", "project-index", 96, 5, "governance"),
    ("core.md", "budgeting", 22, 0, "disabled"),
    # Assignments Dynamic Routing Links (Directly to Hermes Delegation & Execution Paths)
    ("assignments", "hermes-delegation", 98, 5, "delegation"),
    ("assignments", "execution", 96, 5, "execution"),
    ("assignments", "reconcile-harness", 95, 5, "ledger-state"),
    ("assignments", "sow-keystone", 93, 4, "data-flow"),
    ("assignments", "knowledge-memory", 92, 4, "educate"),
    # Ring 1 cross-references (high connection strength)
    ("source-governance", "knowledge-memory", 89, 4, "governance"),
    ("source-governance", "project-index", 91, 4, "governance"),
    ("knowledge-memory", "project-index", 90, 4, "data-flow"),
    ("verification", "execution", 94, 5, "verification"),
    ("verification", "jev-gates", 92, 5, "verification"),
    ("execution", "hermes-delegation", 88, 4, "delegation"),
    ("hermes-delegation", "local-models", 91, 4, "hermes"),
    ("jev-gates", "hermes-delegation", 87, 4, "delegation"),
    # Ring 1 -> Ring 2 operational data flow links
    ("verification", "mark-outcome", 96, 5, "verification"),
    ("execution", "mark-outcome", 93, 5, "data-flow"),
    ("project-index", "sow-keystone", 91, 4, "data-flow"),
    ("verification", "sow-keystone", 94, 5, "verification"),
    ("knowledge-memory", "inbox-diode", 89, 4, "data-flow"),
    ("verification", "reconcile-harness", 95, 5, "verification"),
    ("sow-keystone", "reconcile-harness", 92, 5, "data-flow"),
    ("inbox-diode", "reconcile-harness", 90, 4, "data-flow"),
    ("hermes-delegation", "gtm-outbox", 93, 5, "delegation"),
    ("jev-gates", "gtm-outbox", 94, 5, "verification"),
    ("reconcile-harness", "gtm-outbox", 96, 5, "data-flow"),
    ("execution", "notify-relay", 86, 3, "data-flow"),
    ("reconcile-harness", "notify-relay", 88, 4, "data-flow"),
]

# --------------------------------------------------------------------------- #
# Read-only Second Brain folder scanner + local scratch custom notes
# --------------------------------------------------------------------------- #
# NOTE: Second Brain (SECOND_BRAIN_DIR) is strictly READ-ONLY. We never modify
# or write to existing Obsidian vault files. Legacy trading files are excluded.
_EXCLUDED_SB_DIRS = {"jev_trading_system", "history", "gemini-scribe", ".git", ".obsidian"}
_EXCLUDED_SB_FILES = {"jev-trading.md"}
_CORE_SB_REL_TO_ID = {
    "core.md": "core.md",
    "modules/source-governance.md": "source-governance",
    "modules/knowledge-memory.md": "knowledge-memory",
    "modules/verification.md": "verification",
    "modules/execution.md": "execution",
    "modules/hermes-delegation.md": "hermes-delegation",
    "modules/local-models.md": "local-models",
    "modules/persona.md": "persona",
    "modules/project-index.md": "project-index",
    "optional/budgeting.md": "budgeting",
}
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_MDLINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]+\.md)\)")
_SANITIZE_TELEMETRY_RE = re.compile(r"[@\$€£`*_~>\[\]]+")
_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
_VALID_FLOW_NODES = {"hud", "jev", "mark", "brain", "hermes", "model", "inbox", "harness", "quarantine", "gtm", "notify", "relay", "assignments"}

_VAULT_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "value": None}


def invalidate_vault_cache() -> None:
    _VAULT_CACHE["at"] = 0.0
    _VAULT_CACHE["key"] = ""
    _VAULT_CACHE["value"] = None


def _clean_telemetry_text(raw: str, limit: int = 160) -> str:
    cleaned = _CTRL.sub("", _SANITIZE_TELEMETRY_RE.sub(" ", str(raw or "")))
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned[:limit]


def _slugify(value: str) -> str:
    s = _SLUG_RE.sub("-", str(value or "").strip().lower()).strip("-")
    return s[:48] or "note"


def _infer_flow_node(text_lower: str) -> str:
    if "hermes" in text_lower or "delegat" in text_lower:
        return "hermes"
    if "quarantin" in text_lower or "reconcil" in text_lower or "invoice" in text_lower:
        return "harness"
    if "outbox" in text_lower or "outreach" in text_lower or "gtm" in text_lower:
        return "gtm"
    if "verify" in text_lower or "verification" in text_lower or "guardrail" in text_lower:
        return "jev"
    if "mark lvi" in text_lower or "outcome" in text_lower:
        return "mark"
    if "model" in text_lower or "8080" in text_lower:
        return "model"
    return "brain"


def _parse_markdown_note(
    path: Path,
    *,
    note_id: str,
    doc_id: str,
    ring: int,
    group: str,
    editable: bool,
    scratch_file: str = "",
) -> dict[str, Any]:
    try:
        stat = path.stat()
        mtime = stat.st_mtime
        raw_text = path.read_bytes()[:65536].decode("utf-8", errors="replace")
    except OSError:
        mtime = 0.0
        raw_text = ""

    lines = [ln.strip() for ln in raw_text.splitlines()]
    label = path.stem.replace("-", " ").replace("_", " ").title()
    summary = ""
    flow_node = ""
    explicit_targets: list[str] = []

    in_frontmatter = False
    for idx, ln in enumerate(lines):
        if idx == 0 and ln == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if ln == "---":
                in_frontmatter = False
                continue
            k, sep, v = ln.partition(":")
            if sep:
                k_low = k.strip().lower()
                v_clean = v.strip().strip("\"'")
                if k_low in ("title", "label") and v_clean:
                    label = _clean_telemetry_text(v_clean, 48)
                elif k_low == "flow_node" and v_clean in _VALID_FLOW_NODES:
                    flow_node = v_clean
            continue

        if ln.startswith("#"):
            heading = _clean_telemetry_text(ln.lstrip("#").strip(), 48)
            if heading and label == path.stem.replace("-", " ").replace("_", " ").title():
                label = heading
            continue

        if not summary and ln and not ln.startswith(("---", "|", "```", "- [[", "* [[")):
            candidate = _clean_telemetry_text(ln, 160)
            if len(candidate) >= 8:
                summary = candidate

    for match in _WIKILINK_RE.findall(raw_text):
        target = match.strip()
        if target:
            explicit_targets.append(target)
    for match in _MDLINK_RE.findall(raw_text):
        target = Path(match.strip()).stem
        if target:
            explicit_targets.append(target)

    text_lower = raw_text.lower()
    if not flow_node:
        flow_node = _infer_flow_node(text_lower)
    if not summary:
        summary = f"Markdown note ({path.name}) indexed from {'local scratchpad' if editable else 'Second Brain'}."

    now_ts = time.time()
    age = max(0.0, now_ts - mtime) if mtime else 999999.0
    is_recent = age <= 600
    base_act = 95 if is_recent else (90 if age <= 86400 else 84)

    return {
        "id": note_id,
        "label": label,
        "ring": ring,
        "group": group,
        "doc_id": doc_id,
        "flow_node": flow_node,
        "base_activity": base_act,
        "hot_disk": is_recent,
        "summary": summary,
        "editable": editable,
        "scratch_file": scratch_file,
        "explicit_targets": explicit_targets,
        "text_lower": text_lower,
    }


def scan_obsidian_vault(
    second_brain_dir: Path = SECOND_BRAIN_DIR,
    scratch_dir: Path = SCRATCH_DIR,
    force: bool = False,
    ttl: int = 15,
) -> dict[str, Any]:
    """Read-only scan of Second Brain markdown files plus local scratchpad .md notes.
    Never writes to or modifies the existing Second Brain folder."""
    sb_root = Path(second_brain_dir)
    sc_root = Path(scratch_dir)

    scratch_sig_parts: list[str] = []
    if sc_root.is_dir():
        try:
            for f in sorted(sc_root.glob("*.md")):
                if f.is_file() and _NAME.match(f.name):
                    st = f.stat()
                    scratch_sig_parts.append(f"{f.name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            pass
    cache_key = f"{sb_root}|{sc_root}|{'#'.join(scratch_sig_parts)}"
    now_mono = time.monotonic()
    if (
        not force
        and _VAULT_CACHE["value"] is not None
        and _VAULT_CACHE["key"] == cache_key
        and (now_mono - _VAULT_CACHE["at"]) < ttl
    ):
        return _VAULT_CACHE["value"]

    discovered_notes: list[dict[str, Any]] = []
    discovered_docs: list[dict[str, Any]] = []
    core_mtimes: dict[str, float] = {}

    # 1. Read-only scan of Second Brain root & governance subfolders
    if sb_root.is_dir():
        scan_folders = [
            (sb_root, 1, "governance"),
            (sb_root / "modules", 1, "governance"),
            (sb_root / "templates", 2, "governance"),
            (sb_root / "notes", 2, "governance"),
        ]
        for folder, ring, grp in scan_folders:
            if not folder.is_dir():
                continue
            if folder.name.lower() in _EXCLUDED_SB_DIRS:
                continue
            try:
                md_files = sorted(folder.glob("*.md"))
            except OSError:
                continue
            for md_path in md_files:
                if not md_path.is_file() or md_path.name.startswith((".", "_")):
                    continue
                if md_path.name.lower() in _EXCLUDED_SB_FILES:
                    continue
                try:
                    rel_posix = md_path.relative_to(sb_root).as_posix()
                except ValueError:
                    continue
                if rel_posix in _CORE_SB_REL_TO_ID:
                    try:
                        core_mtimes[_CORE_SB_REL_TO_ID[rel_posix]] = md_path.stat().st_mtime
                    except OSError:
                        pass
                    continue

                slug = _slugify(rel_posix.replace(".md", ""))
                note_id = f"sb:{slug}"
                doc_id = f"sb-auto-{slug}"
                parsed = _parse_markdown_note(
                    md_path,
                    note_id=note_id,
                    doc_id=doc_id,
                    ring=ring,
                    group=grp,
                    editable=False,
                )
                discovered_notes.append(parsed)
                discovered_docs.append({
                    "id": doc_id,
                    "group": "Second Brain",
                    "title": parsed["label"],
                    "path": md_path,
                })

    # 2. Local custom markdown notes in hud-interface/scratch/*.md
    if sc_root.is_dir():
        try:
            scratch_mds = sorted(sc_root.glob("*.md"))
        except OSError:
            scratch_mds = []
        for md_path in scratch_mds:
            if not md_path.is_file() or not _NAME.match(md_path.name):
                continue
            slug = _slugify(md_path.stem)
            note_id = f"vault:{slug}"
            doc_id = f"vault-{slug}"
            parsed = _parse_markdown_note(
                md_path,
                note_id=note_id,
                doc_id=doc_id,
                ring=2,
                group="vault",
                editable=True,
                scratch_file=md_path.name,
            )
            discovered_notes.append(parsed)
            discovered_docs.append({
                "id": doc_id,
                "group": "Scratch Vault",
                "title": parsed["label"],
                "path": md_path,
            })

    # 3. Resolve cross-reference links for all discovered notes
    alias_to_id: dict[str, str] = {}
    for base_n in OBSIDIAN_NOTES:
        nid = base_n["id"]
        alias_to_id[nid.lower()] = nid
        alias_to_id[nid.lower().replace(".md", "")] = nid
        alias_to_id[base_n["label"].lower()] = nid
    for dn in discovered_notes:
        nid = dn["id"]
        alias_to_id[nid.lower()] = nid
        alias_to_id[nid.split(":", 1)[-1].lower()] = nid
        alias_to_id[dn["label"].lower()] = nid
        if dn.get("scratch_file"):
            alias_to_id[dn["scratch_file"].lower()] = nid
            alias_to_id[Path(dn["scratch_file"]).stem.lower()] = nid

    discovered_links: list[tuple[str, str, int, int, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    def add_link(src: str, dst: str, strength: int, rate: int, kind: str) -> None:
        if not src or not dst or src == dst:
            return
        pair = (src, dst) if src < dst else (dst, src)
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        discovered_links.append((src, dst, strength, rate, kind))

    keyword_targets = [
        ("core.md", "core.md"),
        ("source-governance", "source-governance"),
        ("knowledge-memory", "knowledge-memory"),
        ("verification", "verification"),
        ("execution", "execution"),
        ("hermes", "hermes-delegation"),
        ("local-models", "local-models"),
        ("persona", "persona"),
        ("project-index", "project-index"),
        ("outcome", "mark-outcome"),
        ("keystone", "sow-keystone"),
        ("inbox", "inbox-diode"),
        ("quarantine", "reconcile-harness"),
        ("outbox", "gtm-outbox"),
    ]

    for dn in discovered_notes:
        src_id = dn["id"]
        matched_any = False
        for raw_t in dn.get("explicit_targets", []):
            key = raw_t.strip().lower()
            target_id = alias_to_id.get(key) or alias_to_id.get(key.replace(".md", "")) or alias_to_id.get(_slugify(key))
            if target_id and target_id != src_id:
                add_link(src_id, target_id, 95, 5, "wiki-link")
                matched_any = True

        t_low = dn.get("text_lower", "")
        for kw, target_id in keyword_targets:
            if kw in t_low and target_id != src_id:
                add_link(src_id, target_id, 88, 4, "cross-ref")
                matched_any = True

        if not matched_any:
            add_link(src_id, "core.md", 86, 4, "vault-anchor")
            add_link(src_id, "project-index", 84, 3, "vault-anchor")

    result = {
        "notes": discovered_notes,
        "links": discovered_links,
        "docs": discovered_docs,
        "core_mtimes": core_mtimes,
    }
    _VAULT_CACHE.update(at=now_mono, key=cache_key, value=result)
    return result


def create_vault_note(
    payload: dict[str, Any],
    *,
    scratch: Path = SCRATCH_DIR,
    second_brain: Path = SECOND_BRAIN_DIR,
) -> dict[str, Any]:
    """Creates a custom markdown note strictly inside hud-interface/scratch/
    (never touches the Second Brain folder) so it appears in the Obsidian graph."""
    title = _text(payload.get("title"), 80, required=True)
    raw_name = str(payload.get("filename") or "").strip()
    if raw_name:
        if not raw_name.lower().endswith(".md"):
            raw_name += ".md"
        fname = raw_name
    else:
        fname = _slugify(title) + ".md"

    flow_node = str(payload.get("flow_node") or "brain").strip().lower()
    if flow_node not in _VALID_FLOW_NODES:
        flow_node = "brain"

    raw_links = payload.get("links") or ["core.md", "verification"]
    if isinstance(raw_links, str):
        link_items = [x.strip() for x in raw_links.split(",") if x.strip()]
    elif isinstance(raw_links, list):
        link_items = [str(x).strip() for x in raw_links if str(x).strip()]
    else:
        link_items = ["core.md", "verification"]
    if not link_items:
        link_items = ["core.md", "verification"]

    summary = _clean_telemetry_text(payload.get("summary") or payload.get("body") or "Custom operational note linked to the Second Brain graph.", 240)
    wiki_lines = "\n".join(f"- [[{item}]]" for item in link_items[:10])
    md_body = (
        f"---\n"
        f"title: {title}\n"
        f"flow_node: {flow_node}\n"
        f"---\n"
        f"# {title}\n\n"
        f"{summary}\n\n"
        f"## Linked Notes\n"
        f"{wiki_lines}\n"
    )
    saved = editor_save(fname, md_body, None, scratch=scratch)
    graph = build_obsidian_graph(second_brain_dir=second_brain, scratch_dir=scratch, force_scan=True)
    return {
        "saved": saved,
        "note_id": f"vault:{_slugify(Path(fname).stem)}",
        "obsidian": graph,
    }


def build_obsidian_graph(
    flow_nodes: dict[str, dict[str, Any]] | None = None,
    *,
    second_brain_dir: Path = SECOND_BRAIN_DIR,
    scratch_dir: Path = SCRATCH_DIR,
    force_scan: bool = False,
) -> dict[str, Any]:
    """Builds the interactive Obsidian graph payload with node activity scores,
    connection strengths (20..98), active data-flow velocities, and live read-only
    markdown folder discovery."""
    flow_nodes = flow_nodes or {}
    scanned = scan_obsidian_vault(second_brain_dir=second_brain_dir, scratch_dir=scratch_dir, force=force_scan)
    core_mtimes = scanned.get("core_mtimes", {})
    now_ts = time.time()

    notes = []
    note_map = {}
    for item in OBSIDIAN_NOTES:
        fn = flow_nodes.get(item["flow_node"], {})
        disk_mtime = core_mtimes.get(item["id"])
        disk_hot = bool(disk_mtime and (now_ts - disk_mtime) <= 600)
        is_hot = bool(fn.get("hot")) or disk_hot
        status = fn.get("status", "ok") if item["group"] != "disabled" else "disabled"
        boost = 6 if is_hot else (3 if status in ("warn", "info") else 0)
        activity = 14 if item["group"] == "disabled" else min(99, item["base_activity"] + boost)
        node_obj = {
            "id": item["id"],
            "label": item["label"],
            "ring": item["ring"],
            "group": item["group"],
            "doc_id": item["doc_id"],
            "flow_node": item["flow_node"],
            "status": status,
            "hot": is_hot,
            "activity_pct": activity,
            "metric": fn.get("metric", "governed"),
            "summary": item["summary"],
            "editable": False,
            "scratch_file": "",
        }
        notes.append(node_obj)
        note_map[item["id"]] = node_obj

    for dn in scanned.get("notes", []):
        fn = flow_nodes.get(dn["flow_node"], {})
        is_hot = bool(fn.get("hot")) or bool(dn.get("hot_disk"))
        status = fn.get("status", "ok")
        boost = 5 if is_hot else 2
        activity = min(99, dn["base_activity"] + boost)
        node_obj = {
            "id": dn["id"],
            "label": dn["label"],
            "ring": dn["ring"],
            "group": dn["group"],
            "doc_id": dn["doc_id"],
            "flow_node": dn["flow_node"],
            "status": status,
            "hot": is_hot,
            "activity_pct": activity,
            "metric": "scratch .md" if dn.get("editable") else "vault .md",
            "summary": dn["summary"],
            "editable": bool(dn.get("editable")),
            "scratch_file": dn.get("scratch_file", ""),
        }
        notes.append(node_obj)
        note_map[dn["id"]] = node_obj

    links = []
    all_raw_links = list(OBSIDIAN_LINKS) + list(scanned.get("links", []))
    for src, dst, strength, rate, kind in all_raw_links:
        if src not in note_map or dst not in note_map:
            continue
        s_node = note_map[src]
        t_node = note_map[dst]
        active = kind != "disabled" and (rate >= 3 or s_node.get("hot") or t_node.get("hot"))
        links.append({
            "source": src,
            "target": dst,
            "strength_pct": strength,
            "flow_rate": rate + (1 if (s_node.get("hot") or t_node.get("hot")) and rate > 0 else 0),
            "active": bool(active),
            "kind": kind,
        })

    return {
        "notes": notes,
        "links": links,
        "scanned_count": len(scanned.get("notes", [])),
        "plugins": [
            {"id": "flow_particles", "label": "Data Flow Trails", "enabled": True},
            {"id": "activity_heatmap", "label": "Node Activity Halo", "enabled": True},
            {"id": "connection_strength", "label": "Connection Strength", "enabled": True},
        ],
    }


def _hot(mtime: float | None, now_ts: float, window: int = 90) -> bool:
    return bool(mtime) and (now_ts - mtime) <= window


def compose_frame(*, hermes: dict, ledger: dict, gtm: dict, alerts_status: dict, inbox: dict,
                  guard_events: list, e2e_events: list, board: dict, plan: dict,
                  stats: dict, mtimes: dict, server: dict, now: datetime | None = None,
                  gateway: dict | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    now_ts = time.time()
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    def recent(ev: dict) -> bool:
        try:
            return datetime.fromisoformat(str(ev.get("timestamp_utc", "")).replace("Z", "+00:00")) >= day_ago
        except ValueError:
            return False

    guard_recent = sum(1 for ev in guard_events if isinstance(ev, dict) and not ev.get("allowed", True) and recent(ev))
    inv = ledger.get("invariant", {})
    metrics = inv.get("metrics", {})
    counts = ledger.get("counts", {})
    inbox_events = inbox.get("events") if isinstance(inbox.get("events"), list) else []
    inbox_errors = inbox.get("errors") if isinstance(inbox.get("errors"), dict) else {}
    last_e2e = e2e_events[0] if e2e_events else {}
    mode = str(hermes.get("last_execution_mode", "untested"))

    nodes: dict[str, dict[str, Any]] = {
        "hud": {"group": "aios", "label": "Cockpit HUD", "status": "ok",
                "metric": f"pid {server.get('pid')} · up {server.get('uptime_min', 0)}m",
                "detail": f"build {server.get('build')}"},
        "jev": {"group": "aios", "label": "JEV Gates L1–L10", "status": "warn" if guard_recent else "ok",
                "metric": f"{guard_recent} block(s)/24h",
                "detail": "Last E2E: " + str(last_e2e.get("outcome", "none")), "hot": _hot(mtimes.get("guard"), now_ts) or _hot(mtimes.get("e2e"), now_ts)},
        "mark": {"group": "aios", "label": "Mark LVI", "status": "ok" if stats.get("mark_actions") is not None else "idle",
                 "metric": f"{stats.get('mark_actions', '?')} actions · {stats.get('mark_plugins', '?')} plugins",
                 "detail": "5-word outcome contract"},
        "brain": {"group": "aios", "label": "Second Brain", "status": "ok" if stats.get("brain_modules") is not None else "idle",
                  "metric": f"{stats.get('brain_modules', '?')} modules", "detail": "core.md + Ring 1"},
        "hermes": {"group": "hermes", "label": "Hermes Adapter",
                   "status": "warn" if hermes.get("is_simulated") else ("ok" if hermes.get("last_status") not in (None, "none") else "idle"),
                   "metric": mode.replace("_", " "), "detail": f"last status: {hermes.get('last_status')}",
                   "hot": _hot(mtimes.get("hermes"), now_ts)},
        "model": {"group": "hermes", "label": "Local Model", "status": "ok" if hermes.get("live_loopback_reachable") else "err",
                  "metric": "reachable" if hermes.get("live_loopback_reachable") else "unreachable",
                  "detail": str(hermes.get("model", ""))},
        "inbox": {"group": "offline", "label": "Inbox Diode", "status": "warn" if inbox_errors else "ok",
                  "metric": f"{len(inbox_events)} event(s)", "count": len(inbox_events),
                  "detail": ("missing: " + ", ".join(sorted(inbox_errors))) if inbox_errors else "snapshot clean",
                  "hot": _hot(mtimes.get("inbox"), now_ts)},
        "harness": {"group": "offline", "label": "Reconciliation Harness", "status": "ok" if inv.get("passed") else "err",
                    "metric": f"{counts.get('completed', 0)} done · {counts.get('running', 0)} running",
                    "detail": "invariant " + str(inv.get("formula", "")), "hot": _hot(mtimes.get("ledger"), now_ts)},
        "quarantine": {"group": "offline", "label": "Quarantine", "status": "warn" if metrics.get("quarantined") else "ok",
                       "metric": f"{metrics.get('quarantined', 0)} row(s) · {metrics.get('duplicates', 0)} dup",
                       "count": metrics.get("quarantined", 0), "detail": "held before AP posting"},
        "gtm": {"group": "offline", "label": "GTM Outbox", "status": "info" if gtm.get("needs_review") else "ok",
                "metric": f"{gtm.get('needs_review', 0)} review / {gtm.get('total', 0)}", "count": gtm.get("needs_review", 0),
                "detail": "human approval only, no auto-send", "hot": _hot(mtimes.get("gtm"), now_ts)},
        "notify": {"group": "offline", "label": "Notification Outbox", "status": "info" if alerts_status.get("pending_outbox_events") else "ok",
                   "metric": f"{alerts_status.get('pending_outbox_events', 0)} pending", "count": alerts_status.get("pending_outbox_events", 0),
                   "detail": "zero-PII metadata", "hot": _hot(mtimes.get("notify"), now_ts)},
        "relay": {"group": "offline", "label": "SMTP Relay", "status": "idle", "metric": "manual trigger",
                  "detail": "STARTTLS, human-initiated"},
        "assignments": {"group": "aios", "label": "Assignments & Routing", "status": "ok",
                        "metric": f"{len(board.get('tasks', []))} tasks · 3 triggers",
                        "detail": "orchestrator + ledger + educate",
                        "triggers": ["aios-directed", "operator-directed", "event-driven"]},
    }
    for node in nodes.values():
        node.setdefault("hot", False)
    edges = [{"from": a, "to": b, "label": label, "active": nodes[a]["hot"] or nodes[b]["hot"]}
             for a, b, label in FLOW_EDGES]

    alerts = build_alerts(nodes, board, plan, now, guard_recent)
    obsidian = build_obsidian_graph(nodes)
    open_tasks = [t for t in board.get("tasks", []) if t.get("status") != "done"]
    body = {
        "groups": FLOW_GROUPS, "nodes": nodes, "edges": edges, "alerts": alerts,
        "obsidian": obsidian,
        "counters": {
            "inbox": len(inbox_events),
            "outbox_review": gtm.get("needs_review", 0),
            "outbox_total": gtm.get("total", 0),
            "quarantine": metrics.get("quarantined", 0),
            "gateway_crons": gateway.get("crons_enabled", 0) if gateway else 0,
            "gateway_tasks": gateway.get("tasks_executed", 0) if gateway else 0,
            "gateway_online": bool(gateway.get("hermes_online", False)) if gateway else False,
            "notify_pending": alerts_status.get("pending_outbox_events", 0),
            "alerts": len(alerts),
            "alerts_urgent": sum(1 for a in alerts if a["severity"] in ("crit", "warn")),
            "tasks_open": len(open_tasks),
            "vital_open": sum(1 for t in open_tasks if t.get("vital")),
        },
        "gateway": gateway or {},
        "board_revision": board.get("revision", 0),
    }
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return dict(body, ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), hash=fingerprint)
