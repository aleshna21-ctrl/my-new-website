"""
JEV Level 10 Agentic JEV Engine: One Unified Tool Over State, Paths, and Command.

Implements the Level 10 capability from the 10 Levels of JEV hierarchy:
  The agent decides when to call JEV and writes the questions itself.
  One tool `ask_jev` accepts:
    - `state`: optional dictionary/object or string representing live agent context
    - `paths`: optional file paths or glob to inspect on disk (via Level 8/9)
    - `command`: optional shell command executed under Level 6 guardrails
    - `questions`: dictionary of typed questions (noul, choice, score)

The command runs through Level 6 check_bash_command first. Paths are inspected on disk
without loading raw file contents into context. Code evaluates the questions against
the composite state and returns typed answers.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from .jev_cheap_read import (
    STATE_DIR,
    ask_jev_file_bool,
    resolve_authorized_file,
)
from .jev_guard import check_bash_command, screen_tool_result
from .jev_multi_file import ask_jev_files, pick_first_file
from .omnibus import evaluate_jev_system_one

AGENTIC_JEV_LOG = STATE_DIR / "agentic_jev_events.json"


def ask_jev(
    state: dict[str, Any] | str | None = None,
    paths: list[str] | str | None = None,
    command: str | None = None,
    questions: dict[str, dict[str, Any]] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Level 10 Agentic JEV primitive:
    Combines state, disk paths, and a Level 6 guarded command into a single JEV evaluation.
    """
    q_block = questions or {
        "status_check": {
            "type": "choice",
            "options": ["nominal", "anomaly_detected", "needs_action", "other"],
        }
    }

    cmd_result: dict[str, Any] | None = None
    cmd_str = (command or "").strip()
    if cmd_str:
        # Step 1: Level 6 Pre-Execution Gate
        verdict = check_bash_command(cmd_str)
        if not verdict.allowed:
            return {
                "outcome": "failed",
                "tool": "ask_jev",
                "command": cmd_str,
                "error": f"Command blocked by JEV Level 6 Guard: {verdict.reason}",
                "blocked_by": "jev_level_6_guard",
                "risk_score": verdict.risk_score,
                "notice": verdict.notice,
                "is_jev_output": False,
            }

        # Step 2: Safe Execution under isolation
        try:
            capped_timeout = min(120, max(1, timeout))
            proc = subprocess.run(
                cmd_str,
                shell=True,
                capture_output=True,
                text=True,
                timeout=capped_timeout,
                encoding="utf-8",
                errors="replace",
            )
            stdout_screened, out_inj = screen_tool_result(proc.stdout.strip(), "agentic_stdout")
            stderr_screened, err_inj = screen_tool_result(proc.stderr.strip(), "agentic_stderr")
            cmd_result = {
                "command": cmd_str,
                "exit_code": proc.returncode,
                "success": proc.returncode == 0,
                "stdout_summary": (stdout_screened[:400] + "...") if len(stdout_screened) > 400 else stdout_screened,
                "stderr_summary": (stderr_screened[:300] + "...") if len(stderr_screened) > 300 else stderr_screened,
                "injected_flag": out_inj or err_inj,
            }
        except subprocess.TimeoutExpired:
            return {
                "outcome": "failed",
                "tool": "ask_jev",
                "command": cmd_str,
                "error": f"Command timed out after {timeout}s",
                "is_jev_output": False,
            }
        except Exception as exc:
            return {
                "outcome": "failed",
                "tool": "ask_jev",
                "command": cmd_str,
                "error": f"Command execution error: {exc}",
                "is_jev_output": False,
            }

    # Step 3: Inspect files on disk (Level 8 / 9)
    path_summaries: list[dict[str, Any]] = []
    tokens_on_disk_total = 0
    raw_paths = paths if isinstance(paths, list) else ([paths.strip()] if isinstance(paths, str) and paths.strip() else [])

    for p in raw_paths:
        res_file, err = resolve_authorized_file(p)
        if err or res_file is None:
            path_summaries.append({"path": p, "error": err or "file_not_found"})
            continue
        try:
            content = res_file.read_text(encoding="utf-8", errors="replace")
            tok = max(1, len(content) // 4)
            tokens_on_disk_total += tok
            path_summaries.append({
                "path": str(res_file).replace("\\", "/"),
                "name": res_file.name,
                "lines": len(content.splitlines()),
                "tokens_on_disk": tok,
                "lead_snippet": content[:250].replace("\n", " "),
            })
        except Exception as exc:
            path_summaries.append({"path": p, "error": str(exc)})

    # Step 4: Assemble composite state for JEV decision
    composite_state: dict[str, Any] = {
        "user_state": state if isinstance(state, dict) else {"state_value": state},
        "command_result": cmd_result,
        "path_summaries": path_summaries,
    }

    # Step 5: Evaluate questions with JEV System-One evaluator
    eval_res = evaluate_jev_system_one(composite_state, q_block)
    answers = eval_res.get("answers", {})

    result = {
        "outcome": "done",
        "tool": "ask_jev",
        "command": cmd_str if cmd_str else None,
        "command_success": cmd_result.get("success") if cmd_result else None,
        "paths_evaluated": len(path_summaries),
        "tokens_judged_on_disk": tokens_on_disk_total,
        "tokens_added_to_agent_context": 0,
        "answers": answers,
        "composite_state_summary": {
            "has_state": state is not None,
            "has_command": bool(cmd_str),
            "paths_count": len(path_summaries),
        },
        "is_jev_output": False,
    }
    _record_agentic_event(result)
    return result


def triage_failure(
    failure_context: str | dict[str, Any],
    command: str | None = None,
    candidate_paths: list[str] | str | None = None,
) -> dict[str, Any]:
    """Level 10 Option A: Triage a failure (classify bug in code vs environment vs test)."""
    questions = {
        "failure_classification": {
            "type": "choice",
            "options": ["bug_in_code", "environment_issue", "wrong_test", "stale_dependency", "other"],
        },
        "severity": {
            "type": "score",
            "levels": ["minor", "operational", "blocking", "critical"],
        },
        "can_auto_retry": {
            "type": "noul",
            "question": "Can this failure be safely retried without code modification?",
        },
    }
    return ask_jev(state=failure_context, paths=candidate_paths, command=command, questions=questions)


def judge_diff(
    diff_text: str,
    target_files: list[str] | str | None = None,
) -> dict[str, Any]:
    """Level 10 Option B: Judge a diff before shipping (risk score + human review gate)."""
    questions = {
        "risk_level": {
            "type": "score",
            "levels": ["low", "moderate", "elevated", "high_risk"],
        },
        "requires_human_review": {
            "type": "noul",
            "question": "Does this diff modify critical security, financial, or architectural rules?",
        },
        "change_intent": {
            "type": "choice",
            "options": ["bug_fix", "feature_addition", "refactor", "security_hardening", "other"],
        },
    }
    return ask_jev(state={"diff": diff_text[:1200]}, paths=target_files, questions=questions)


def gate_plan(
    customer_request: str,
    target_paths: list[str] | str | None = None,
) -> dict[str, Any]:
    """Level 10 Option C: Classify a request and gate an execution plan."""
    questions = {
        "plan_approval": {
            "type": "choice",
            "options": ["auto_approve", "requires_confirmation", "reject_policy_violation", "other"],
        },
        "policy_risk": {
            "type": "score",
            "levels": ["safe", "cautionary", "high_risk", "policy_breach"],
        },
        "is_out_of_scope": {
            "type": "noul",
            "question": "Does the request ask for actions outside authorized boundaries?",
        },
    }
    return ask_jev(state={"request": customer_request}, paths=target_paths, questions=questions)


def _record_agentic_event(res: dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        events = []
        if AGENTIC_JEV_LOG.exists():
            try:
                events = json.loads(AGENTIC_JEV_LOG.read_text(encoding="utf-8"))
            except Exception:
                events = []
        events.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "tool": res.get("tool"),
            "command": res.get("command"),
            "paths_evaluated": res.get("paths_evaluated", 0),
            "tokens_judged_on_disk": res.get("tokens_judged_on_disk", 0),
            "tokens_added_to_agent_context": 0,
            "answers": res.get("answers"),
        })
        AGENTIC_JEV_LOG.write_text(json.dumps(events[-30:], indent=2), encoding="utf-8")
    except Exception:
        pass
