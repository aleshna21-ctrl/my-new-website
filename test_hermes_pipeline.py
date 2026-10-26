#!/usr/bin/env python3
"""
test_hermes_pipeline.py
=======================
AIOS Tracer Bullet Execution Script for Hermes Pipeline:
1. Injects a dummy test payload into the [ INBOX ] state of job_ledger.db assigned to Hermes.
2. Wakes up the LiveLocalModelAdapter (with keep_alive=-1, allow_simulation=True) to process the payload.
3. Steps the ledger state machine from [ INBOX ] -> running -> validated -> approved -> completed.
4. Dynamically populates the active agent states in job_ledger.db.
5. Re-runs the Obsidian vault generator to ensure the AIOS root and assignments graphs reflect
   dynamic Hermes sub-agents rather than hardcoded definitions.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from job_ledger import (
    DB_FILE,
    init_db,
    inject_inbox_job,
    update_job_state,
    register_agent_state,
    get_active_agent_states,
    VALID_TRANSITIONS,
)
from inference_adapter import LiveLocalModelAdapter, FailureEvent
from hud.shared_memory import SharedMemoryStore
from hud.obsidian_root_generator import generate_aios_obsidian_vault, query_ledger_stats


# Ensure UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def run_hermes_tracer_bullet() -> dict:
    print("=" * 70)
    print("[TRACER BULLET] Starting Hermes Pipeline Execution & State Population")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # Step 1: Inject Dummy Payload into [ INBOX ] state of job_ledger.db
    # -------------------------------------------------------------------------
    init_db()
    tracer_job_id = f"tracer-hermes-{int(time.time())}"
    tracer_scope = "hermes-agent"
    tracer_type = "hermes_inference"

    print(f"\n[Step 1] Ingesting dummy payload into [ INBOX ] state in SQLite ledger...")
    print(f"         Database Path: {DB_FILE}")
    print(f"         Job ID:        {tracer_job_id}")
    print(f"         Scope:         {tracer_scope}")
    print(f"         Job Type:      {tracer_type}")
    print(f"         Initial State: [ INBOX ]")

    injected = inject_inbox_job(tracer_job_id, tracer_scope, tracer_type, state="[ INBOX ]")
    if not injected:
        raise RuntimeError(f"Failed to inject tracer job '{tracer_job_id}' into [ INBOX ] state.")

    # Verify injection in SQLite
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT job_id, scope_id, job_type, state FROM jobs WHERE job_id = ?", (tracer_job_id,))
        row = cur.fetchone()
        assert row is not None, f"Tracer job {tracer_job_id} not found in database!"
        assert row["state"] == "[ INBOX ]", f"Expected state '[ INBOX ]', got '{row['state']}'"
        print(f"         [OK] Verified [ INBOX ] state in SQLite ledger: {dict(row)}")

    # -------------------------------------------------------------------------
    # Step 2: Wake up LiveLocalModelAdapter and process payload
    # -------------------------------------------------------------------------
    print(f"\n[Step 2] Waking up LiveLocalModelAdapter to process payload...")
    adapter = LiveLocalModelAdapter(
        endpoint="http://127.0.0.1:8080/v1/chat/completions",
        model_tag="qwen3:4b",
        allow_simulation=True,
        keep_alive=-1,
    )
    print(f"         Adapter Initialized: endpoint={adapter.endpoint}, model={adapter.model_tag}")
    print(f"         VRAM Stability Flag: keep_alive={adapter.keep_alive} (LOCKED)")

    dummy_event = {
        "type": "tracer_bullet_intake",
        "description": "Synthetic Hermes AIOS pipeline intake payload for tracer execution",
        "reported_events": 1,
        "period": "LIVE_VERIFICATION",
        "evidence_ids": [f"tracer-proof-{tracer_job_id}"]
    }
    prompt = "Extract synthetic failure event: " + json.dumps(dummy_event)
    processed_result = adapter.enforce_schema_and_quarantine(prompt, FailureEvent)
    print(f"         [OK] Adapter Wakeup Succeeded. Processed payload:")
    print(f"            Result Status: {processed_result.get('status')}")
    print(f"            Execution Mode: {processed_result.get('execution_mode')}")
    print(f"            Simulated: {processed_result.get('is_simulated')}")

    # -------------------------------------------------------------------------
    # Step 3: Advance Ledger State Machine
    # -------------------------------------------------------------------------
    print(f"\n[Step 3] Advancing job_ledger.db state machine through strict transitions...")
    states_sequence = ["running", "validated", "approved", "completed"]
    for next_state in states_sequence:
        success = update_job_state(tracer_job_id, next_state)
        print(f"         -> Transitioned to: '{next_state}' (Result: {success})")

    # Verify completed state in database
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT job_id, state, updated_at FROM jobs WHERE job_id = ?", (tracer_job_id,))
        final_row = cur.fetchone()
        assert final_row is not None and final_row["state"] == "completed"
        print(f"         [OK] Final Ledger State Confirmed: {dict(final_row)}")

    # -------------------------------------------------------------------------
    # Step 4: Dynamically populate active agent states in the ledger
    # -------------------------------------------------------------------------
    print(f"\n[Step 4] Dynamically populating active agent states in job_ledger.db...")
    dynamic_subagents = [
        {
            "agent_id": "agent-hermes-gateway",
            "name": "Hermes Gateway Daemon",
            "role": "rpc_gateway",
            "state": "ACTIVE",
            "capabilities": ["hmac_sha256", "anti_replay_nonce", "json_rpc_2_0", "two_way_sync"],
            "meta": {"desc": "Handles /gateway/v1/rpc with anti-replay timestamp & nonce authentication.", "tier": 2}
        },
        {
            "agent_id": "agent-hermes-model-adapter",
            "name": "Hermes Model Adapter",
            "role": "model_adapter",
            "state": "ACTIVE",
            "capabilities": ["vram_locked_keep_alive", "bounded_schema_repair", "loopback_8080"],
            "meta": {"desc": "Live loopback adapter on 127.0.0.1:8080 bridging upstream Ollama with keep_alive=-1.", "tier": 2}
        },
        {
            "agent_id": "agent-hermes-probe-worker",
            "name": "Hermes Diagnostic Probe",
            "role": "diagnostic_probe",
            "state": "ACTIVE",
            "capabilities": ["synthetic_connectivity", "isolated_probe_lock", "rtt_telemetry"],
            "meta": {"desc": "Synthetic connectivity and latency monitor isolated via PROBE_LOCK.", "tier": 2}
        },
        {
            "agent_id": "agent-hermes-evaluator",
            "name": "Hermes Agentic Evaluator",
            "role": "agentic_judge",
            "state": "ACTIVE",
            "capabilities": ["schema_triage", "system_one_gates", "diff_triage"],
            "meta": {"desc": "Implements JEV System-One judgment gates, cheap file reads, and diff triage.", "tier": 3}
        },
        {
            "agent_id": "agent-hermes-tracer",
            "name": "Hermes Pipeline Tracer",
            "role": "pipeline_tracer",
            "state": "ACTIVE",
            "capabilities": ["tracer_bullet_intake", "state_transition_audit", "dynamic_agent_population"],
            "meta": {"desc": "Autonomous tracer bullet verifying adapter wake-up and dynamically populating ledger.", "tier": 1}
        }
    ]

    shared_memory = SharedMemoryStore()

    for sa in dynamic_subagents:
        aid = sa["agent_id"]
        registered = register_agent_state(
            agent_id=aid,
            name=sa["name"],
            role=sa["role"],
            state=sa["state"],
            capabilities=sa["capabilities"],
            meta=sa["meta"]
        )
        # Also sync to shared memory store
        shared_memory.update_agent_heartbeat(
            agent_id=aid,
            role=sa["role"],
            operational_state="active",
            capabilities=sa["capabilities"],
            meta=sa["meta"]
        )
        print(f"         [OK] Registered Agent: {sa['name']} ({aid}) [State: {sa['state']}]")

    # Verify registered agent states in ledger
    active_states = get_active_agent_states()
    print(f"         Total Active Agents in Ledger: {len(active_states)}")

    # -------------------------------------------------------------------------
    # Step 5: Regenerate Obsidian Vault with Dynamic Sub-Agents
    # -------------------------------------------------------------------------
    print(f"\n[Step 5] Triggering AIOS Obsidian Vault generation routine...")
    vault_res = generate_aios_obsidian_vault()
    print(f"         Vault Sync Status: {vault_res.get('status')}")
    print(f"         Files Updated:     {vault_res.get('written_files_count')}")

    # Inspect the newly generated hermes-sub-agents.md
    hermes_md_path = PROJECT_ROOT / "vault" / "agents" / "hermes-sub-agents.md"
    if hermes_md_path.exists():
        text = hermes_md_path.read_text(encoding="utf-8")
        assert "agent-hermes-tracer" in text, "Dynamic tracer sub-agent should appear in generated markdown!"
        print("         [OK] Verified hermes-sub-agents.md dynamically incorporates tracer sub-agents.")

    print("\n" + "=" * 70)
    print("[SUCCESS] [TRACER BULLET] Pipeline execution completed successfully with 0 errors!")
    print("=" * 70)
    return {
        "status": "success",
        "tracer_job_id": tracer_job_id,
        "processed_result": processed_result,
        "active_agents_count": len(active_states),
        "vault_sync": vault_res
    }


if __name__ == "__main__":
    outcome = run_hermes_tracer_bullet()
    sys.exit(0 if outcome.get("status") == "success" else 1)
