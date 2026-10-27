"""
hud/routes/os_routes.py
Domain route module for AI OS Dashboard, real-time SSE telemetry streams, board ops, and Obsidian vault state.
"""

from __future__ import annotations
import json
import time
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Iterator

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse


def register_os_routes(router: TypeSafeRouter, provider: Any):
    # 1. Server-Sent Events Telemetry Stream
    def handle_os_stream(**kwargs):
        def stream_generator() -> Iterator[bytes]:
            yield b"retry: 3000\n\n"
            last_hash, last_sent, seq = None, 0.0, 0
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                try:
                    frame = provider.os_frame()
                except Exception as exc:
                    frame = {"error": f"{type(exc).__name__}: {exc}", "hash": "error"}

                if frame.get("hash") != last_hash:
                    seq += 1
                    frame["seq"] = seq
                    payload = json.dumps(frame, default=str)
                    yield f"event: telemetry\nid: {seq}\ndata: {payload}\n\n".encode("utf-8")
                    last_hash, last_sent = frame.get("hash"), time.monotonic()
                elif time.monotonic() - last_sent >= 15:
                    ping = json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "seq": seq})
                    yield f"event: ping\ndata: {ping}\n\n".encode("utf-8")
                    last_sent = time.monotonic()

                # Fast-path event wait: wakes immediately upon state change or every 2 seconds
                provider.wait_telemetry_event(timeout=2.0)

        headers = {
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-transform, no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff"
        }
        return HTTPResponse(status_code=200, headers=headers, body=stream_generator())

    router.register("/api/os/stream", "GET", handle_os_stream, service="os-telemetry-stream")

    # 2. OS Frame & Telemetry Snapshot
    def handle_os_telemetry(**kwargs):
        return provider.os_frame()

    router.register("/api/os/telemetry", "GET", handle_os_telemetry, service="os-dashboard")

    # 3. Obsidian State & Rescan (GET)
    def handle_os_obsidian_get(query: Optional[Dict[str, list]] = None, **kwargs):
        q = (query or {}).get("rescan") or [""]
        if q[0] in ("1", "true", "yes"):
            from hud import os_dashboard as osd
            osd.invalidate_vault_cache()
        return provider.os_frame().get("obsidian", {})

    router.register("/api/os/obsidian", "GET", handle_os_obsidian_get, service="os-dashboard")

    # 4. Board State (GET & POST)
    def handle_os_board_get(**kwargs):
        return provider.os_board_payload()

    router.register("/api/os/board", "GET", handle_os_board_get, service="os-dashboard")

    def handle_os_board_post(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud import os_dashboard as osd
        osd.apply_board_op(body or {})
        provider.notify_telemetry_event()
        return provider.os_board_payload()

    router.register("/api/os/board", "POST", handle_os_board_post, service="os-dashboard")

    # 5. Inbox & Outbox (GET)
    def handle_os_inbox(**kwargs):
        return provider.os_inbox_payload()

    router.register("/api/os/inbox", "GET", handle_os_inbox, service="os-dashboard")

    def handle_os_outbox(**kwargs):
        return provider.os_outbox_payload()

    router.register("/api/os/outbox", "GET", handle_os_outbox, service="os-dashboard")

    # 6. Docs
    def handle_os_docs(**kwargs):
        from hud import os_dashboard as osd
        return {"docs": osd.list_docs()}

    router.register("/api/os/docs", "GET", handle_os_docs, service="os-dashboard")

    def handle_os_doc(query: Optional[Dict[str, list]] = None, **kwargs):
        from hud import os_dashboard as osd
        doc_id = ((query or {}).get("id") or [""])[0]
        return osd.read_doc(doc_id)

    router.register("/api/os/doc", "GET", handle_os_doc, service="os-dashboard")

    # 7. Scratch Editor
    def handle_editor_files(**kwargs):
        from hud import os_dashboard as osd
        return osd.editor_list()

    router.register("/api/os/editor/files", "GET", handle_editor_files, service="os-dashboard")

    def handle_editor_file(query: Optional[Dict[str, list]] = None, **kwargs):
        from hud import os_dashboard as osd
        name = ((query or {}).get("name") or [""])[0]
        return osd.editor_read(name)

    router.register("/api/os/editor/file", "GET", handle_editor_file, service="os-dashboard")

    def handle_editor_save(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud import os_dashboard as osd
        payload = body or {}
        return osd.editor_save(str(payload.get("name", "")), payload.get("text"), payload.get("base_sha256") or None)

    router.register("/api/os/editor/save", "POST", handle_editor_save, service="os-dashboard")

    # 8. Obsidian Actions (POST)
    def handle_obsidian_note(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud import os_dashboard as osd
        res = osd.create_vault_note(body or {})
        provider.notify_telemetry_event()
        return res

    router.register("/api/os/obsidian/note", "POST", handle_obsidian_note, service="os-dashboard")

    def handle_obsidian_rescan(**kwargs):
        from hud import os_dashboard as osd
        osd.invalidate_vault_cache()
        provider.notify_telemetry_event()
        return provider.os_frame().get("obsidian", {})

    router.register("/api/os/obsidian/rescan", "POST", handle_obsidian_rescan, service="os-dashboard")

    # 9. Outbox Decision (POST)
    def handle_outbox_decide(body: Optional[Dict[str, Any]] = None, **kwargs):
        from hud.gtm import decide
        payload = body or {}
        stage_file = os.path.join(provider.GTM_DIR, "staged_outreach.json")
        decide(stage_file, str(payload.get("id", "")), str(payload.get("revision", "")), str(payload.get("decision", "")))
        provider.notify_telemetry_event()
        return provider.os_outbox_payload()

    router.register("/api/os/outbox/decide", "POST", handle_outbox_decide, service="os-dashboard")

    # 10. Aggregated HUD Status (GET)
    def handle_hud_aggregated(**kwargs):
        return {
            "hermes": provider.get_hermes_telemetry(),
            "ledger": provider.get_offline_ledger_and_invariant(),
            "alerts": provider.get_alerts_status()
        }

    router.register("/api/hud", "GET", handle_hud_aggregated, service="hud-telemetry")
