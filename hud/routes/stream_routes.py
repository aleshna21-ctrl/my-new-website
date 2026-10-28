"""
hud/routes/stream_routes.py
Domain route module for Hermes Live Activity Stream & Telemetry,
and Scheduled Task (Cron) & Kanban Multi-Agent Work Queue Monitor.
"""

from __future__ import annotations
import json
import time
from typing import Dict, Any, Optional

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse


def register_stream_routes(router: TypeSafeRouter, provider: Any):
    """
    Registers endpoints for:
    1. Live Agent Activity & Telemetry Stream (/api/stream/events, /api/hermes/activity-stream)
    2. Scheduled Task (Cron) & Kanban Queue Monitor (/api/cron/monitor, /api/cron/tasks, /api/cron/trigger, /api/cron/toggle, /api/kanban/queue)
    """

    # 1. Activity Stream - GET
    def handle_stream_events_get(query: Optional[Dict[str, list]] = None, **kwargs):
        limit = 50
        role = None
        status = None
        if query:
            if "limit" in query and query["limit"]:
                try:
                    limit = int(query["limit"][0])
                except (ValueError, TypeError):
                    limit = 50
            if "role" in query and query["role"]:
                role = query["role"][0]
            if "status" in query and query["status"]:
                status = query["status"][0]

        return provider.get_activity_stream(limit=limit, role=role, status=status)

    router.register("/api/stream/events", "GET", handle_stream_events_get, service="activity-stream")
    router.register("/api/hermes/activity-stream", "GET", handle_stream_events_get, service="activity-stream")

    # 2. Activity Stream - POST (Inject activity event)
    def handle_stream_events_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        role = payload.get("role", "exec")
        action = payload.get("action", "actions.custom_event")
        thought = payload.get("thought", "")
        latency_ms = payload.get("latency_ms", 35.0)
        tokens = payload.get("tokens", 100)
        status = payload.get("status", "done")
        repaired = payload.get("repaired", False)
        efficacy = payload.get("efficacy", 0.95)
        event_payload = payload.get("payload", {})
        event_id = payload.get("id")

        evt = provider.record_activity_event(
            role=role,
            action=action,
            thought=thought,
            latency_ms=latency_ms,
            tokens=tokens,
            status=status,
            repaired=repaired,
            efficacy=efficacy,
            payload=event_payload,
            event_id=event_id
        )
        return {"status": "ok", "event": evt}

    router.register("/api/stream/events", "POST", handle_stream_events_post, service="activity-stream")

    # 3. Scheduled Task (Cron) & Kanban Work Queue Monitor - GET
    def handle_cron_monitor_get(**kwargs):
        return provider.get_cron_kanban_monitor()

    router.register("/api/cron/monitor", "GET", handle_cron_monitor_get, service="cron-kanban-monitor")
    router.register("/api/cron/tasks", "GET", handle_cron_monitor_get, service="cron-kanban-monitor")

    # 4. Trigger Cron Job - POST
    def handle_cron_trigger_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        return provider.trigger_cron_job_endpoint(body or {})

    router.register("/api/cron/trigger", "POST", handle_cron_trigger_post, service="cron-kanban-monitor")

    # 5. Toggle Cron Job - POST
    def handle_cron_toggle_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        return provider.toggle_cron_job_endpoint(body or {})

    router.register("/api/cron/toggle", "POST", handle_cron_toggle_post, service="cron-kanban-monitor")

    # 6. Kanban Queue & Leases - GET
    def handle_kanban_queue_get(**kwargs):
        monitor_data = provider.get_cron_kanban_monitor()
        return {
            "status": "ok",
            "summary": monitor_data.get("kanban_summary", {}),
            "leases": monitor_data.get("active_leases", []),
            "recent_jobs": monitor_data.get("recent_queue_jobs", [])
        }

    router.register("/api/kanban/queue", "GET", handle_kanban_queue_get, service="cron-kanban-monitor")
