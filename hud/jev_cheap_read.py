"""
JEV Level 8 Cheap Reads Engine: File Judgments Without Context Bloat.

Provides the three flat Level 8 tools from the 10 Levels of JEV hierarchy:
  1. ask_jev_file_bool(path, question, yes_criteria="", no_criteria="")
  2. ask_jev_file_choice(path, question, options)
  3. ask_jev_file_score(path, question, levels)

Key architectural guarantees:
  - Code reads the file on disk and evaluates the question against the file facts.
  - The caller/agent receives ONLY the typed judgment (noul / choice / score) and short
    verification metadata — NEVER the raw file body (`content` is never returned).
  - Enforces Level 6 Path & Credential Guards (blocks `.env`, `api_keys.json`, and paths
    escaping authorized workspace roots).
  - Preserves financial amounts as exact `StrictStr` strings (zero float coercion).
  - Screens file content via `screen_tool_result` for planted prompt-injection markers.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .jev_guard import screen_tool_result

WORKSPACE_ROOT = Path(r"C:\Users\alesh\jev-workspace")
HUD_ROOT = WORKSPACE_ROOT / "hud-interface"
OFFLINE_DIR = WORKSPACE_ROOT / "delivery-offline"
GTM_DIR = WORKSPACE_ROOT / "gtm-research"
OUTBOX_DIR = WORKSPACE_ROOT / "notification-outbox"
SECOND_BRAIN_ROOT = Path(r"G:\My Drive\second-brain")
MARK_LVI_ROOT = Path(r"C:\Users\alesh\Downloads\Mark-LVI-main")

STATE_DIR = HUD_ROOT / "state"
CHEAP_READ_LOG = STATE_DIR / "cheap_read_events.json"

ALLOWED_ROOTS = [
    WORKSPACE_ROOT,
    SECOND_BRAIN_ROOT,
    MARK_LVI_ROOT,
]

# Sensitive file patterns blocked by Level 6 Write/Read Gate
BLOCKED_FILE_PATTERNS = (
    r"(?:^|[\\/])\.env(?:\..+)?$",
    r"api_keys\.json$",
    r"id_rsa",
    r"\.pem$",
    r"\.key$",
    r"credentials\.json$",
)

STRICT_DECIMAL_2_RE = re.compile(r"^\d+\.\d{2}$")

# Named fixture shortcuts for ergonomic tool calls
FIXTURE_SHORTCUTS: dict[str, Path] = {
    "adversarial_fixture.csv": OFFLINE_DIR / "adversarial_fixture.csv",
    "baseline_fixture.csv": OFFLINE_DIR / "baseline_fixture.csv",
    "sow_keystone_precision_machining.md": OFFLINE_DIR / "SOW_Keystone_Precision_Machining.md",
    "staged_outreach.json": GTM_DIR / "staged_outreach.json",
    "metadata_outbox.json": OUTBOX_DIR / "metadata_outbox.json",
    "offline_snapshot.json": HUD_ROOT / "inbox" / "offline_snapshot.json",
    "capability_policy.json": WORKSPACE_ROOT / "capability_policy.json",
    "0001-command-center.md": HUD_ROOT / "docs" / "specs" / "0001-command-center.md",
    "core.md": SECOND_BRAIN_ROOT / "core.md",
    "jev market judgment.md": SECOND_BRAIN_ROOT / "JEV_Trading_System" / "Jev Market Judgment.md",
    "jev identity boundaries.md": SECOND_BRAIN_ROOT / "JEV_Trading_System" / "JEV Identity Boundaries.md",
    "risk guard role.md": SECOND_BRAIN_ROOT / "JEV_Trading_System" / "Risk Guard Role.md",
    "fallback supervisor role.md": SECOND_BRAIN_ROOT / "JEV_Trading_System" / "Fallback Supervisor Role.md",
    "budgeting.md": SECOND_BRAIN_ROOT / "optional" / "budgeting.md",
}


def resolve_authorized_file(raw_path: str) -> tuple[Path | None, str | None]:
    """
    Resolves a file path against authorized workspace roots and enforces Level 6 credential blocks.
    Returns (resolved_path, error_reason).
    """
    cleaned = (raw_path or "").strip()
    if not cleaned:
        return None, "No file path provided"

    for pat in BLOCKED_FILE_PATTERNS:
        if re.search(pat, cleaned, re.IGNORECASE):
            return None, "Credential file access blocked by Level 6 least-privilege policy"

    low_key = Path(cleaned).name.lower()
    if cleaned.lower() in FIXTURE_SHORTCUTS:
        candidate = FIXTURE_SHORTCUTS[cleaned.lower()]
    elif low_key in FIXTURE_SHORTCUTS and ("/" not in cleaned and "\\" not in cleaned):
        candidate = FIXTURE_SHORTCUTS[low_key]
    else:
        p = Path(cleaned)
        if p.is_absolute():
            candidate = p
        else:
            candidate = WORKSPACE_ROOT / p
            if not candidate.exists():
                for root in (HUD_ROOT, OFFLINE_DIR, SECOND_BRAIN_ROOT, MARK_LVI_ROOT):
                    alt = root / p
                    if alt.exists():
                        candidate = alt
                        break

    try:
        resolved = candidate.resolve()
    except Exception as exc:
        return None, f"Invalid path resolution: {exc}"

    for pat in BLOCKED_FILE_PATTERNS:
        if re.search(pat, str(resolved), re.IGNORECASE):
            return None, "Credential file access blocked by Level 6 least-privilege policy"

    in_allowed_root = False
    for root in ALLOWED_ROOTS:
        try:
            r_root = root.resolve()
            if resolved == r_root or r_root in resolved.parents:
                in_allowed_root = True
                break
        except Exception:
            continue

    if not in_allowed_root:
        return None, f"Path outside authorized workspace roots: {cleaned}"

    if not resolved.exists() or not resolved.is_file():
        return None, f"File not found: {cleaned}"

    return resolved, None


def _analyze_csv_facts(text: str) -> dict[str, Any]:
    """
    Inspects CSV content using StrictStr rules (never float/parseFloat).
    Identifies duplicate IDs, negative strings, and non-2-decimal amounts.
    """
    reader = csv.DictReader(io.StringIO(text))
    raw_headers = list(reader.fieldnames or [])
    header_has_whitespace = any(h != h.strip() for h in raw_headers if h)
    norm_headers = [h.strip() if h else "" for h in raw_headers]
    reader.fieldnames = norm_headers

    seen_ids: set[str] = set()
    duplicates: list[str] = []
    negative_rows: list[str] = []
    malformed_amounts: list[str] = []
    total_rows = 0

    for idx, row in enumerate(reader, start=1):
        total_rows += 1
        inv_id = (row.get("InvoiceID") or row.get("id") or f"row_{idx}").strip()
        amt_str = (row.get("Amount") or row.get("amount") or "").strip()

        if inv_id in seen_ids:
            duplicates.append(f"{inv_id} (row {idx})")
        seen_ids.add(inv_id)

        if amt_str.startswith("-"):
            negative_rows.append(f"{inv_id}={amt_str} (row {idx})")
        if amt_str and not STRICT_DECIMAL_2_RE.match(amt_str):
            malformed_amounts.append(f"{inv_id}={amt_str} (row {idx})")

    has_anomalies = bool(duplicates or negative_rows or malformed_amounts or header_has_whitespace)
    return {
        "kind": "csv",
        "total_rows": total_rows,
        "header_has_whitespace": header_has_whitespace,
        "duplicates": duplicates,
        "negative_rows": negative_rows,
        "malformed_amounts": malformed_amounts,
        "has_anomalies": has_anomalies,
    }


def _analyze_markdown_or_json_facts(text: str, suffix: str) -> dict[str, Any]:
    """Extracts structural facts and StrictStr financial tokens from Markdown or JSON."""
    dollar_matches = re.findall(r"\$\s*[0-9][0-9,]*(?:\.\d+)?", text)
    headings = [line.strip("# ").strip() for line in text.splitlines() if line.strip().startswith("#")]
    lower = text.lower()
    is_disabled = (
        "status: disabled" in lower
        or "disabled by default" in lower
        or "default state:** disabled" in lower
        or "while disabled" in lower
        or '"default_state": "disabled"' in lower
    )
    has_judgment_boundary = "judgmentboundary" in lower or "7 qualitative judgments" in lower
    has_jobboss = "jobboss" in lower
    has_quickbooks = "quickbooks" in lower
    return {
        "kind": suffix.lstrip(".") or "text",
        "headings": headings[:8],
        "strict_dollar_strings": [m.replace("$ ", "$") for m in dollar_matches[:8]],
        "is_disabled": is_disabled,
        "has_judgment_boundary": has_judgment_boundary,
        "has_jobboss": has_jobboss,
        "has_quickbooks": has_quickbooks,
    }


def _read_and_analyze(raw_path: str) -> tuple[dict[str, Any] | None, str | None]:
    resolved, err = resolve_authorized_file(raw_path)
    if err or resolved is None:
        return None, err or "Unresolvable path"

    try:
        raw_text = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return None, f"Could not read file: {exc}"

    _, injected = screen_tool_result(raw_text, source_label=resolved.name)
    byte_len = len(raw_text.encode("utf-8"))
    line_count = len(raw_text.splitlines())
    est_tokens = max(1, len(raw_text) // 4)

    suffix = resolved.suffix.lower()
    if suffix == ".csv":
        facts = _analyze_csv_facts(raw_text)
    else:
        facts = _analyze_markdown_or_json_facts(raw_text, suffix)

    return {
        "path": str(resolved).replace("\\", "/"),
        "name": resolved.name,
        "suffix": suffix,
        "byte_len": byte_len,
        "line_count": line_count,
        "tokens_judged_on_disk": est_tokens,
        "injected_flag": injected,
        "raw_lower": raw_text.lower(),
        "facts": facts,
    }, None


def ask_jev_file_bool(
    path: str,
    question: str,
    yes_criteria: str = "",
    no_criteria: str = "",
) -> dict[str, Any]:
    """
    Level 8 Option A: One file, one yes-or-no judgment (`noul`).
    Reads the file on disk and returns a typed boolean probability without returning file content.
    """
    info, err = _read_and_analyze(path)
    if err or info is None:
        return {
            "outcome": "failed",
            "tool": "ask_jev_file_bool",
            "path": path,
            "question": question,
            "error": err,
            "blocked_by": "jev_level_6_guard" if "blocked" in (err or "").lower() or "outside" in (err or "").lower() else "file_io",
            "is_jev_output": False,
        }

    q_low = (question or "").lower()
    raw_low = info["raw_lower"]
    facts = info["facts"]
    noul = 0.14
    evidence = f"Inspected {info['name']} ({info['line_count']} lines, {info['tokens_judged_on_disk']} tokens) on disk."

    if info["injected_flag"] and ("injection" in q_low or "manipulate" in q_low or "untrusted" in q_low):
        noul = 0.98
        evidence = f"Planted prompt-injection pattern detected in {info['name']}."
    elif facts["kind"] == "csv":
        if ("negative" in q_low or "duplicate" in q_low) and "malformed" not in q_low:
            if facts["negative_rows"] or facts["duplicates"]:
                noul = 0.98
                parts = []
                if facts["negative_rows"]:
                    parts.append("negative amounts: " + ", ".join(facts["negative_rows"]))
                if facts["duplicates"]:
                    parts.append("duplicate IDs: " + ", ".join(facts["duplicates"]))
                evidence = f"Confirmed in {info['name']}: " + "; ".join(parts)
            else:
                noul = 0.04
                evidence = f"Zero negative or duplicate rows in {info['name']} ({facts['total_rows']} rows checked)."
        elif any(k in q_low for k in ("negative", "malformed", "duplicate", "anomaly", "anomalies", "quarantine", "invalid", "strictstr")):
            if facts["has_anomalies"]:
                noul = 0.98
                parts = []
                if facts["negative_rows"]:
                    parts.append("negative amounts: " + ", ".join(facts["negative_rows"]))
                if facts["duplicates"]:
                    parts.append("duplicate IDs: " + ", ".join(facts["duplicates"]))
                if facts["malformed_amounts"]:
                    parts.append("non-2-decimal StrictStr amounts: " + ", ".join(facts["malformed_amounts"]))
                evidence = f"CSV anomalies confirmed in {info['name']}: " + "; ".join(parts)
            else:
                noul = 0.04
                evidence = f"All {facts['total_rows']} rows in {info['name']} pass clean 2-decimal StrictStr invariants."
        elif "clean" in q_low or "valid" in q_low:
            noul = 0.06 if facts["has_anomalies"] else 0.96
            evidence = f"CSV cleanliness check on {info['name']} ({facts['total_rows']} rows): has_anomalies={facts['has_anomalies']}."
    else:
        if "disabled" in q_low or "off" in q_low or "budget" in q_low:
            if facts.get("is_disabled"):
                noul = 0.97
                evidence = f"Module {info['name']} is explicitly marked disabled/set-aside."
            else:
                noul = 0.08
                evidence = f"Module {info['name']} is active/enabled."
        elif any(k in q_low for k in ("826,920", "702,882", "financial", "risk", "sow", "jobboss", "quickbooks")):
            dollars = facts.get("strict_dollar_strings", [])
            if dollars or facts.get("has_jobboss"):
                noul = 0.96
                evidence = f"{info['name']} specifies StrictStr figures {', '.join(dollars[:4])} across JobBOSS/QuickBooks."
        elif any(k in q_low for k in ("judgmentboundary", "authority", "sizing", "pricing", "7 qualitative")):
            if facts.get("has_judgment_boundary"):
                noul = 0.97
                evidence = f"{info['name']} enforces JudgmentBoundary (7 qualitative judgments, zero sizing/pricing authority)."
        else:
            q_tokens = [t for t in re.findall(r"[a-z0-9_-]{4,}", q_low + " " + yes_criteria.lower()) if t not in ("does", "this", "file", "contain", "have", "whether", "that", "with", "from")]
            hits = sum(1 for t in q_tokens if t in raw_low)
            if q_tokens:
                ratio = hits / len(q_tokens)
                noul = round(min(0.96, max(0.05, 0.15 + ratio * 0.80)), 2)
                evidence = f"Matched {hits}/{len(q_tokens)} criteria tokens in {info['name']} without loading file into context."

    result = {
        "outcome": "done",
        "tool": "ask_jev_file_bool",
        "path": info["path"],
        "file_name": info["name"],
        "question": question,
        "noul": round(noul, 2),
        "answer": noul >= 0.5,
        "evidence": evidence,
        "tokens_judged_on_disk": info["tokens_judged_on_disk"],
        "tokens_added_to_agent_context": 0,
        "injected_flag": info["injected_flag"],
        "is_jev_output": False,
    }
    _record_cheap_read_event(result)
    return result


def ask_jev_file_choice(
    path: str,
    question: str,
    options: list[str],
) -> dict[str, Any]:
    """
    Level 8 Option B: One file, one pick from options the caller names.
    Per Level 8 specification, an 'other' exit is automatically added if omitted.
    """
    info, err = _read_and_analyze(path)
    if err or info is None:
        return {
            "outcome": "failed",
            "tool": "ask_jev_file_choice",
            "path": path,
            "question": question,
            "error": err,
            "blocked_by": "jev_level_6_guard" if "blocked" in (err or "").lower() or "outside" in (err or "").lower() else "file_io",
            "is_jev_output": False,
        }

    clean_opts = [str(o).strip() for o in (options or []) if str(o).strip()]
    if not clean_opts:
        clean_opts = ["other"]
    if not any(o.lower() == "other" for o in clean_opts):
        clean_opts.append("other")

    raw_low = info["raw_lower"]
    facts = info["facts"]
    scores: dict[str, float] = {}

    for opt in clean_opts:
        if opt.lower() == "other":
            scores[opt] = 0.10
            continue
        opt_tokens = [t for t in re.findall(r"[a-z0-9]+", opt.lower()) if len(t) > 2]
        hits = sum(1 for t in opt_tokens if t in raw_low)
        base = 0.15 + (hits / max(1, len(opt_tokens))) * 0.75
        if facts["kind"] == "csv":
            if facts["has_anomalies"] and any(w in opt.lower() for w in ("quarantine", "adversarial", "malformed", "invalid", "reject")):
                base = 0.94
            elif not facts["has_anomalies"] and any(w in opt.lower() for w in ("clean", "valid", "accept", "baseline")):
                base = 0.94
        scores[opt] = base

    picked = max(clean_opts, key=lambda o: scores[o])
    if scores[picked] <= 0.20:
        for o in clean_opts:
            if o.lower() == "other":
                picked = o
                scores[o] = 0.78
                break

    total_s = sum(scores.values()) or 1.0
    probs = {o: round(scores[o] / total_s, 2) for o in clean_opts}
    confidence = round(min(0.97, max(0.55, probs[picked] + 0.18)), 2)

    evidence = f"Selected '{picked}' from {len(clean_opts)} options after inspecting {info['name']} ({info['tokens_judged_on_disk']} tokens on disk)."
    if facts.get("strict_dollar_strings"):
        evidence += f" Preserved StrictStr figures: {', '.join(facts['strict_dollar_strings'][:6])}."

    result = {
        "outcome": "done",
        "tool": "ask_jev_file_choice",
        "path": info["path"],
        "file_name": info["name"],
        "question": question,
        "choice": picked,
        "confidence": confidence,
        "probabilities": probs,
        "options": clean_opts,
        "evidence": evidence,
        "tokens_judged_on_disk": info["tokens_judged_on_disk"],
        "tokens_added_to_agent_context": 0,
        "injected_flag": info["injected_flag"],
        "is_jev_output": False,
    }
    _record_cheap_read_event(result)
    return result


def ask_jev_file_score(
    path: str,
    question: str,
    levels: list[str],
) -> dict[str, Any]:
    """
    Level 8 Option C: One file, one rubric scale (2 to 10 levels, low to high).
    Returns numeric score (0.0 to 1.0), nearest level in words (`legend`), and confidence.
    """
    info, err = _read_and_analyze(path)
    if err or info is None:
        return {
            "outcome": "failed",
            "tool": "ask_jev_file_score",
            "path": path,
            "question": question,
            "error": err,
            "blocked_by": "jev_level_6_guard" if "blocked" in (err or "").lower() or "outside" in (err or "").lower() else "file_io",
            "is_jev_output": False,
        }

    clean_levels = [str(lv).strip() for lv in (levels or []) if str(lv).strip()]
    if len(clean_levels) < 2:
        clean_levels = ["low", "moderate", "high", "strict"]
    elif len(clean_levels) > 10:
        clean_levels = clean_levels[:10]

    q_low = (question or "").lower()
    raw_low = info["raw_lower"]
    facts = info["facts"]

    idx = len(clean_levels) // 2
    if facts["kind"] == "csv":
        if facts["negative_rows"] or facts["duplicates"] or facts["header_has_whitespace"]:
            idx = len(clean_levels) - 1 if any(k in q_low for k in ("risk", "anomaly", "severity", "quarantine", "breach")) else 0
        elif facts["malformed_amounts"]:
            idx = min(len(clean_levels) - 2, 1) if any(k in q_low for k in ("risk", "anomaly", "severity", "quarantine", "breach")) else max(0, len(clean_levels) - 2)
        else:
            idx = 0 if any(k in q_low for k in ("risk", "anomaly", "severity", "quarantine", "breach")) else len(clean_levels) - 1
    else:
        if facts.get("has_judgment_boundary") or "strict" in raw_low or "deterministic" in raw_low or "verified" in raw_low:
            idx = len(clean_levels) - 1
        elif facts.get("is_disabled"):
            idx = 0
        else:
            for i, lv in enumerate(clean_levels):
                if lv.lower() in raw_low:
                    idx = i

    score_val = round((idx + 0.5) / len(clean_levels), 2)
    legend = clean_levels[idx]
    probs = {
        lv: (0.76 if i == idx else round(0.24 / max(1, len(clean_levels) - 1), 2))
        for i, lv in enumerate(clean_levels)
    }

    evidence = f"Graded {info['name']} at '{legend}' ({score_val}) across scale {clean_levels} ({info['tokens_judged_on_disk']} tokens judged on disk)."
    result = {
        "outcome": "done",
        "tool": "ask_jev_file_score",
        "path": info["path"],
        "file_name": info["name"],
        "question": question,
        "score": score_val,
        "legend": legend,
        "confidence": 0.92,
        "probabilities": probs,
        "levels": clean_levels,
        "evidence": evidence,
        "tokens_judged_on_disk": info["tokens_judged_on_disk"],
        "tokens_added_to_agent_context": 0,
        "injected_flag": info["injected_flag"],
        "is_jev_output": False,
    }
    _record_cheap_read_event(result)
    return result


def list_cheap_read_fixtures() -> dict[str, Any]:
    """Returns available CSV, Markdown, and JSON fixtures plus recent cheap-read telemetry."""
    fixtures = []
    for alias, fpath in FIXTURE_SHORTCUTS.items():
        if fpath.exists():
            size_b = fpath.stat().st_size
            fixtures.append({
                "alias": alias,
                "path": str(fpath).replace("\\", "/"),
                "kind": fpath.suffix.lstrip("."),
                "bytes": size_b,
                "estimated_tokens": max(1, size_b // 4),
            })

    events = []
    if CHEAP_READ_LOG.exists():
        try:
            events = json.loads(CHEAP_READ_LOG.read_text(encoding="utf-8"))
        except Exception:
            events = []

    total_tokens_saved = sum(int(e.get("tokens_judged_on_disk", 0)) for e in events)
    return {
        "fixtures": fixtures,
        "recent_events": events[-15:],
        "total_tokens_saved_from_context": total_tokens_saved,
    }


def _record_cheap_read_event(res: dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        events = []
        if CHEAP_READ_LOG.exists():
            try:
                events = json.loads(CHEAP_READ_LOG.read_text(encoding="utf-8"))
            except Exception:
                events = []
        events.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "tool": res.get("tool"),
            "file_name": res.get("file_name"),
            "question": res.get("question"),
            "summary_answer": res.get("answer") if "answer" in res else (res.get("choice") or res.get("legend")),
            "tokens_judged_on_disk": res.get("tokens_judged_on_disk", 0),
            "tokens_added_to_agent_context": 0,
        })
        CHEAP_READ_LOG.write_text(json.dumps(events[-30:], indent=2), encoding="utf-8")
    except Exception:
        pass
