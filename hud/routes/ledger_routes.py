"""
hud/routes/ledger_routes.py
Domain route module for Job Ledger, SQLite data contracts, GTM queue, alerts, SSTM memory, and JEV pipelines.
"""

from __future__ import annotations
import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse
from data_contracts import SQLiteLedgerPayload


def register_ledger_routes(router: TypeSafeRouter, provider: Any):
    # 1. Offline Ledger & Invariants
    def handle_offline_ledger(**kwargs):
        return provider.get_offline_ledger_and_invariant()

    router.register("/api/offline-ledger", "GET", handle_offline_ledger, service="job-ledger")

    def handle_offline_ledger_cycle(**kwargs):
        import job_ledger
        ledger = job_ledger.get_default_ledger()
        jid = f"job-hud-{int(datetime.now(timezone.utc).timestamp())}"
        ledger.queue_job(jid, "hud-operator-scope", "reconciliation")
        claimed = ledger.claim_job()
        if claimed:
            ledger.update_job_state(claimed, "validated")
            ledger.update_job_state(claimed, "approved")
            ledger.update_job_state(claimed, "completed")
        return {"job_id": jid, "claimed": claimed, "final_state": "completed"}

    router.register("/api/offline-ledger/cycle", "POST", handle_offline_ledger_cycle, service="job-ledger")

    # 2. SQLite Ledger Data Contract
    def handle_sqlite_ledger(trace_id: Optional[str] = None, **kwargs):
        return provider.get_sqlite_ledger_data(trace_id=trace_id)

    router.register("/api/sqlite/ledger", "GET", handle_sqlite_ledger,
                    response_model=SQLiteLedgerPayload, service="sqlite-ledger")

    # 3. GTM Queue
    def handle_gtm_queue(**kwargs):
        return provider.get_gtm_queue()

    router.register("/api/gtm-queue", "GET", handle_gtm_queue, service="gtm-research")

    def handle_gtm_review(body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        stage_path = os.path.join(provider.GTM_DIR, "staged_outreach.json")
        idx = int(payload.get("index", -1))
        new_status = payload.get("status", "needs_review")
        if new_status in {"needs_review", "approved", "rejected"} and os.path.exists(stage_path):
            with open(stage_path, "r", encoding="utf-8") as f:
                drafts = json.load(f)
            if 0 <= idx < len(drafts):
                drafts[idx]["status"] = new_status
                with open(stage_path, "w", encoding="utf-8") as f:
                    json.dump(drafts, f, indent=2)
        return {"updated": True}

    router.register("/api/gtm-queue/review", "POST", handle_gtm_review, service="gtm-research")

    # 4. Alerts
    def handle_alerts_get(**kwargs):
        return provider.get_alerts_status()

    router.register("/api/alerts", "GET", handle_alerts_get, service="alerts-engine")

    def handle_alerts_dispatch(**kwargs):
        from smtp_alert_relay import dispatch_pending_alerts
        return dispatch_pending_alerts()

    router.register("/api/alerts/dispatch", "POST", handle_alerts_dispatch, service="alerts-engine")

    # 5. Omnibus & Session
    def handle_omnibus(**kwargs):
        from hud.omnibus import get_omnibus_bundle
        return get_omnibus_bundle()

    router.register("/api/omnibus", "GET", handle_omnibus, service="omnibus-bundle")

    def handle_session(**kwargs):
        return {"token": "local-session-token", "authenticated": True}

    router.register("/api/session", "GET", handle_session, service="session-auth")

    # 6. Multi-Agent Shared Short-Term Memory (SSTM)
    def handle_memory_state(**kwargs):
        from hud.shared_memory import get_shared_memory_store
        return get_shared_memory_store().get_state_summary()

    router.register("/api/memory/state", "GET", handle_memory_state, service="sstm-memory")

    def handle_memory_tasks(**kwargs):
        from hud.shared_memory import get_shared_memory_store
        return {"status": "ok", "tasks": get_shared_memory_store().get_completed_tasks()}

    router.register("/api/memory/tasks", "GET", handle_memory_tasks, service="sstm-memory", is_prefix=True)

    def handle_memory_blackboard_get(query: Optional[Dict[str, list]] = None, **kwargs):
        from hud.shared_memory import get_shared_memory_store
        store = get_shared_memory_store()
        key = ((query or {}).get("key") or [""])[0]
        if key:
            return {"key": key, "value": store.get_blackboard_key(key)}
        return {"status": "ok", "entries": store.get_all_blackboard_entries()}

    router.register("/api/memory/blackboard", "GET", handle_memory_blackboard_get, service="sstm-memory")

    def handle_memory_blackboard_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.shared_memory import get_shared_memory_store
        payload = body or {}
        store = get_shared_memory_store()
        entry = store.set_blackboard_key(
            key=str(payload.get("key", "")),
            value=payload.get("value"),
            writer_agent_id=str(payload.get("writer_agent_id", "operator")),
            ttl_seconds=float(payload["ttl_seconds"]) if payload.get("ttl_seconds") is not None else None
        )
        provider.notify_telemetry_event()
        return {"status": "set", "entry": entry.to_dict()}

    router.register("/api/memory/blackboard", "POST", handle_memory_blackboard_post, service="sstm-memory")

    def handle_memory_obsidian_status(**kwargs):
        from hud.shared_memory import get_shared_memory_store, PRIMARY_VAULT_DIR, LOCAL_VAULT_DIR
        store = get_shared_memory_store()
        return {
            "status": store._vault_sync_status,
            "last_vault_sync_utc": store._last_vault_sync_utc,
            "primary_vault_dir": str(PRIMARY_VAULT_DIR),
            "primary_vault_exists": PRIMARY_VAULT_DIR.exists(),
            "local_vault_dir": str(LOCAL_VAULT_DIR),
            "local_vault_exists": LOCAL_VAULT_DIR.exists()
        }

    router.register("/api/memory/obsidian-status", "GET", handle_memory_obsidian_status, service="sstm-memory")

    def handle_memory_task_complete(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.shared_memory import get_shared_memory_store
        payload = body or {}
        store = get_shared_memory_store()
        rec = store.record_task_completion(
            agent_id=str(payload.get("agent_id", "sub-agent")),
            task_id=str(payload.get("task_id", f"task-sstm-{int(time.time()*1000)}")),
            task_type=str(payload.get("task_type", "general")),
            status=str(payload.get("status", "completed")),
            input_summary=payload.get("input_summary", {}),
            output_summary=payload.get("output_summary", {}),
            artifacts=payload.get("artifacts", []),
            duration_ms=float(payload.get("duration_ms", 0.0)),
            sync_vault_now=bool(payload.get("sync_vault_now", True))
        )
        provider.notify_telemetry_event()
        return {"status": "recorded", "task": rec.to_dict()}

    router.register("/api/memory/task/complete", "POST", handle_memory_task_complete, service="sstm-memory")

    def handle_memory_agent_heartbeat(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.shared_memory import get_shared_memory_store
        payload = body or {}
        store = get_shared_memory_store()
        ag = store.update_agent_heartbeat(
            agent_id=str(payload.get("agent_id", "sub-agent")),
            role=payload.get("role"),
            operational_state=str(payload.get("operational_state", "idle")),
            current_task_id=payload.get("current_task_id"),
            capabilities=payload.get("capabilities"),
            meta=payload.get("meta")
        )
        provider.notify_telemetry_event()
        return {"status": "updated", "agent": ag.to_dict()}

    router.register("/api/memory/agent/heartbeat", "POST", handle_memory_agent_heartbeat, service="sstm-memory")

    def handle_memory_sync_obsidian(**kwargs):
        from hud.shared_memory import get_shared_memory_store
        store = get_shared_memory_store()
        res = store.sync_to_obsidian_vault()
        provider.notify_telemetry_event()
        return res

    router.register("/api/memory/sync-obsidian", "POST", handle_memory_sync_obsidian, service="sstm-memory")

    # 7. JEV pipelines, guardrails, cheap read, and composite gates
    def handle_guardrail_events(**kwargs):
        from hud.jev_guard import GUARDRAIL_LOG
        if os.path.exists(GUARDRAIL_LOG):
            try:
                with open(GUARDRAIL_LOG, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    router.register("/api/guardrail/events", "GET", handle_guardrail_events, service="jev-guardrail")

    def handle_guardrail_bash(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_guard import check_bash_command
        cmd = str((body or {}).get("command", ""))
        verdict = check_bash_command(cmd)
        return {
            "allowed": verdict.allowed,
            "command": verdict.command,
            "risk_score": verdict.risk_score,
            "reason": verdict.reason,
            "irreversible": verdict.irreversible,
            "notice": verdict.notice,
        }

    router.register("/api/guardrail/bash", "POST", handle_guardrail_bash, service="jev-guardrail")

    def handle_cheap_read_fixtures(**kwargs):
        from hud.jev_cheap_read import list_cheap_read_fixtures
        return list_cheap_read_fixtures()

    router.register("/api/jev-cheap-read/fixtures", "GET", handle_cheap_read_fixtures, service="cheap-read")

    def handle_cheap_read_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_cheap_read import ask_jev_file_bool, ask_jev_file_choice, ask_jev_file_score
        payload = body or {}
        mode = str(payload.get("mode", "bool")).strip().lower()
        path = str(payload.get("path", ""))
        question = str(payload.get("question", ""))
        if mode == "bool":
            return ask_jev_file_bool(path, question, str(payload.get("yes_criteria", "")), str(payload.get("no_criteria", "")))
        elif mode == "choice":
            opts = payload.get("options", [])
            return ask_jev_file_choice(path, question, [str(x) for x in opts] if isinstance(opts, list) else [])
        elif mode == "score":
            lvs = payload.get("levels", ["low", "moderate", "high", "strict"])
            return ask_jev_file_score(path, question, [str(x) for x in lvs] if isinstance(lvs, list) else ["low", "high"])
        return HTTPResponse(status_code=400, payload={"error": "Unsupported cheap-read mode"})

    router.register("/api/jev-cheap-read", "POST", handle_cheap_read_post, service="cheap-read")

    def handle_agentic_events(**kwargs):
        from hud.jev_agentic import AGENTIC_JEV_LOG
        if os.path.exists(AGENTIC_JEV_LOG):
            try:
                with open(AGENTIC_JEV_LOG, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    router.register("/api/jev-agentic/events", "GET", handle_agentic_events, service="agentic-jev")

    def handle_agentic_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_agentic import ask_jev, triage_failure, judge_diff, gate_plan
        payload = body or {}
        mode = str(payload.get("mode", "default")).strip().lower()
        state = payload.get("state")
        paths = payload.get("paths")
        command = payload.get("command")
        questions = payload.get("questions")
        if mode == "triage":
            return triage_failure(state or "execution_failure", command=command, candidate_paths=paths)
        elif mode == "judge_diff":
            return judge_diff(str(state or ""), target_files=paths)
        elif mode == "gate_plan":
            return gate_plan(str(state or ""), target_paths=paths)
        return ask_jev(state=state, paths=paths, command=command, questions=questions)

    router.register("/api/jev-agentic", "POST", handle_agentic_post, service="agentic-jev")

    def handle_composite_presets(**kwargs):
        from hud.jev_composite_gate import GTM_OUTREACH_WEIGHTS, CODE_REVIEW_WEIGHTS, IDEA_VERDICT_WEIGHTS
        return {
            "weights": {
                "gtm_outreach": GTM_OUTREACH_WEIGHTS,
                "code_review": CODE_REVIEW_WEIGHTS,
                "idea_verdict": IDEA_VERDICT_WEIGHTS,
            },
            "confidence_thresholds": {"floor": 0.50, "ceiling": 0.90},
        }

    router.register("/api/jev-composite-gate/presets", "GET", handle_composite_presets, service="composite-gate")

    def handle_composite_score(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_composite_gate import evaluate_composite_score
        payload = body or {}
        return evaluate_composite_score(
            target_kind=str(payload.get("target_kind", "gtm_outreach")),
            target_data=payload.get("target_data"),
            weights_override=payload.get("weights"),
        )

    router.register("/api/jev-composite-score", "POST", handle_composite_score, service="composite-gate")

    def handle_confidence_gate(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_composite_gate import evaluate_confidence_gate
        payload = body or {}
        return evaluate_confidence_gate(
            action_type=str(payload.get("action_type", "bash_gate")),
            command_or_target=str(payload.get("target") or payload.get("command") or "ls -la"),
            context=payload.get("context"),
        )

    router.register("/api/jev-confidence-gate", "POST", handle_confidence_gate, service="composite-gate")

    def handle_multi_file_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_multi_file import ask_jev_files, pick_first_file, scout_and_pick
        payload = body or {}
        mode = str(payload.get("mode", "scout")).strip().lower()
        targets = payload.get("targets", "second-brain")
        question = str(payload.get("question", ""))
        if mode == "ask_files":
            return ask_jev_files(targets, payload.get("questions") or question)
        elif mode == "pick_first":
            cands = targets if isinstance(targets, list) else [t.strip() for t in str(targets).split(",") if t.strip()]
            return pick_first_file([str(x) for x in cands], question)
        elif mode == "scout":
            return scout_and_pick(targets, question)
        return HTTPResponse(status_code=400, payload={"error": "Unsupported multi-file mode"})

    router.register("/api/jev-multi-file", "POST", handle_multi_file_post, service="multi-file")

    def handle_e2e_events(**kwargs):
        from hud.jev_e2e_pipeline import get_recent_e2e_events
        return get_recent_e2e_events()

    router.register("/api/jev-e2e/events", "GET", handle_e2e_events, service="e2e-pipeline")

    def handle_e2e_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.jev_e2e_pipeline import run_e2e_invoice_to_gtm_pipeline
        payload = body or {}
        return run_e2e_invoice_to_gtm_pipeline(
            invoice_fixture=str(payload.get("invoice_fixture", "adversarial_fixture.csv")),
            stage_to_outbox=bool(payload.get("stage_to_outbox", True)),
        )

    router.register("/api/jev-e2e", "POST", handle_e2e_post, service="e2e-pipeline")

    def handle_assistant(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.omnibus import query_project_assistant
        payload = body or {}
        return query_project_assistant(str(payload.get("query", "")), str(payload.get("scope", "all")))

    router.register("/api/assistant", "POST", handle_assistant, service="project-assistant")

    def handle_jev_decide(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.omnibus import evaluate_jev_system_one
        payload = body or {}
        return evaluate_jev_system_one(payload.get("state", {}), payload.get("questions", {}))

    router.register("/api/jev-decide", "POST", handle_jev_decide, service="system-one")

    def handle_jev_rung(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.omnibus import evaluate_jev_trading_rung
        payload = body or {}
        return evaluate_jev_trading_rung(payload.get("judgments", {}), bool(payload.get("hard_risk_breach", False)))

    router.register("/api/jev-rung", "POST", handle_jev_rung, service="trading-rung")
