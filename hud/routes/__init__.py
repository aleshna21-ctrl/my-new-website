"""
hud/routes/__init__.py
Central domain router registration.
Mounts all partitioned domain routes onto the central TypeSafeRouter.
"""

from __future__ import annotations
from typing import Any

from hud.type_safe_router import TypeSafeRouter
from hud.routes.static_routes import register_static_routes
from hud.routes.cortex_routes import register_cortex_routes
from hud.routes.gateway_routes import register_gateway_routes
from hud.routes.quarantine_routes import register_quarantine_routes
from hud.routes.os_routes import register_os_routes
from hud.routes.ledger_routes import register_ledger_routes
from hud.routes.stream_routes import register_stream_routes


def register_all_routes(router: TypeSafeRouter, provider: Any):
    """
    Mounts all partitioned domain route modules onto the central TypeSafeRouter.
    """
    register_static_routes(router)
    register_cortex_routes(router, provider)
    register_gateway_routes(router, provider)
    register_quarantine_routes(router, provider)
    register_os_routes(router, provider)
    register_ledger_routes(router, provider)
    register_stream_routes(router, provider)
