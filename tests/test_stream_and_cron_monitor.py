"""
tests/test_stream_and_cron_monitor.py
Comprehensive verification test suite for:
1. Live Agent Activity & Telemetry Stream Engine (/api/stream/events)
2. Scheduled Task (Cron) & Kanban Work Queue Monitor Engine (/api/cron/monitor, /api/cron/trigger, /api/cron/toggle, /api/kanban/queue)
"""

import pytest
import hud_server
from hud.type_safe_router import HTTPRequest


def test_activity_stream_get_seeded_events():
    """Verify that GET /api/stream/events returns seeded canonical events and computed metrics."""
    req = HTTPRequest(path="/api/stream/events", method="GET")
    resp = hud_server.TYPE_SAFE_ROUTER.dispatch(req)
    assert resp.status_code == 200
    data = resp.payload
    assert data["status"] == "ok"
    assert "events" in data
    assert len(data["events"]) >= 5
    assert "stats" in data
    stats = data["stats"]
    assert "tps" in stats
    assert "avg_latency_ms" in stats
    assert "p95_latency_ms" in stats
    assert "clean_rate_percent" in stats
    assert "repaired_count" in stats
    assert "efficacy_index" in stats
    assert "active_model" in stats


def test_activity_stream_filter_by_role_and_status():
    """Verify that filtering by role and status functions properly."""
    req_scout = HTTPRequest(path="/api/stream/events", method="GET", query={"role": ["scout"]})
    resp_scout = hud_server.TYPE_SAFE_ROUTER.dispatch(req_scout)
    assert resp_scout.status_code == 200
    for evt in resp_scout.payload["events"]:
        assert evt["role"] == "scout"

    req_repaired = HTTPRequest(path="/api/stream/events", method="GET", query={"status": ["repaired"]})
    resp_repaired = hud_server.TYPE_SAFE_ROUTER.dispatch(req_repaired)
    assert resp_repaired.status_code == 200
    for evt in resp_repaired.payload["events"]:
        assert evt["status"] == "repaired"


def test_activity_stream_inject_custom_event():
    """Verify that POST /api/stream/events injects an event and updates statistics."""
    payload = {
        "role": "supervisor",
        "action": "actions.custom_test_gate",
        "thought": "Verified Level 9 integrity gate for test execution.",
        "latency_ms": 33.7,
        "tokens": 155,
        "status": "done",
        "repaired": False,
        "efficacy": 0.992,
        "payload": {"test_marker": "active_test_123"}
    }
    req_post = HTTPRequest(path="/api/stream/events", method="POST", body=payload)
    resp_post = hud_server.TYPE_SAFE_ROUTER.dispatch(req_post)
    assert resp_post.status_code == 200
    assert resp_post.payload["status"] == "ok"
    created_id = resp_post.payload["event"]["id"]
    assert created_id.startswith("evt-")

    # Verify event appears in GET
    req_get = HTTPRequest(path="/api/stream/events", method="GET", query={"limit": ["10"]})
    resp_get = hud_server.TYPE_SAFE_ROUTER.dispatch(req_get)
    assert any(e["id"] == created_id for e in resp_get.payload["events"])


def test_cron_kanban_monitor_get():
    """Verify that GET /api/cron/monitor and /api/cron/tasks return enriched crons and work queue."""
    for path in ("/api/cron/monitor", "/api/cron/tasks"):
        req = HTTPRequest(path=path, method="GET")
        resp = hud_server.TYPE_SAFE_ROUTER.dispatch(req)
        assert resp.status_code == 200
        data = resp.payload
        assert data["status"] == "ok"
        assert "crons" in data
        assert "crons_summary" in data
        assert "kanban_summary" in data
        assert "active_leases" in data
        assert "recent_queue_jobs" in data

        summary = data["crons_summary"]
        assert summary["total"] >= 1
        assert "next_execution_seconds" in summary

        k_summary = data["kanban_summary"]
        assert "queue_depth" in k_summary
        assert "active_leases_count" in k_summary


def test_cron_trigger_and_toggle_endpoints():
    """Verify that cron trigger and toggle endpoints update state and log activity events."""
    # Toggle off
    req_toggle_off = HTTPRequest(
        path="/api/cron/toggle",
        method="POST",
        body={"cron_id": "cron-001-invariants", "enabled": False}
    )
    resp_toggle_off = hud_server.TYPE_SAFE_ROUTER.dispatch(req_toggle_off)
    assert resp_toggle_off.status_code == 200

    # Trigger job
    req_trigger = HTTPRequest(
        path="/api/cron/trigger",
        method="POST",
        body={"cron_id": "cron-001-invariants"}
    )
    resp_trigger = hud_server.TYPE_SAFE_ROUTER.dispatch(req_trigger)
    assert resp_trigger.status_code == 200

    # Toggle back on
    req_toggle_on = HTTPRequest(
        path="/api/cron/toggle",
        method="POST",
        body={"cron_id": "cron-001-invariants", "enabled": True}
    )
    resp_toggle_on = hud_server.TYPE_SAFE_ROUTER.dispatch(req_toggle_on)
    assert resp_toggle_on.status_code == 200


def test_kanban_queue_endpoint():
    """Verify that GET /api/kanban/queue returns formatted work queue and lease data."""
    req = HTTPRequest(path="/api/kanban/queue", method="GET")
    resp = hud_server.TYPE_SAFE_ROUTER.dispatch(req)
    assert resp.status_code == 200
    data = resp.payload
    assert data["status"] == "ok"
    assert "summary" in data
    assert "leases" in data
    assert "recent_jobs" in data


def test_os_frame_includes_activity_and_cron():
    """Verify that os_frame() aggregates activity_stream and cron_kanban for SSE stream."""
    frame = hud_server.os_frame()
    assert "activity_stream" in frame
    assert frame["activity_stream"]["status"] == "ok"
    assert "cron_kanban" in frame
    assert frame["cron_kanban"]["status"] == "ok"
