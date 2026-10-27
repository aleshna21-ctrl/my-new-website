"""
hud/routes/cortex_routes.py
Domain route module for Cortex telemetry, hierarchy DAG, streaming time-series, and Encore observability.
"""

from __future__ import annotations
from typing import Dict, Any, Optional

from hud.type_safe_router import TypeSafeRouter, HTTPRequest, HTTPResponse
from data_contracts import (
    StreamingSeriesResponse, CortexHierarchyPayload, SQLiteLedgerPayload,
    EncoreObservabilityMetrics
)


def register_cortex_routes(router: TypeSafeRouter, provider: Any):
    """
    Registers all Cortex dashboard, hierarchy, streaming, and observability endpoints.
    `provider` provides the underlying data access methods (or defaults to hud_server functions).
    """

    # 1. Cortex Quotas & Credits
    def handle_credits(**kwargs):
        return provider.get_cortex_credits()

    router.register("/api/cortex/credits", "GET", handle_credits, service="cortex-credits")

    # 2. Automated Task History & Auto-Approval
    def handle_tasks(**kwargs):
        return provider.get_cortex_automated_tasks()

    router.register("/api/cortex/tasks", "GET", handle_tasks, service="cortex-tasks")

    # 3. 4-Tier DAG Hierarchy
    def handle_hierarchy(trace_id: Optional[str] = None, **kwargs):
        return provider.get_cortex_hierarchy(trace_id=trace_id)

    router.register("/api/cortex/hierarchy", "GET", handle_hierarchy,
                    response_model=CortexHierarchyPayload, service="cortex-hierarchy")

    # 4. Rolling Streaming Series
    def handle_streaming_series(trace_id: Optional[str] = None, **kwargs):
        series_data = provider.get_cortex_streaming_series(trace_id=trace_id)
        if isinstance(series_data, list):
            return {"status": "ok", "series": series_data}
        return series_data

    router.register("/api/cortex/streaming/series", "GET", handle_streaming_series,
                    service="cortex-streaming")
    router.register("/api/cortex/streaming-series", "GET", handle_streaming_series,
                    service="cortex-streaming")

    # 5. Append Streaming Metric Point
    def handle_streaming_record(**kwargs):
        return provider.record_cortex_streaming_point()

    router.register("/api/cortex/streaming/record", "POST", handle_streaming_record,
                    service="cortex-streaming")

    # 6. Auto-accept toggle
    def handle_auto_accept(body: Optional[Dict[str, Any]] = None, **kwargs):
        if hasattr(provider, "toggle_cortex_auto_accept"):
            return provider.toggle_cortex_auto_accept(body or {})
        return {"status": "ok"}

    router.register("/api/cortex/auto-accept", "POST", handle_auto_accept, service="cortex-tasks")

    # 7. Encore Observability Metrics & Traces
    def handle_metrics(**kwargs):
        return router.observability.get_metrics()

    router.register("/api/observability/metrics", "GET", handle_metrics,
                    response_model=EncoreObservabilityMetrics, service="encore-observability")

    def handle_traces(**kwargs):
        return {"traces": router.observability.get_recent_spans(limit=50)}

    router.register("/api/observability/traces", "GET", handle_traces, service="encore-observability")

    def handle_health(**kwargs):
        return {"status": "healthy", "service": "aios-hud-server", "framework": "encore", "version": "1.58.8"}

    router.register("/api/observability/health", "GET", handle_health, service="encore-observability")

