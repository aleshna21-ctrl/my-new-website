"""
hud/routes/quarantine_routes.py
Domain route module for Invoice Quarantine invariant inspection, CSV repair, and fixture resets.
"""

from __future__ import annotations
from typing import Dict, Any, Optional

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse


def register_quarantine_routes(router: TypeSafeRouter, provider: Any):
    # 1. Inspect Quarantine Invariants & Malformed Rows
    def handle_get_quarantine(**kwargs):
        return provider.get_quarantine_data()

    router.register("/api/quarantine", "GET", handle_get_quarantine, service="quarantine-service")

    # 2. Repair In-Memory / CSV Quarantine Row
    def handle_repair_quarantine(body: Optional[Dict[str, Any]] = None, **kwargs):
        payload = body or {}
        row_idx = int(payload.get("row_idx", payload.get("row", 0)))
        inv_id = payload.get("invoice_id")
        amt = payload.get("amount")
        dt = payload.get("date")
        auto_rec = bool(payload.get("auto_recover", False))
        auto_all = bool(payload.get("auto_recover_all", False))

        res = provider.repair_quarantine_row(
            row_idx=row_idx,
            invoice_id=inv_id,
            amount=amt,
            date=dt,
            auto_recover=auto_rec,
            auto_recover_all=auto_all
        )
        status = 400 if res.get("status") == "error" else 200
        return HTTPResponse(status_code=status, payload=res)

    router.register("/api/quarantine/repair", "POST", handle_repair_quarantine, service="quarantine-service")

    # 3. Reset Quarantine Fixture to Pristine Adversarial Baseline
    def handle_reset_quarantine(**kwargs):
        return provider.reset_quarantine_fixture()

    router.register("/api/quarantine/reset", "POST", handle_reset_quarantine, service="quarantine-service")
