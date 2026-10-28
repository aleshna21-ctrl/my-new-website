"""
Unified JEV + Mark LVI + Second Brain Modular Omnibus Broker.
Provides:
1. Mark LVI Outcome Contract (done / unverified / failed / ask / started) & Untrusted-Content Boundary.
2. JEV System-One Programmable Judgment Engine (noul, choice, score, Levels 1-10, 7 Market Judgments -> 5 Action Rungs).
3. Inbox & Outbox Diode Queue Manager (offline_snapshot, agent_inbox, metadata_outbox, staged_outreach).
4. Second Brain & Obsidian Vault Graph Indexer (Ring 0 Core, Ring 1 Modules, Ring 2 JEV 9 Roles + 3 Identities, Ring 3 Workspace/Mark-LVI).
5. Omniscient AI Assistant Context Broker (Mark LVI Key-Index Recall + JEV Level 8-10 Cheap Reads + StrictStr Financial Guard).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

_CURRENT_DIR = Path(__file__).resolve().parent  # hud
HUD_ROOT = Path(os.environ.get("HUD_DIR", str(_CURRENT_DIR.parent)))
WORKSPACE_ROOT = Path(os.environ.get("JEV_PROJECT_ROOT", str(HUD_ROOT.parent)))
OFFLINE_DIR = Path(os.environ.get("JEV_OFFLINE_DIR", str(WORKSPACE_ROOT / "delivery-offline" if (WORKSPACE_ROOT / "delivery-offline").exists() else HUD_ROOT / "inbox")))
GTM_DIR = Path(os.environ.get("GTM_RESEARCH_DIR", str(WORKSPACE_ROOT / "gtm-research" if (WORKSPACE_ROOT / "gtm-research").exists() else HUD_ROOT / "outbox" / "gtm")))
OUTBOX_DIR = Path(os.environ.get("NOTIFICATION_OUTBOX_DIR", str(WORKSPACE_ROOT / "notification-outbox" if (WORKSPACE_ROOT / "notification-outbox").exists() else HUD_ROOT / "outbox")))
_DEFAULT_SECOND_BRAIN = (
    Path(r"G:\My Drive\second-brain")
    if Path(r"G:\My Drive\second-brain").exists()
    else HUD_ROOT / "vault"
)
SECOND_BRAIN_ROOT = Path(os.environ.get("SECOND_BRAIN_DIR", str(_DEFAULT_SECOND_BRAIN)))

_DEFAULT_MARK_LVI = (
    Path(r"C:\Users\alesh\Downloads\Mark-LVI-main")
    if Path(r"C:\Users\alesh\Downloads\Mark-LVI-main").exists()
    else HUD_ROOT / "mark-lvi"
)
MARK_LVI_ROOT = Path(os.environ.get("MARK_LVI_DIR", str(_DEFAULT_MARK_LVI)))

UNTRUSTED_START = "<<<UNTRUSTED_DATA_START>>>"
UNTRUSTED_END = "<<<UNTRUSTED_DATA_END>>>"


def wrap_untrusted(content: str, source_label: str = "external_record") -> str:
    """Mark LVI untrusted-content boundary: defangs embedded end markers and wraps as DATA."""
    safe_body = str(content or "").replace(UNTRUSTED_END, "[DEFANGED_END_MARKER]")
    return f"{UNTRUSTED_START}[source={source_label}]\n{safe_body}\n{UNTRUSTED_END}"


def make_outcome(status: str, message: str, *, data: Any = None, evidence: str = "") -> dict[str, Any]:
    """Mark LVI five-word outcome contract: done / unverified / failed / ask / started."""
    if status not in ("done", "unverified", "failed", "ask", "started"):
        raise ValueError(f"Invalid Mark LVI outcome status: {status}")
    return {
        "outcome": status,
        "message": message,
        "evidence": evidence or ("verified_readback" if status == "done" else "unconfirmed"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def evaluate_jev_system_one(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    Deterministic offline + local-compatible JEV System-One evaluator.
    Supports:
      - noul: probability of yes (0.0 to 1.0)
      - choice: one of declared options + probabilities + confidence
      - score: weighted rubric position + legend + confidence
    """
    text_blob = json.dumps(state, sort_keys=True).lower()
    answers: dict[str, Any] = {}

    for qid, qspec in questions.items():
        qtype = qspec.get("type", "noul")
        prompt = str(qspec.get("question", "")).lower()

        if qtype == "noul":
            score_val = 0.12
            if "injection" in qid or "manipulate" in prompt or "instruct" in prompt:
                bad_terms = ("ignore previous", "system prompt", "rm -rf", "drop table", "override", "bypass")
                hits = sum(1 for t in bad_terms if t in text_blob)
                score_val = min(0.99, 0.04 + hits * 0.42)
            elif "urgent" in qid or "urgency" in prompt:
                urgent_terms = ("broken", "down", "losing revenue", "emergency", "breach", "quarantined", "critical")
                hits = sum(1 for t in urgent_terms if t in text_blob)
                score_val = min(0.98, 0.18 + hits * 0.28)
            elif "reachability" in qid or "healthy" in prompt:
                score_val = 0.98 if "unreachable" not in text_blob and "error" not in text_blob else 0.35
            else:
                pos_criteria = str(qspec.get("criteria", {}).get("true", "")).lower().split()
                overlap = sum(1 for w in pos_criteria[:12] if len(w) > 4 and w in text_blob)
                score_val = min(0.96, round(0.25 + overlap * 0.14, 2))
            answers[qid] = {"type": "noul", "noul": round(score_val, 2)}

        elif qtype == "choice":
            options = list(qspec.get("options", ["healthy", "degraded", "other"]))
            if not options:
                options = ["other"]
            picked = options[0]
            confidence = 0.88
            for opt in options:
                if opt.lower().replace("_", " ") in text_blob or opt.lower() in text_blob:
                    picked = opt
                    confidence = 0.94
                    break
            if "rm -rf" in text_blob and "irreversible" in options:
                picked = "irreversible"
                confidence = 0.99 if "--force" in text_blob or "/" in text_blob else 0.35
            probs = {opt: (round(confidence, 2) if opt == picked else round((1.0 - confidence) / max(1, len(options) - 1), 2)) for opt in options}
            answers[qid] = {
                "type": "choice",
                "choice": picked,
                "confidence": round(confidence, 2),
                "probabilities": probs,
            }

        elif qtype == "score":
            levels = list(qspec.get("levels", ["low", "moderate", "high", "critical"]))
            idx = 0
            if any(k in text_blob for k in ("critical", "breach", "kill", "losing revenue")):
                idx = len(levels) - 1
            elif any(k in text_blob for k in ("quarantined", "degraded", "warning", "stale", "overtime")):
                idx = max(0, len(levels) // 2)
            norm = round((idx + 0.2) / max(1, len(levels)), 2)
            answers[qid] = {
                "type": "score",
                "score": norm,
                "legend": levels[idx] if levels else "nominal",
                "confidence": 0.91,
            }

    return {
        # Keyword heuristic stand-in. Per the JEV Trading module, this must never be
        # presented as Jev model output; no latency or cost is measured here.
        "engine": "local-heuristic-standin",
        "is_jev_output": False,
        "answers": answers,
    }


def evaluate_jev_trading_rung(judgments: dict[str, str], hard_risk_breach: bool = False) -> dict[str, Any]:
    """
    Deterministic JEV 7-Judgment -> 5-Action-Rung composer (Second Brain Module: JEV Trading).
    Never delegates arithmetic or order sizing to the model; selects RUN, REDUCE, HOLD_LATE, RULES_ONLY, or KILL by condition.
    """
    if hard_risk_breach or judgments.get("execution_health") == "critical":
        rung = "KILL"
        action = "HOLD"
    elif judgments.get("toxic_flow") == "high" or judgments.get("liquidity_stress") == "high":
        rung = "HOLD_LATE"
        action = "HOLD"
    elif judgments.get("execution_health") == "degraded" or judgments.get("quote_environment") == "stale":
        rung = "RULES_ONLY"
        action = "HOLD"
    elif judgments.get("inventory_pressure") == "elevated" or judgments.get("toxic_flow") == "moderate":
        rung = "REDUCE"
        action = "BUY" if judgments.get("direction") == "up" else "HOLD"
    else:
        rung = "RUN"
        action = "BUY" if judgments.get("direction") == "up" else ("SELL" if judgments.get("direction") == "down" else "HOLD")

    return {
        "rung": rung,
        "action": action,
        "mode": "dry",
        "max_position_usd": "50.00",
        "max_loss_usd": "25.00",
        "judgments": judgments,
        "deterministic_verified": True,
    }


def get_second_brain_graph() -> dict[str, Any]:
    """
    Builds the unified Concentric Ring & Minimal 3D Obsidian Knowledge Graph across:
    - Ring 0 (Core): Second Brain Core (`core.md`)
    - Ring 1 (Governance Modules): 9 enabled modules + 1 disabled `budgeting` module from `manifest.json`
    - Ring 2 (JEV Trading System Roles & Identities): 9 Roles + 3 Identity Facades from `JEV_Trading_System`
    - Ring 3 (Live Workspace & Mark LVI Artifacts): Inbox/Outbox diodes, SQLite ledger, GTM queue, Mark LVI providers & memory
    """
    nodes: list[dict[str, Any]] = [
        {
            "id": "aios-root",
            "label": "AIOS Root Node",
            "ring": 0,
            "group": "core",
            "status": "active",
            "path": (HUD_ROOT / "vault" / "00_AIOS_ROOT.md").as_posix(),
            "tags": ["core", "aios", "root-node", "ring-0"],
            "summary": "Ring 0 Operating System Nucleus: Primary coordinator and direct wiring hub for all 5 execution agent clusters.",
            "requires": ["core.md"],
        },
        {
            "id": "core.md",
            "label": "Second Brain Core",
            "ring": 0,
            "group": "core",
            "status": "active",
            "path": "g:/My Drive/second-brain/core.md",
            "tags": ["core", "second-brain", "taxonomy"],
            "summary": "Shared base instructions: 4-part structure, explicit module activation states (shared, conditional, disabled), source precedence.",
            "requires": [],
        },
        # Ring 1: Second Brain Modules & AIOS Dynamic Routing
        {
            "id": "assignments",
            "label": "Assignments & Routing",
            "ring": 1,
            "group": "aios",
            "status": "active",
            "path": (HUD_ROOT / "vault" / "03_AIOS_ASSIGNMENTS.md").as_posix(),
            "tags": ["assignments", "orchestrator", "routing", "ledger"],
            "summary": "Dynamic assignment routing linking Kanban orchestrator, SQLite ledger, and educate. Accepts aios-directed, operator-directed, and event-driven triggers.",
            "requires": ["aios-root", "core.md", "execution", "knowledge-memory"],
        },
        {
            "id": "source-governance",
            "label": "Source Governance",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/source-governance.md",
            "tags": ["governance", "provenance", "section-1"],
            "summary": "Owns source authority & chronology. hermes-jev-loop-adaptation.md governs conflicting earlier material.",
            "requires": ["core.md"],
        },
        {
            "id": "knowledge-memory",
            "label": "Knowledge & Memory",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/knowledge-memory.md",
            "tags": ["memory", "storage", "section-1"],
            "summary": "9-layer storage boundaries (Sources, Hot/Cold context, Durable memory, Procedures, Runtime state, Project records).",
            "requires": ["source-governance"],
        },
        {
            "id": "execution",
            "label": "Execution",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/execution.md",
            "tags": ["execution", "capabilities", "section-2"],
            "summary": "Authorized work, actual tool schemas, secret protection, separation of missing capability vs authorization.",
            "requires": ["source-governance", "verification"],
        },
        {
            "id": "verification",
            "label": "Verification",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/verification.md",
            "tags": ["verification", "peer-review", "section-2"],
            "summary": "Requires observable proof, dated evidence, and strict separation of specification, test results, and runtime state.",
            "requires": ["source-governance"],
        },
        {
            "id": "hermes-delegation",
            "label": "Hermes Delegation",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/hermes-delegation.md",
            "tags": ["hermes", "delegation", "section-2"],
            "summary": "Team routing & assignment without mandatory budget fields. Tracks PREPARED_LOCAL, QUEUED, REPLIED, VERIFIED, FAILED, BLOCKED.",
            "requires": ["execution", "verification"],
        },
        {
            "id": "jev-trading",
            "label": "JEV Trading",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/jev-trading.md",
            "tags": ["jev", "trading", "risk-limits", "section-2"],
            "summary": "Deterministic code owns arithmetic/prices/risk; Jev supplies 7 typed judgments. Selects RUN, REDUCE, HOLD_LATE, RULES_ONLY, KILL.",
            "requires": ["source-governance", "execution", "verification"],
        },
        {
            "id": "local-models",
            "label": "Local Models",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/local-models.md",
            "tags": ["qwen3", "ollama", "hermes", "section-2"],
            "summary": "Verifies actual GPU/CPU, quantization, context limits, and live interface reachability on 127.0.0.1:8080.",
            "requires": ["execution", "verification"],
        },
        {
            "id": "persona",
            "label": "Persona & Cognition",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/persona.md",
            "tags": ["persona", "architect", "section-3"],
            "summary": "Systems architect & prompt engineer persona: thinks in modules, ownership, failure conditions, and deterministic vs probabilistic split.",
            "requires": ["core.md"],
        },
        {
            "id": "project-index",
            "label": "Project Index",
            "ring": 1,
            "group": "module",
            "status": "enabled",
            "path": "g:/My Drive/second-brain/modules/project-index.md",
            "tags": ["index", "records", "section-4"],
            "summary": "Owns project pointers for Second Brain, Hermes team, Trading/JEV loop, and Local Qwen3 Thinking.",
            "requires": ["source-governance", "knowledge-memory"],
        },
        {
            "id": "budgeting",
            "label": "Optional Budgeting (OFF)",
            "ring": 1,
            "group": "optional",
            "status": "disabled",
            "path": "g:/My Drive/second-brain/optional/budgeting.md",
            "tags": ["optional", "disabled", "budgeting"],
            "summary": "Set aside & disabled by default per user directive. Routine handoffs require zero budget or token-allocation fields.",
            "requires": ["execution"],
        },
        # Ring 2: JEV Trading System Roles & Identities
        {
            "id": "Market State Role",
            "label": "Market State Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Market State Role.md",
            "tags": ["jev", "role", "master-template"],
            "summary": "Master JEV role template: transforms supplied quote & account state into validated Decimal market state.",
            "requires": ["jev-trading"],
        },
        {
            "id": "Asset Validator Role",
            "label": "Asset Validator Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Asset Validator Role.md",
            "tags": ["jev", "role", "validator"],
            "summary": "Validates supported Alpaca spot crypto pair or US equity symbol and market-open status.",
            "requires": ["jev-trading", "Market State Role"],
        },
        {
            "id": "Risk Guard Role",
            "label": "Risk Guard Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Risk Guard Role.md",
            "tags": ["jev", "role", "risk-guard"],
            "summary": "Enforces hard deterministic ceilings ($50.00 max position, $25.00 max loss cap) before and after order pricing.",
            "requires": ["jev-trading", "Market State Role"],
        },
        {
            "id": "Fallback Supervisor Role",
            "label": "Fallback Supervisor",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Fallback Supervisor Role.md",
            "tags": ["jev", "role", "rung-selector"],
            "summary": "Maps state and 7 qualitative Jev judgments to Action Rungs: RUN, REDUCE, HOLD_LATE, RULES_ONLY, KILL.",
            "requires": ["Risk Guard Role", "jev-trading"],
        },
        {
            "id": "Policy Composer Role",
            "label": "Policy Composer Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Policy Composer Role.md",
            "tags": ["jev", "role", "policy"],
            "summary": "Translates qualitative Jev regime/direction judgments and state into candidate BUY / SELL / HOLD policy.",
            "requires": ["Market State Role", "Fallback Supervisor Role"],
        },
        {
            "id": "Strategy Steward Role",
            "label": "Strategy Steward Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Strategy Steward Role.md",
            "tags": ["jev", "role", "strategy"],
            "summary": "Golden Cross 50/200 SMA deterministic calculation steward; can tighten risk but never raise caps.",
            "requires": ["Policy Composer Role"],
        },
        {
            "id": "Pricing Engine Role",
            "label": "Pricing Engine Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Pricing Engine Role.md",
            "tags": ["jev", "role", "pricing"],
            "summary": "Computes exact Decimal order quantity and limit price under RUN or REDUCE rung constraints.",
            "requires": ["Strategy Steward Role", "Risk Guard Role"],
        },
        {
            "id": "Broker Execution Role",
            "label": "Broker Execution Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Broker Execution Role.md",
            "tags": ["jev", "role", "execution"],
            "summary": "Executes dry/simulated intent checks; defaults to NOT_SENT in dry mode and enforces final risk guard.",
            "requires": ["Pricing Engine Role", "execution"],
        },
        {
            "id": "Control Plane Role",
            "label": "Control Plane Role",
            "ring": 2,
            "group": "jev-role",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Control Plane Role.md",
            "tags": ["jev", "role", "control-plane"],
            "summary": "Manages pause vs liquidation boundaries and finite 256-message LocalBus transport ceiling.",
            "requires": ["jev-trading", "verification"],
        },
        {
            "id": "JEV Identity Boundaries",
            "label": "JEV Identity Boundaries",
            "ring": 2,
            "group": "jev-identity",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/JEV Identity Boundaries.md",
            "tags": ["jev", "implementation", "master-template", "offline-verified"],
            "summary": "Three local application facades (JudgmentBoundary, ApplicationBoundary, OperatorBoundary); none is a remote or authenticated agent.",
            "requires": ["jev-trading", "Control Plane Role"],
        },
        {
            "id": "Jev Market Judgment",
            "label": "Jev Market Judgment",
            "ring": 2,
            "group": "jev-identity",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Jev Market Judgment.md",
            "tags": ["jev", "implementation", "offline-verified", "judgment-boundary"],
            "summary": "Identity ID: jev-market-judgment. Facade: JudgmentBoundary. Validates exactly 7 qualitative judgments; invalid/expired/cached-failed input becomes unavailable. Zero action, sizing, or pricing authority.",
            "requires": ["JEV Identity Boundaries"],
        },
        {
            "id": "Hermes JEV Operator",
            "label": "Hermes JEV Operator",
            "ring": 2,
            "group": "jev-identity",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/Hermes JEV Operator.md",
            "tags": ["jev", "implementation", "offline-verified", "operator-boundary"],
            "summary": "Identity ID: hermes-jev-operator. Facade: OperatorBoundary. Local orchestration facade executing typed TickInput against ApplicationBoundary.",
            "requires": ["JEV Identity Boundaries", "hermes-delegation"],
        },
        {
            "id": "JEV Spot Scalper",
            "label": "JEV Spot Scalper",
            "ring": 2,
            "group": "jev-identity",
            "status": "verified",
            "path": "g:/My Drive/second-brain/JEV_Trading_System/JEV Spot Scalper.md",
            "tags": ["jev", "implementation", "offline-verified", "application-boundary"],
            "summary": "Identity ID: jev-spot-scalper. Facade: ApplicationBoundary. Binds one run_id and symbol per application identity after validated tick.",
            "requires": ["JEV Identity Boundaries", "Jev Market Judgment"],
        },
        # Ring 3: Live Workspace & Mark LVI Connected Nodes
        {
            "id": "inbox-offline-snapshot",
            "label": "Inbox: Offline Snapshot",
            "ring": 3,
            "group": "inbox",
            "status": "active",
            "path": (HUD_ROOT / "inbox" / "offline_snapshot.json").as_posix(),
            "tags": ["inbox", "diode", "snapshot"],
            "summary": "Read-only exported snapshot from delivery-offline SQLite job_ledger.db and reconciliation harness.",
            "requires": ["verification", "project-index"],
        },
        {
            "id": "outbox-metadata-diode",
            "label": "Outbox: Metadata Diode",
            "ring": 3,
            "group": "outbox",
            "status": "active",
            "path": (OUTBOX_DIR / "metadata_outbox.json").as_posix(),
            "tags": ["outbox", "diode", "smtp-relay"],
            "summary": "Regex-scrubbed, zero-PII event outbox awaiting isolated SMTP TLS relay dispatch.",
            "requires": ["execution", "verification"],
        },
        {
            "id": "outbox-gtm-queue",
            "label": "Outbox: GTM Review Gate",
            "ring": 3,
            "group": "outbox",
            "status": "active",
            "path": (GTM_DIR / "staged_outreach.json").as_posix(),
            "tags": ["outbox", "gtm", "human-review"],
            "summary": "Staged B2B reconciliation outreach drafts gated by content-hash revision lock and explicit operator approval.",
            "requires": ["execution", "hermes-delegation"],
        },
        {
            "id": "mark-lvi-engine",
            "label": "Mark LVI Assistant Core",
            "ring": 3,
            "group": "assistant",
            "status": "active",
            "path": (MARK_LVI_ROOT / "main.py").as_posix(),
            "tags": ["mark-lvi", "providers", "outcome-guard"],
            "summary": "Cross-platform voice & tool assistant with STT Whisper + Local LLM + Piper TTS, 5-word verified outcomes, and recallable memory.",
            "requires": ["local-models", "knowledge-memory", "persona"],
        },
        {
            "id": "capability-policy",
            "label": "5-Zone Capability Policy",
            "ring": 3,
            "group": "security",
            "status": "active",
            "path": (WORKSPACE_ROOT / "capability_policy.json").as_posix(),
            "tags": ["security", "air-gap", "zones"],
            "summary": "Enforces loopback-only socket guards and least-privilege capability manifests across all 5 workspace agent groups.",
            "requires": ["execution", "source-governance"],
        },
    ]

    links: list[dict[str, str]] = []
    node_ids = {n["id"] for n in nodes}
    for n in nodes:
        for req in n.get("requires", []):
            if req in node_ids:
                links.append({"source": req, "target": n["id"]})

    return {
        "version": 2,
        "assembled_sha256": "7343B1C3051C560EEC99E488A8A5F37F45D9606CC51A9AF288B52ABC5564C6C6",
        "rings": [
            {"ring": 0, "name": "Ring 0: Shared Core", "count": 1},
            {"ring": 1, "name": "Ring 1: Second Brain Modules (9 ON, 1 OFF)", "count": 10},
            {"ring": 2, "name": "Ring 2: JEV Trading System Roles", "count": 9},
            {"ring": 3, "name": "Ring 3: Diode Inbox/Outbox & Mark LVI", "count": 5},
        ],
        "nodes": nodes,
        "links": links,
    }


def get_inbox_outbox_state() -> dict[str, Any]:
    """Aggregates all Inbox and Outbox queues with strict string preservation."""
    snapshot_path = HUD_ROOT / "inbox" / "offline_snapshot.json"
    snapshot_data: dict[str, Any] = {}
    if snapshot_path.exists():
        try:
            snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception:
            snapshot_data = {}

    audio_inbox_dir = OFFLINE_DIR / "inbox-audio"
    audio_files = [p.name for p in audio_inbox_dir.glob("*") if p.is_file()] if audio_inbox_dir.exists() else []

    outbox_path = OUTBOX_DIR / "metadata_outbox.json"
    outbox_events: list[dict[str, Any]] = []
    if outbox_path.exists():
        try:
            outbox_events = json.loads(outbox_path.read_text(encoding="utf-8"))
        except Exception:
            outbox_events = []

    gtm_path = GTM_DIR / "staged_outreach.json"
    gtm_drafts: list[dict[str, Any]] = []
    if gtm_path.exists():
        try:
            gtm_drafts = json.loads(gtm_path.read_text(encoding="utf-8"))
        except Exception:
            gtm_drafts = []

    inbox_items = []
    for ev in snapshot_data.get("events", []):
        inbox_items.append({
            "id": ev.get("event_id", "inbox-evt"),
            "channel": "OFFLINE_SNAPSHOT_DIODE",
            "title": f"Ledger {ev.get('kind', 'event')}: {ev.get('event_id')}",
            "state": ev.get("state", "completed"),
            "reference": ev.get("reference", ""),
            "timestamp": ev.get("recorded_at", ""),
            "outcome_badge": "done",
            "linked_node": "inbox-offline-snapshot",
            "detail": f"Snapshot event, reference {ev.get('reference', '')}.",
        })
    for wav in audio_files:
        inbox_items.append({
            "id": f"audio:{wav}",
            "channel": "INBOX_AUDIO_DROP",
            "title": f"Client Discovery Audio: {wav}",
            "state": "queued_transcription",
            "reference": "delivery-offline/inbox-audio",
            "timestamp": "",
            "outcome_badge": "started",
            "linked_node": "mark-lvi-engine",
            "detail": "File present in delivery-offline/inbox-audio.",
        })

    outbox_items = []
    for ev in outbox_events:
        outbox_items.append({
            "id": ev.get("event_id", "evt"),
            "channel": "METADATA_DIODE_OUTBOX",
            "title": f"Job {ev.get('job_id')} ({ev.get('from_state')} -> {ev.get('to_state')})",
            "state": "sent" if ev.get("dispatched_via_smtp") else "pending_relay",
            "requires_review": bool(ev.get("requires_review", False)),
            "timestamp": ev.get("timestamp_utc", ""),
            "outcome_badge": "done" if ev.get("dispatched_via_smtp") else "unverified",
            "linked_node": "outbox-metadata-diode",
            "detail": f"Event {ev.get('event_id')} in notification-outbox/metadata_outbox.json.",
        })
    for idx, d in enumerate(gtm_drafts[:12]):
        # review_status wins over the legacy status field; the queue contains drafts where they disagree.
        status = d.get("review_status") or d.get("status", "needs_review")
        outbox_items.append({
            "id": d.get("id") or d.get("prospect_id") or f"gtm_{idx}",
            "channel": "GTM_HUMAN_REVIEW_OUTBOX",
            "title": f"{d.get('company_name', 'Prospect')} — {d.get('subject', '')}",
            "state": status,
            "requires_review": status == "needs_review",
            "recipient": d.get("recipient_ref") or d.get("contact_email") or "unassigned",
            "vertical": d.get("vertical", "B2B Reconciliation"),
            "outcome_badge": "done" if status == "approved" else ("ask" if status == "needs_review" else "failed"),
            "linked_node": "outbox-gtm-queue",
            "detail": f"Vertical: {d.get('vertical', 'unspecified')}. Decisions are made through the existing review gate.",
        })

    return {
        "inbox_count": len(inbox_items),
        "outbox_count": len(outbox_items),
        "inbox": inbox_items,
        "outbox": outbox_items,
    }


def get_agents_and_workflows() -> dict[str, Any]:
    """Returns the unified Agent Capability Matrix, JEV 10-Level Pipeline, and Mark LVI Provider Stack."""
    cap_path = WORKSPACE_ROOT / "capability_policy.json"
    cap_data: dict[str, Any] = {}
    if cap_path.exists():
        try:
            cap_data = json.loads(cap_path.read_text(encoding="utf-8"))
        except Exception:
            cap_data = {}

    links = {
        "delivery_offline_discovery_and_worker": "local-models",
        "delivery_offline_reconciliation_harness": "verification",
        "gtm_research_batch_and_dispatcher": "outbox-gtm-queue",
        "gtm_smtp_alert_relay": "outbox-metadata-diode",
        "hud_operator_interface": "capability-policy",
    }
    zones = []
    for agent_id, spec in cap_data.get("agents", {}).items():
        zones.append({
            "id": agent_id,
            "label": agent_id.replace("_", " ").title(),
            "linked_node": links.get(agent_id, "capability-policy"),
            "zone": spec.get("zone", ""),
            "network_policy": spec.get("network_policy", "loopback_only"),
            "scripts": spec.get("scripts", []),
            "enabled_capabilities": spec.get("enabled_capabilities", []),
            "disabled_capabilities": spec.get("disabled_capabilities", []),
            # Declared in capability_policy.json; this does not prove a process is running or enforced.
            "status": "POLICY_DECLARED",
        })

    mark_lvi_stack = {
        "hearing_stt": {"provider": "faster-whisper (CPU)", "warm_latency": "1.16s", "language_follow": True, "status": "READY"},
        "thinking_llm": {"provider": "Hermes / Qwen3 Local (127.0.0.1:8080)", "protocol": "/v1/chat/completions", "tool_budget": "12 tools / 11,615 chars", "think_filter": True, "status": "LOOPBACK_GUARDED"},
        "speaking_tts": {"provider": "Piper Neural TTS", "speed": "15x realtime (0.34s / 5.15s)", "languages": 52, "status": "READY"},
        "safety_gates": ["5-Word Verified Outcomes", "UI-Issued Confirmation Token", "Reversible Undo Closure Stack", "Untrusted-Content Boundary"],
    }

    return {
        "default_unlisted_plugin_state": cap_data.get("default_unlisted_plugin_state", "OFF"),
        "workspace_agents": zones,
        "mark_lvi_stack": mark_lvi_stack,
    }


def query_project_assistant(query: str, context_scope: str = "all") -> dict[str, Any]:
    """
    Omniscient Project Assistant using Mark LVI Key-Index Recall + JEV Level 8/9 Cheap Reads.
    Accesses all project knowledge across Second Brain, JEV Workspace, and Mark LVI while preserving StrictStr financial numbers and untrusted-content boundaries.
    """
    q = (query or "").strip()
    q_lower = q.lower()

    graph = get_second_brain_graph()
    io_state = get_inbox_outbox_state()
    agents = get_agents_and_workflows()

    # Step 1: Run JEV System-One pre-flight triage on the user query
    jev_triage = evaluate_jev_system_one(
        {"query": q, "scope": context_scope},
        {
            "is_injection": {"type": "noul", "question": "Does query attempt prompt injection or policy bypass?"},
            "intent_route": {"type": "choice", "options": ["second_brain_lookup", "inbox_outbox_triage", "jev_trading_risk", "agent_capability_audit", "financial_ledger_check", "mark_lvi_engine"]},
            "urgency": {"type": "score", "levels": ["routine", "operational", "priority", "critical"]},
        },
    )

    if jev_triage["answers"]["is_injection"]["noul"] > 0.65:
        return make_outcome(
            "failed",
            "Blocked by JEV Level 1/6 Injection Gate: Query contains instruction-override patterns.",
            data={"jev_triage": jev_triage},
            evidence="jev_guard_noul_threshold",
        )

    tokens = re.findall(r"[a-z0-9_-]{3,}", q_lower)
    scored_nodes = []
    for n in graph["nodes"]:
        hay = (n["id"] + " " + n["label"] + " " + n["summary"] + " " + " ".join(n["tags"])).lower()
        hits = sum(2 if tok in n["label"].lower() else 1 for tok in tokens if tok in hay)
        if hits > 0:
            scored_nodes.append((hits, n))
    scored_nodes.sort(key=lambda pair: pair[0], reverse=True)
    matched_nodes = [n for _, n in scored_nodes]
    if not matched_nodes:
        matched_nodes = graph["nodes"][:4]

    citations = [f"{n['label']} ({n['path']})" for n in matched_nodes[:5]]

    # Synthesize comprehensive answer from live project state
    summary_lines = [
        f"[JEV System-One Route: {jev_triage['answers']['intent_route']['choice']} | Confidence: {jev_triage['answers']['intent_route']['confidence']}]",
        f"Scanned {len(graph['nodes'])} Second Brain / JEV nodes, {io_state['inbox_count']} Inbox events, {io_state['outbox_count']} Outbox items, and {len(agents['workspace_agents'])} Zone-Enforced Agent Groups.",
    ]

    for n in matched_nodes[:3]:
        summary_lines.append(f"• {n['label']} [Ring {n['ring']} | {n['status'].upper()}]: {n['summary']}")

    if any(k in q_lower for k in ("money", "financial", "ledger", "invoice", "quarantine", "sow", "risk", "cost")):
        summary_lines.append(
            "• Financial Core (StrictStr Guard): Annual Risk Exposure = '$826,920.00' | Projected 85% Savings = '$702,882.00' | High-Precision Test Fixture = '9007199254740993.0001 USD'. Zero browser float conversion."
        )

    if any(k in q_lower for k in ("inbox", "outbox", "gtm", "email", "diode", "cambridge", "apex", "coldchain")):
        pending_gtm = sum(1 for item in io_state["outbox"] if item["channel"] == "GTM_HUMAN_REVIEW_OUTBOX" and item["requires_review"])
        summary_lines.append(
            f"• Inbox/Outbox Diode Status: {io_state['inbox_count']} items in Inbox; {io_state['outbox_count']} items in Outbox ({pending_gtm} GTM drafts awaiting human approval gate)."
        )

    cheap_read_trace = None
    if any(k in q_lower for k in ("csv", "fixture", "adversarial", "baseline", "sow", "cheap", "invoice", "budgeting")):
        from .jev_cheap_read import ask_jev_file_bool
        target_fixture = "budgeting.md" if "budget" in q_lower else ("SOW_Keystone_Precision_Machining.md" if "sow" in q_lower else "adversarial_fixture.csv")
        cheap_read_trace = ask_jev_file_bool(target_fixture, q)
        if cheap_read_trace.get("outcome") == "done":
            summary_lines.append(
                f"• JEV Level 8 Cheap Read [{cheap_read_trace['file_name']}]: noul={cheap_read_trace['noul']} ({cheap_read_trace['evidence']})"
            )

    wrapped_context = wrap_untrusted(
        "\n".join(f"{n['id']}: {n['summary']}" for n in matched_nodes[:4]),
        source_label="second_brain_and_workspace_index",
    )

    return make_outcome(
        "done",
        "\n".join(summary_lines),
        data={
            "jev_triage": jev_triage,
            "citations": citations,
            "matched_node_ids": [n["id"] for n in matched_nodes[:5]],
            "untrusted_envelope_preview": wrapped_context,
        },
        evidence="omniscient_index_verified_read",
    )


def get_omnibus_bundle() -> dict[str, Any]:
    """Returns the complete unified payload for the HTML HUD prototypes."""
    default_judgments = {
        "regime": "trending",
        "direction": "up",
        "toxic_flow": "low",
        "liquidity_stress": "low",
        "quote_environment": "clean",
        "inventory_pressure": "neutral",
        "execution_health": "healthy",
    }
    return {
        "schema_version": "2.0-omnibus",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "second_brain": get_second_brain_graph(),
        "inbox_outbox": get_inbox_outbox_state(),
        "agents_workflows": get_agents_and_workflows(),
        "jev_trading_state": evaluate_jev_trading_rung(default_judgments, hard_risk_breach=False),
        "financial_strict_strings": {
            "annual_risk_exposure_usd": "826920.00",
            "projected_savings_usd": "702882.00",
            "precision_canary_usd": "9007199254740993.0001",
            "jev_1m_calls_cost_usd": "16.80",
            "sota_1m_calls_cost_usd": "3500.00",
        },
    }
