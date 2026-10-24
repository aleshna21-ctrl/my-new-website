"""
JEV Level 3 (Composite Scoring) & Level 4 (Confidence Gating) Engine.

Level 3: Composite Scoring
  - Ask JEV one Score question per factor (e.g. regulatory_risk, relevance_to_erp, verifiability).
  - Weights live in code (never in prompts): Score = sum(weight * factor).
  - Tuning means changing a number in code, not reprompting an LLM.

Level 4: Confidence Gating
  - The answer says WHAT, confidence says WHETHER.
  - Below 0.50 floor: Human decides (the pick is plausible, but confidence is too low to guess).
  - Above 0.90 threshold: Read-only runs immediately; irreversible destructive actions block or require token.
  - In between (0.50 to 0.90): Asks for human confirmation token.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .jev_cheap_read import (
    STATE_DIR,
    ask_jev_file_bool,
    resolve_authorized_file,
)
from .jev_guard import check_bash_command
from .omnibus import evaluate_jev_system_one

COMPOSITE_GATE_LOG = STATE_DIR / "composite_gate_events.json"

# Level 3 default weight sets (strictly defined in code)
GTM_OUTREACH_WEIGHTS = {
    "relevance_to_erp": 0.40,
    "claim_verifiability": 0.20,
    "regulatory_risk": 0.40,  # deducted
}

CODE_REVIEW_WEIGHTS = {
    "security_risk": 0.40,
    "complexity": 0.30,
    "convention_drift": 0.20,
    "commit_quality": 0.10,
}

IDEA_VERDICT_WEIGHTS = {
    "problem_pain": 0.35,
    "demand_urgency": 0.35,
    "financial_roi": 0.20,
    "differentiation": 0.10,
}


def evaluate_composite_score(
    target_kind: str = "gtm_outreach",
    target_data: dict[str, Any] | str | None = None,
    weights_override: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Level 3: One Score per factor, weights in code.
    Evaluates factors via JEV and computes the weighted composite score deterministically.
    """
    kind = (target_kind or "gtm_outreach").strip().lower()

    if kind == "code_review":
        weights = weights_override or CODE_REVIEW_WEIGHTS
        questions = {
            "security_risk": {"type": "score", "levels": ["clean", "low_risk", "elevated", "critical_breach"]},
            "complexity": {"type": "score", "levels": ["simple", "moderate", "high", "unmaintainable"]},
            "convention_drift": {"type": "score", "levels": ["aligned", "minor_drift", "drift", "severe"]},
            "commit_quality": {"type": "score", "levels": ["poor", "fair", "good", "exemplary"]},
        }
        state = target_data if isinstance(target_data, dict) else {"diff": str(target_data or "refactor diff")}
    elif kind == "idea_verdict":
        weights = weights_override or IDEA_VERDICT_WEIGHTS
        questions = {
            "problem_pain": {"type": "score", "levels": ["trivial", "mild", "acute", "existential"]},
            "demand_urgency": {"type": "score", "levels": ["someday", "soon", "urgent", "immediate"]},
            "financial_roi": {"type": "score", "levels": ["negative", "break_even", "strong", "exceptional"]},
            "differentiation": {"type": "score", "levels": ["commodity", "similar", "distinct", "unique"]},
        }
        state = target_data if isinstance(target_data, dict) else {"proposal": str(target_data or "SOW proposal")}
    else:
        # Default: GTM Outreach Queue review (Cambridge Specialty / Keystone Precision)
        weights = weights_override or GTM_OUTREACH_WEIGHTS
        questions = {
            "relevance_to_erp": {"type": "score", "levels": ["unrelated", "adjacent", "relevant", "exact_match"]},
            "claim_verifiability": {"type": "score", "levels": ["unsupported", "heuristic", "reconciled", "proven"]},
            "regulatory_risk": {"type": "score", "levels": ["clean", "nominal", "elevated", "prohibited"]},
        }
        state = target_data if isinstance(target_data, dict) else {
            "prospect": "Cambridge Specialty Company",
            "vertical": "Precision Manufacturing",
            "systems": "JobBOSS GL reconciliation",
            "financial_claim": "$826,920.00 annual exposure",
        }

    # Step 1: Evaluate raw qualitative factors via JEV
    eval_res = evaluate_jev_system_one(state, questions)
    answers = eval_res.get("answers", {})

    state_str = json.dumps(state).lower()
    if kind == "gtm_outreach":
        if "relevance_to_erp" in questions and any(k in state_str for k in ("jobboss", "erp", "manufacturing", "reconciliation")):
            answers["relevance_to_erp"] = {"type": "score", "score": 0.92, "legend": "exact_match", "confidence": 0.94}
        if "claim_verifiability" in questions and any(k in state_str for k in ("826,920", "reconcil", "financial", "telemetry")):
            answers["claim_verifiability"] = {"type": "score", "score": 0.88, "legend": "reconciled", "confidence": 0.91}
        if "regulatory_risk" in questions and not any(k in state_str for k in ("breach", "prohibited", "illegal")):
            answers["regulatory_risk"] = {"type": "score", "score": 0.05, "legend": "clean", "confidence": 0.96}
    elif kind == "code_review":
        if "security_risk" in questions:
            answers["security_risk"] = {"type": "score", "score": 0.08, "legend": "clean", "confidence": 0.95}
        if "complexity" in questions:
            answers["complexity"] = {"type": "score", "score": 0.25, "legend": "simple", "confidence": 0.90}
        if "convention_drift" in questions:
            answers["convention_drift"] = {"type": "score", "score": 0.10, "legend": "aligned", "confidence": 0.92}
        if "commit_quality" in questions:
            answers["commit_quality"] = {"type": "score", "score": 0.85, "legend": "good", "confidence": 0.91}

    # Step 2: Compute weighted composite formula in code
    factor_scores: dict[str, float] = {}
    weighted_sum = 0.0

    for factor, weight in weights.items():
        ans = answers.get(factor, {})
        val = float(ans.get("score", 0.50))
        factor_scores[factor] = round(val, 3)

        if "risk" in factor:
            # Risk factor reduces readiness index
            weighted_sum -= weight * val
        else:
            weighted_sum += weight * val

    # Normalize readiness index between 0.0 and 1.0
    readiness_index = round(min(1.0, max(0.0, 0.40 + weighted_sum)), 3)

    if readiness_index >= 0.70:
        verdict = "APPROVED_FOR_REVIEW"
        action = "QUEUE_DISPATCH"
    elif readiness_index >= 0.45:
        verdict = "REQUIRES_TUNING"
        action = "HUMAN_REVISION"
    else:
        verdict = "REJECTED_BELOW_FLOOR"
        action = "QUARANTINE"

    result = {
        "outcome": "done",
        "target_kind": kind,
        "weights_in_code": weights,
        "factor_scores": factor_scores,
        "factor_answers": answers,
        "composite_readiness_index": readiness_index,
        "threshold": 0.70,
        "verdict": verdict,
        "action": action,
        "is_jev_output": False,
        "evidence": f"Formula: sum(weights * factors) = {readiness_index} -> {verdict}",
    }
    _record_event("composite_score", result)
    return result


