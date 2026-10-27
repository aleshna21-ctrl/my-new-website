"""
hud/routes/gateway_routes.py
Domain route module for AIOS Gateway, authenticated Hermes RPC webhooks, cron registry, and task execution.
"""

from __future__ import annotations
import time
from typing import Dict, Any, Optional

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse
from hud.gateway import (
    verify_gateway_request, GatewayAuthError,
    execute_gateway_rpc, execute_task_command,
    load_cron_registry, update_cron_job, trigger_cron_job, delete_cron_job,
    send_signed_rpc, GLOBAL_SYNC_TRACKER, GLOBAL_FEEDBACK_LOOP
)
from data_contracts import GatewayRPCRequest, GatewayRPCResponse


def register_gateway_routes(router: TypeSafeRouter, provider: Any):
    # 1. Gateway Status
    def handle_status(**kwargs):
        return provider.get_gateway_status()

    router.register("/api/gateway/status", "GET", handle_status, service="aios-gateway")

    # 2. Gateway Sync & Feedback
    def handle_feedback(**kwargs):
        return {
            "status": "ok",
            "sequence_id": GLOBAL_SYNC_TRACKER.current_seq(),
            "feedback": GLOBAL_FEEDBACK_LOOP.get_metrics(),
            "history": GLOBAL_SYNC_TRACKER.get_history(limit=25),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

    router.register("/api/gateway/feedback", "GET", handle_feedback, service="aios-gateway")
    router.register("/api/gateway/sync", "GET", handle_feedback, service="aios-gateway")

    # 3. Cron Registry (GET)
    def handle_crons_get(**kwargs):
        return {"status": "ok", "crons": load_cron_registry()}

    router.register("/api/gateway/crons", "GET", handle_crons_get, service="aios-gateway")

    # 4. Task History (GET)
    def handle_tasks_get(**kwargs):
        from hud.gateway import load_task_history
        return {"status": "ok", "tasks": load_task_history()}

    router.register("/api/gateway/tasks", "GET", handle_tasks_get, service="aios-gateway")

    # 5. Hermes Telemetry (GET)
    def handle_hermes_telemetry(**kwargs):
        return provider.get_hermes_telemetry()

    router.register("/api/hermes", "GET", handle_hermes_telemetry, service="hermes-adapter")

    # 6. Gateway RPC (POST)
    def handle_gateway_rpc_endpoint(request_data: GatewayRPCRequest, **kwargs):
        start_t = time.monotonic()
        res = execute_gateway_rpc(request_data.method, request_data.params)
        rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
        provider.notify_telemetry_event()
        return GatewayRPCResponse(
            jsonrpc="2.0",
            id=request_data.id,
            result=res.get("result"),
            error=res.get("error"),
            status="error" if res.get("error") else "ok",
            ack=res.get("ack"),
            round_trip_ms=rtt_ms
        )

    router.register("/api/gateway/rpc", "POST", handle_gateway_rpc_endpoint,
                    request_model=GatewayRPCRequest, response_model=GatewayRPCResponse,
                    service="aios-gateway")

    # 7. Authenticated Hermes Webhook (POST)
    def handle_hermes_webhook(request: HTTPRequest, body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        start_t = time.monotonic()
        idemp_key = request.headers.get("X-Idempotency-Key") or payload.get("idempotency_key")
        if idemp_key and "idempotency_key" not in payload:
            payload["idempotency_key"] = idemp_key

        try:
            raw = request.raw_body or b"{}"
            verify_gateway_request(request.headers, "POST", request.path, raw)
        except GatewayAuthError as gae:
            return HTTPResponse(
                status_code=401,
                payload={
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": f"Unauthorized: {gae}"},
                    "status": "unauthorized"
                }
            )

        method = payload.get("method", "")
        params = payload.get("params", {})
        req_id = payload.get("id")
        if idemp_key and "idempotency_key" not in params:
            params["idempotency_key"] = idemp_key

        rpc_res = execute_gateway_rpc(method, params)
        provider.notify_telemetry_event()
        rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
        ack = rpc_res.get("ack")
        out = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": rpc_res.get("result"),
            "error": rpc_res.get("error"),
            "status": "error" if rpc_res.get("error") else "ok",
            "ack": ack,
            "round_trip_ms": rtt_ms
        }
        status_code = 400 if rpc_res.get("error") else 200
        headers = {}
        if ack and ack.get("ack_id"):
            headers["X-Gateway-Ack-ID"] = str(ack["ack_id"])
        if ack and ack.get("sequence_id") is not None:
            headers["X-Gateway-Sequence-ID"] = str(ack["sequence_id"])
        headers["X-Gateway-RTT-MS"] = str(rtt_ms)
        return HTTPResponse(status_code=status_code, headers=headers, payload=out)

    router.register("/api/gateway/hermes", "POST", handle_hermes_webhook, service="aios-gateway")

    # 8. Gateway Tasks (POST)
    def handle_gateway_tasks_post(request: HTTPRequest, body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        start_t = time.monotonic()
        idemp_key = request.headers.get("X-Idempotency-Key") or payload.get("idempotency_key")
        cmd = payload.get("command") or payload.get("cmd", "ping")
        params = payload.get("params", payload)
        if idemp_key and "idempotency_key" not in params:
            params["idempotency_key"] = idemp_key
        dispatch_remote = bool(payload.get("remote", False))

        if dispatch_remote:
            job_id = provider.enqueue_ai_inbox_task({"command": cmd, **params}, scope_default="gateway-remote", job_type_default=cmd)
            provider.notify_telemetry_event()
            return HTTPResponse(
                status_code=202,
                payload={
                    "status": "accepted",
                    "state": "[ INBOX ]",
                    "job_id": job_id,
                    "command": cmd,
                    "message": "AI task accepted and queued into [ INBOX ] state. Decoupled from port 8080."
                }
            )

        task_res = execute_task_command(cmd, params)
        provider.notify_telemetry_event()
        rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
        ack = task_res.get("ack")
        headers = {}
        if isinstance(ack, dict) and ack.get("ack_id"):
            headers["X-Gateway-Ack-ID"] = str(ack["ack_id"])
        if isinstance(ack, dict) and ack.get("sequence_id") is not None:
            headers["X-Gateway-Sequence-ID"] = str(ack["sequence_id"])
        headers["X-Gateway-RTT-MS"] = str(rtt_ms)

        try:
            from hud.shared_memory import get_shared_memory_store
            seq_id = ack.get("sequence_id") if isinstance(ack, dict) else None
            get_shared_memory_store().record_task_completion(
                agent_id="agent-supervisor",
                task_id=f"task-local-{seq_id or int(time.time()*1000)}",
                task_type=cmd,
                status="completed" if not task_res.get("error") else "failed",
                input_summary={"command": cmd, "remote": False},
                output_summary={"result": str(task_res.get("result", task_res))[:200]},
                duration_ms=float(rtt_ms or 0.0)
            )
        except Exception:
            pass

        return HTTPResponse(
            status_code=200,
            headers=headers,
            payload={"status": "ok", "task": task_res, "ack": ack, "round_trip_ms": rtt_ms}
        )

    router.register("/api/gateway/tasks", "POST", handle_gateway_tasks_post, service="aios-gateway")

    # 9. Gateway Crons (POST)
    def handle_gateway_crons_post(request: HTTPRequest, body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        start_t = time.monotonic()
        action = payload.get("action", "update")
        cron_id = payload.get("id") or payload.get("cron_id") or payload.get("job_id")
        idemp_key = request.headers.get("X-Idempotency-Key") or payload.get("idempotency_key")

        try:
            if action == "trigger":
                dispatch_remote = bool(payload.get("remote", False))
                if dispatch_remote:
                    res = send_signed_rpc(provider.get_hermes_gateway_rpc_url(), "hermes.cron.trigger", {"id": cron_id}, idempotency_key=idemp_key)
                    provider.notify_telemetry_event()
                    return res
                outcome = trigger_cron_job(cron_id)
                provider.notify_telemetry_event()
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                seq_id = outcome.get("sequence_id")
                headers = {"X-Gateway-RTT-MS": str(rtt_ms)}
                if seq_id is not None:
                    headers["X-Gateway-Sequence-ID"] = str(seq_id)
                return HTTPResponse(status_code=200, headers=headers, payload={"status": "ok", "triggered": outcome, "round_trip_ms": rtt_ms})
            elif action == "delete":
                del_ok = delete_cron_job(cron_id)
                provider.notify_telemetry_event()
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                return HTTPResponse(status_code=200, headers={"X-Gateway-RTT-MS": str(rtt_ms)}, payload={"status": "ok" if del_ok else "not_found", "deleted": del_ok, "round_trip_ms": rtt_ms})
            else:
                upd = update_cron_job(cron_id, payload)
                provider.notify_telemetry_event()
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                seq_id = upd.get("sequence_id")
                headers = {"X-Gateway-RTT-MS": str(rtt_ms)}
                if seq_id is not None:
                    headers["X-Gateway-Sequence-ID"] = str(seq_id)
                return HTTPResponse(status_code=200, headers=headers, payload={"status": "ok", "cron": upd, "round_trip_ms": rtt_ms})
        except Exception as err:
            return HTTPResponse(status_code=400, payload={"error": str(err), "status": "error"})

    router.register("/api/gateway/crons", "POST", handle_gateway_crons_post, service="aios-gateway")

    # 10. Board Sync (POST)
    def handle_board_sync(request: HTTPRequest, body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        start_t = time.monotonic()
        idemp_key = request.headers.get("X-Idempotency-Key") or payload.get("idempotency_key")
        if idemp_key and "idempotency_key" not in payload:
            payload["idempotency_key"] = idemp_key
        dispatch_remote = bool(payload.get("remote", False))

        if dispatch_remote:
            res = send_signed_rpc(provider.get_hermes_gateway_rpc_url(), "hermes.board.sync", payload, idempotency_key=idemp_key)
            provider.notify_telemetry_event()
            ack = res.get("ack")
            headers = {}
            if isinstance(ack, dict) and ack.get("ack_id"):
                headers["X-Gateway-Ack-ID"] = str(ack["ack_id"])
            if isinstance(ack, dict) and ack.get("sequence_id") is not None:
                headers["X-Gateway-Sequence-ID"] = str(ack["sequence_id"])
            return HTTPResponse(status_code=200, headers=headers, payload=res)
        else:
            rpc_res = execute_gateway_rpc("hermes.board.sync", payload)
            provider.notify_telemetry_event()
            rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
            ack = rpc_res.get("ack")
            headers = {"X-Gateway-RTT-MS": str(rtt_ms)}
            if isinstance(ack, dict) and ack.get("ack_id"):
                headers["X-Gateway-Ack-ID"] = str(ack["ack_id"])
            if isinstance(ack, dict) and ack.get("sequence_id") is not None:
                headers["X-Gateway-Sequence-ID"] = str(ack["sequence_id"])
            out = rpc_res.get("result", rpc_res)
            if isinstance(out, dict):
                out["round_trip_ms"] = rtt_ms
                if ack:
                    out["ack"] = ack
            return HTTPResponse(status_code=200, headers=headers, payload=out)

    router.register("/api/gateway/board/sync", "POST", handle_board_sync, service="aios-gateway")

    # 11. Decoupled AI Task Queue Endpoints
    def handle_ai_task_enqueue(body: Optional[Dict[str, Any]] = None, **kwargs):
        job_id = provider.enqueue_ai_inbox_task(body or {}, scope_default="ui-task", job_type_default="ai_task")
        return HTTPResponse(
            status_code=202,
            payload={
                "status": "accepted",
                "state": "[ INBOX ]",
                "job_id": job_id,
                "message": "AI task accepted and queued in [ INBOX ] state. Synchronous trap severed."
            }
        )

    for alias in ("/api/ai/task", "/api/hermes/task", "/api/task/execute", "/api/tasks/ai", "/api/ai/execute"):
        router.register(alias, "POST", handle_ai_task_enqueue, service="ai-task-queue")

    # 12. Hermes Probe Execution
    def handle_hermes_probe(body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        if payload.get("task") or payload.get("prompt") or payload.get("async") or payload.get("client_data") or payload.get("job_type"):
            job_id = provider.enqueue_ai_inbox_task(payload, scope_default="hermes-probe", job_type_default="probe_task")
            return HTTPResponse(
                status_code=202,
                payload={"status": "accepted", "state": "[ INBOX ]", "job_id": job_id, "message": "Probe task queued in [ INBOX ] state."}
            )
        return provider.execute_hermes_probe(payload)

    router.register("/api/hermes/probe", "POST", handle_hermes_probe, service="hermes-probe")
