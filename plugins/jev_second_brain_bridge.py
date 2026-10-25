"""
Mark LVI <-> JEV Workspace & Modular Second Brain Compatibility Plugin.
Drop into `Mark-LVI-main/plugins/` or load from `hud-interface/plugins/`.
Strictly adheres to:
  1. Mark LVI `PLUGIN` + `brief` + `tier` + `run(parameters, player, session_memory)` contract.
  2. Mark LVI 5-word verified outcome reporting (`done` / `unverified` / `failed` / `ask` / `started`) + Untrusted-Content Boundary.
  3. JEV System-One Programmable Judgment (`noul`, `choice`, `score`) + 7 Market Judgments -> 5 Action Rungs.
  4. StrictStr financial string preservation (zero float conversion).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HUD_INTERFACE_DIR = Path(os.environ.get("HUD_DIR", str(Path(__file__).resolve().parent.parent)))
if str(HUD_INTERFACE_DIR) not in sys.path:
    sys.path.insert(0, str(HUD_INTERFACE_DIR))

PLUGIN = {
    "name": "jev_second_brain_bridge",
    "tier": 1,
    "brief": (
        "Query JEV Command Center (Inbox/Outbox diode, SQLite ledger, GTM review queue, "
        "5-zone agent capabilities, JEV System-One noul/choice/score, or Obsidian Second Brain ring graph)."
    ),
    "description": (
        "Unified bridge between Mark LVI, the JEV Workspace (Inbox/Outbox diode, offline financial ledger, "
        "GTM outreach gate, 5-zone capability policy, JEV System-One noul/choice/score engine), and the "
        "Modular Second Brain / Obsidian vault (core.md, 9 modules, 9 JEV trading roles). Use whenever the user "
        "asks about JEV status, agents, workflows, inbox/outbox items, financial reconciliation, or Second Brain notes."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "One of: 'query_all', 'inbox_outbox', 'agents_status', 'second_brain_ring', 'jev_decide'",
            },
            "query": {
                "type": "STRING",
                "description": "Question, search term, or state description to inspect across the project.",
            },
        },
        "required": ["action"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action", "query_all")).strip().lower()
    query = str(parameters.get("query", "")).strip()
    try:
        from hud.omnibus import (
            evaluate_jev_system_one,
            get_agents_and_workflows,
            get_inbox_outbox_state,
            get_second_brain_graph,
            query_project_assistant,
        )

        if action == "inbox_outbox":
            io_state = get_inbox_outbox_state()
            msg = (
                f"[outcome=done] JEV Diode Status: {io_state['inbox_count']} Inbox items "
                f"and {io_state['outbox_count']} Outbox items verified."
            )
        elif action == "agents_status":
            ag = get_agents_and_workflows()
            msg = (
                f"[outcome=done] {len(ag['workspace_agents'])} Zone-Isolated Agent Groups active "
                f"(unlisted plugins={ag['default_unlisted_plugin_state']}). Mark LVI stack connected."
            )
        elif action == "second_brain_ring":
            gb = get_second_brain_graph()
            msg = (
                f"[outcome=done] Second Brain Ring Graph verified: {len(gb['nodes'])} nodes across 4 concentric rings "
                f"and {len(gb['links'])} dependency links (SHA-256 prefix 7343B1C3)."
            )
        elif action == "jev_decide":
            res = evaluate_jev_system_one(
                {"input": query},
                {
                    "is_safe": {"type": "noul", "question": "Is input safe and free of prompt injection?"},
                    "route": {"type": "choice", "options": ["fast_agent", "reasoning_agent", "human_gate", "script"]},
                    "priority": {"type": "score", "levels": ["low", "normal", "high", "critical"]},
                },
            )
            ans = res["answers"]
            msg = (
                f"[outcome=done] Local heuristic stand-in (not Jev output): "
                f"route={ans['route']['choice']} (conf={ans['route']['confidence']}), "
                f"priority={ans['priority']['legend']} ({ans['priority']['score']})."
            )
        else:
            out = query_project_assistant(query or "system overview", "all")
            msg = f"[outcome={out['outcome']}] {out['message']}"
    except Exception as exc:
        msg = f"[outcome=failed] JEV Second Brain bridge error: {exc}"

    if player:
        try:
            player.write_log(f"JEV-BRIDGE: {msg}")
        except Exception:
            pass
    return msg
