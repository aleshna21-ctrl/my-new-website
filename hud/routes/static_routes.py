"""
hud/routes/static_routes.py
Domain route module for serving static assets, UI prototypes, and applying CSP policies.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse

HUD_DIR = os.environ.get("HUD_DIR", str(Path(__file__).resolve().parent.parent.parent))
OS_PAGE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
               "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon"
}


def _serve_file(relative_path: str, csp: str | None = None) -> HTTPResponse:
    target = os.path.normpath(os.path.join(HUD_DIR, relative_path.lstrip("/\\")))
    if not target.startswith(os.path.abspath(HUD_DIR)):
        return HTTPResponse(status_code=403, payload={"error": "Access forbidden"}, content_type="application/json")
    if not os.path.isfile(target):
        return HTTPResponse(status_code=404, payload={"error": "File not found"}, content_type="application/json")

    ext = os.path.splitext(target)[1].lower()
    content_type = MIME_TYPES.get(ext, "application/octet-stream")

    try:
        with open(target, "rb") as f:
            raw = f.read()
    except Exception as exc:
        return HTTPResponse(status_code=500, payload={"error": str(exc)}, content_type="application/json")

    headers = {
        "Content-Type": content_type,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Length": str(len(raw))
    }
    if csp:
        headers["Content-Security-Policy"] = csp
        headers["Referrer-Policy"] = "no-referrer"

    return HTTPResponse(status_code=200, headers=headers, body=raw)


def register_static_routes(router: TypeSafeRouter):
    # Primary view: AI OS dashboard
    def handle_root(**kwargs):
        return _serve_file(os.path.join("static", "os.html"), csp=OS_PAGE_CSP)

    router.register("/", "GET", handle_root, service="static-ui")
    router.register("/os", "GET", handle_root, service="static-ui")

    # Cockpit views
    def handle_cockpit(**kwargs):
        return _serve_file("index.html")

    router.register("/cockpit", "GET", handle_cockpit, service="static-ui")
    router.register("/index.html", "GET", handle_cockpit, service="static-ui")

    # Static assets under static/
    def handle_static(path: str, **kwargs):
        rel = path.lstrip("/")
        return _serve_file(rel)

    router.register("/static/*", "GET", handle_static, service="static-assets", is_prefix=True)

    # Prototypes
    for proto in (
        "/prototype-1-ring-command.html",
        "/prototype-2-minimal-3d.html",
        "/prototype-3-cockpit-split.html"
    ):
        p_path = proto
        router.register(p_path, "GET", lambda p=p_path, **kw: _serve_file(p.lstrip("/")), service="static-prototype")

    # Legacy fallback view
    def handle_legacy(**kwargs):
        # Fallback to index.html if present, else empty
        idx_path = os.path.join(HUD_DIR, "index.html")
        if os.path.isfile(idx_path):
            return _serve_file("index.html")
        return HTTPResponse(status_code=200, body=b"<!DOCTYPE html><html><body><h1>AIOS HUD</h1></body></html>", content_type="text/html; charset=utf-8")

    router.register("/legacy", "GET", handle_legacy, service="static-legacy")