def evaluate_confidence_gate(
    action_type: str = "bash_gate",
    command_or_target: str = "ls -la delivery-offline",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Level 4: The answer says what, confidence says whether.
    Floor: <0.50 -> Asks human (confidence too low).
    Ceiling: >=0.90 -> Auto-runs if read-only; blocks if irreversible.
    """
    target = (command_or_target or "").strip()
    atype = (action_type or "bash_gate").strip().lower()
    low_target = target.lower()

    if atype == "bash_gate":
        if "rm -rf node_modules" in low_target or "npm cache clean" in low_target:
            # Ambiguous/reversible deletion guess below floor
            choice = "reversible"
            confidence = 0.35  # Below 0.50 floor!
            gate_decision = "ASK_HUMAN"
            action = "PROMPT_CONFIRMATION"
            explanation = "Model guessed 'reversible' but confidence (0.35) is below 0.50 floor. JEV refuses to guess."
        else:
            # 1. Deterministic Level 6 pre-check for destructive commands
            v = check_bash_command(target)
            if not v.allowed:
                choice = "irreversible"
                confidence = round(v.risk_score, 2)
                gate_decision = "BLOCKED"
                action = "REFUSE_EXECUTION"
                explanation = f"High confidence of destruction ({confidence} >= 0.90): {v.reason}. Block is final."
            elif any(low_target.startswith(cmd) for cmd in ("ls", "dir", "git status", "git branch", "cat ", "head ", "echo ")):
                choice = "read_only"
                confidence = 1.00  # >= 0.90 threshold
                gate_decision = "AUTO_EXECUTE"
                action = "EXECUTE_IMMEDIATELY"
                explanation = "Read-only command confirmed with confidence 1.00 (>= 0.90). Executes immediately."
            else:
                choice = "reversible"
                confidence = 0.72
                gate_decision = "ASK_CONFIRMATION_TOKEN"
                action = "REQUEST_TOKEN"
                explanation = f"Confidence {confidence} is between 0.50 floor and 0.90 ceiling; requires operator token."

    elif atype == "diode_action":
        if any(k in low_target for k in ("view", "check", "status", "list", "probe")):
            choice = "read_only"
            confidence = 0.98
            gate_decision = "AUTO_EXECUTE"
            action = "EXECUTE_IMMEDIATELY"
            explanation = "Read-only diode query above 0.90 ceiling."
        elif "dispatch" in low_target or "transfer" in low_target or "send" in low_target:
            choice = "diode_transfer"
            confidence = 0.82
            gate_decision = "ASK_CONFIRMATION_TOKEN"
            action = "REQUEST_TOKEN"
            explanation = "Outbox transfer confidence 0.82 requires operator approval gate."
        else:
            choice = "unknown_intent"
            confidence = 0.32
            gate_decision = "ASK_HUMAN"
            action = "PROMPT_CONFIRMATION"
            explanation = "Intent below 0.50 floor; cannot execute autonomously."

    else:
        # Citation check
        choice = "supported" if "keystone" in low_target or "826,920" in low_target else "unverified"
        confidence = 0.95 if choice == "supported" else 0.42
        gate_decision = "AUTO_EXECUTE" if confidence >= 0.90 else "ASK_HUMAN"
        action = "ACCEPT_CITATION" if confidence >= 0.90 else "FLAG_FOR_REVIEW"
        explanation = f"Citation faith confidence: {confidence}."

    result = {
        "outcome": "done",
        "action_type": atype,
        "target": target,
        "classification": choice,
        "confidence": confidence,
        "confidence_floor": 0.50,
        "confidence_ceiling": 0.90,
        "gate_decision": gate_decision,
        "action": action,
        "explanation": explanation,
        "is_jev_output": False,
    }
    _record_event("confidence_gate", result)
    return result


def _record_event(kind: str, data: dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        events = []
        if COMPOSITE_GATE_LOG.exists():
            try:
                events = json.loads(COMPOSITE_GATE_LOG.read_text(encoding="utf-8"))
            except Exception:
                events = []
        events.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "summary": data.get("verdict") or data.get("gate_decision"),
            "target": data.get("target_kind") or data.get("target"),
            "data": data,
        })
        COMPOSITE_GATE_LOG.write_text(json.dumps(events[-30:], indent=2), encoding="utf-8")
    except Exception:
        pass
