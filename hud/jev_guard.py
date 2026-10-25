"""
JEV Level 6 Guardrail Engine: Pre-Tool Execution Gate and Post-Tool Result Screen.
Provides:
  1. check_bash_command(cmd): Pre-execution hook judging destructive intent, irreversibility,
     and credential leakage before OS execution.
  2. screen_tool_result(output): Post-execution hook wrapping untrusted data and defanging injection.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("HUD_STATE_DIR", str(Path(__file__).resolve().parent.parent / "state")))
GUARDRAIL_LOG = STATE_DIR / "guardrail_events.json"

# Prohibited destructive / irreversible command regex patterns
DESTRUCTIVE_PATTERNS = [
    (r"\brm\s+-(?:r|f|rf|fr)\b", "Recursive deletion command (rm -rf) detected", 0.99, True),
    (r"\bformat\s+[a-zA-Z]:", "Disk formatting command detected", 0.99, True),
    (r"\bdel\b.*(?:\*|\b(?:/[sS]|/[fF]|/[qQ]))", "Wildcard/recursive file deletion (del) detected", 0.95, True),
    (r"\bdrop\s+(?:database|table)\b", "Database drop command detected", 0.98, True),
    (r"\bmkfs\b", "Filesystem creation/overwrite command detected", 0.99, True),
    (r"\bdd\s+if=", "Raw block-device overwrite command (dd) detected", 0.98, True),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Fork-bomb pattern detected", 0.99, True),
    (r"\b(?:shutdown|reboot)\b", "System power termination command", 0.92, True),
    (r"\bgit\s+push\s+--force\b", "Destructive git push force detected", 0.96, True),
    (r"\bshred\b", "Secure file shredding command detected", 0.95, True),
]

# Sensitive credentials / environment exfiltration patterns
CREDENTIAL_PATTERNS = [
    (r"\bcurl\b.*(?:api_key|secret|token|password|openai|openrouter|gemini)", "Exfiltration of credential variables via curl", 0.96),
    (r"\bprintenv\b.*(?:KEY|SECRET|TOKEN|PASS)", "Direct inspection of sensitive environment secrets", 0.91),
    (r"(?:\bcat\b|\btype\b|\bGet-Content\b|\bhead\b|\bmore\b)\s+.*?(?:\.env|api_keys\.json|id_rsa|\.pem|\.key)", "Direct read of private credential files to stdout", 0.94),
    (r"(?:Invoke-WebRequest|iwr|wget).*-(?:Method\s+Post|Body).*(?:KEY|TOKEN)", "Outbound HTTP exfiltration of tokens", 0.95),
]

INJECTION_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"system\s+prompt",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"reveal\s+all\s+(?:keys|passwords|instructions)",
    r"bypass\s+(?:all\s+)?(?:safeguards|sandbox|guardrails|security)",
]


@dataclass(frozen=True)
class GuardrailVerdict:
    allowed: bool
    command: str
    risk_score: float
    reason: str
    irreversible: bool
    notice: str


def check_bash_command(command: str) -> GuardrailVerdict:
    """
    Pre-execution hook (Level 6 Bash Gate).
    Runs in sub-millisecond local time without calling external networks.
    """
    cmd = (command or "").strip()
    cmd_lower = cmd.lower()

    # 1. Check for destructive / irreversible patterns
    for pattern, desc, conf, irrev in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_lower):
            verdict = GuardrailVerdict(
                allowed=False,
                command=cmd,
                risk_score=conf,
                reason=desc,
                irreversible=irrev,
                notice="This block is final and must not be worked around.",
            )
            _record_guardrail_event("pre_tool_call_bash", cmd, verdict)
            return verdict

    # 2. Check for credential exfiltration
    for pattern, desc, conf in CREDENTIAL_PATTERNS:
        if re.search(pattern, cmd_lower):
            verdict = GuardrailVerdict(
                allowed=False,
                command=cmd,
                risk_score=conf,
                reason=desc,
                irreversible=True,
                notice="Credential access blocked by least-privilege policy.",
            )
            _record_guardrail_event("pre_tool_call_credential", cmd, verdict)
            return verdict

    # Command is allowed
    verdict = GuardrailVerdict(
        allowed=True,
        command=cmd,
        risk_score=0.05,
        reason="Command passed deterministic Level 6 safety rules",
        irreversible=False,
        notice="Execution permitted under monitoring.",
    )
    return verdict


def screen_tool_result(output_text: str, source_label: str = "bash_output") -> tuple[str, bool]:
    """
    Post-execution hook (Level 6 Untrusted Result Screen).
    Detects planted prompt-injection markers and wraps text as passive data.
    Returns (safe_text, was_injected).
    """
    text = str(output_text or "")
    text_lower = text.lower()

    has_injection = any(re.search(pat, text_lower) for pat in INJECTION_PATTERNS)

    if has_injection:
        # Defang closing tags
        safe_body = text.replace("<<<UNTRUSTED_DATA_END>>>", "[DEFANGED_END]")
        wrapped = (
            f"<<<UNTRUSTED_DATA_START>>>[source={source_label} | JEV_WARNING=PLANTED_INSTRUCTION_FLAGGED]\n"
            f"{safe_body}\n"
            f"<<<UNTRUSTED_DATA_END>>>"
        )
        return wrapped, True

    return text, False


def _record_guardrail_event(event_type: str, cmd: str, verdict: GuardrailVerdict) -> None:
    """Logs blocked events to state/guardrail_events.json for the HUD."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        events = []
        if GUARDRAIL_LOG.exists():
            try:
                events = json.loads(GUARDRAIL_LOG.read_text(encoding="utf-8"))
            except Exception:
                events = []

        events.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "command": cmd,
            "allowed": verdict.allowed,
            "risk_score": verdict.risk_score,
            "reason": verdict.reason,
            "notice": verdict.notice,
        })
        GUARDRAIL_LOG.write_text(json.dumps(events[-30:], indent=2), encoding="utf-8")
    except Exception:
        pass
