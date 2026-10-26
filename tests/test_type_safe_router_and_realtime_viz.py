"""
tests/test_type_safe_router_and_realtime_viz.py
Comprehensive test suite for:
1. Type-Safe API Routing and Pydantic contract validation.
2. Built-in Encore Observability (traceparent, X-Encore-Trace-ID, spans, metrics).
3. Real-Time Visualization Skill (SQLite JSON metrics, 4-tier DAG hierarchy, rolling 60s streaming buffer).
4. HUD Server integration with type-safe dispatch and observability headers.
"""

import json
import os
import sys
import tempfile
import sqlite3
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT))

import data_contracts
from data_contracts import (
    StreamingSeriesPoint, StreamingSeriesResponse,
    DAGNode, DAGLink, CortexHierarchyPayload,
    SQLiteJobRecord, SQLiteLedgerPayload,
    EncoreSpanRecord, EncoreObservabilityMetrics,
    GatewayRPCRequest, GatewayRPCResponse
)
from hud.type_safe_router import (
    EncoreObservabilityEngine, RealTimeVisualizationEngine,
    TypeSafeRouter, GLOBAL_OBSERVABILITY
)
import hud_server


class TypeSafeRouterObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.observability = EncoreObservabilityEngine(service_name="test-service", max_traces=100)
        self.router = TypeSafeRouter(observability=self.observability)

    def test_traceparent_generation_and_parsing(self):
        trace_id = self.observability.generate_trace_id()
        span_id = self.observability.generate_span_id()
        self.assertEqual(len(trace_id), 32)
        self.assertEqual(len(span_id), 16)

        tp = self.observability.build_traceparent(trace_id, span_id)
        self.assertTrue(tp.startswith(f"00-{trace_id}-{span_id}-"))

        parsed_t, parsed_s = self.observability.parse_traceparent(tp)
        self.assertEqual(parsed_t, trace_id)
        self.assertEqual(parsed_s, span_id)

    def test_observability_span_context_and_metrics(self):
        with self.observability.start_span("test-operation", method="GET") as span:
            span.add_attribute("custom_key", "custom_val")
            self.assertEqual(span.service, "test-service")

        metrics = self.observability.get_metrics()
        self.assertEqual(metrics.service_name, "test-service")
        self.assertEqual(metrics.total_requests, 1)
        self.assertEqual(metrics.recent_traces_count, 1)
        self.assertEqual(metrics.error_count, 0)
        self.assertGreaterEqual(metrics.uptime_seconds, 0.0)

        spans = self.observability.get_recent_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "test-operation")
        self.assertEqual(spans[0]["attributes"]["custom_key"], "custom_val")

    def test_type_safe_route_registration_and_validation(self):
        class PingRequest(data_contracts.BaseModel):
            message: str

        class PingResponse(data_contracts.BaseModel):
            echo: str
            received_length: int

        def handle_ping(request_data: PingRequest, **kwargs):
            return PingResponse(echo=request_data.message, received_length=len(request_data.message))

        self.router.register(
            "/api/test/ping", "POST",
            handle_ping,
            request_model=PingRequest,
            response_model=PingResponse,
            service="test-ping"
        )

        # 1. Valid request
        payload, status, headers = self.router.dispatch(
            "/api/test/ping", "POST",
            headers={},
            body={"message": "hello-aios"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["echo"], "hello-aios")
        self.assertEqual(payload["received_length"], 10)
        self.assertIn("X-Encore-Trace-ID", headers)
        self.assertIn("traceparent", headers)
        self.assertEqual(headers["X-Encore-Service"], "test-ping")

        # 2. Invalid request schema -> 400
        payload, status, headers = self.router.dispatch(
            "/api/test/ping", "POST",
            headers={},
            body={"invalid_key": 123}
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["status"], "validation_error")
        self.assertIn("details", payload)


class RealTimeVisualizationEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "job_ledger.db")

        # Create realistic SQLite job_ledger.db structure
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE jobs (
                    job_id TEXT PRIMARY KEY,
                    scope_id TEXT,
                    job_type TEXT,
                    state TEXT,
                    attempt_count INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE hud_terminal_events (
                    event_id TEXT PRIMARY KEY,
                    job_id TEXT,
                    event_type TEXT,
                    timestamp_utc TEXT
                )
            """)
            conn.execute("""
                INSERT INTO jobs (job_id, scope_id, job_type, state, attempt_count, created_at, updated_at)
                VALUES ('job-001', 'cambridge-specialty', 'reconciliation', 'completed', 1, '2026-10-26T00:00:00Z', '2026-10-26T00:01:00Z'),
                       ('job-002', 'vetpowered-cnc', 'probe', 'running', 0, '2026-10-26T00:02:00Z', '2026-10-26T00:02:30Z'),
                       ('job-003', 'adversarial-batch-01', 'invoice-audit', 'quarantined', 2, '2026-10-26T00:03:00Z', '2026-10-26T00:03:15Z')
            """)
            conn.execute("""
                INSERT INTO hud_terminal_events (event_id, job_id, event_type, timestamp_utc)
                VALUES ('ev-seal-01', 'job-001', 'diode_sealed', '2026-10-26T00:01:05Z')
            """)
            conn.commit()
        finally:
            conn.close()

        self.engine = RealTimeVisualizationEngine(db_path_resolver=lambda: self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sqlite_ledger_read_only_diode(self):
        ledger = self.engine.get_sqlite_ledger()
        self.assertIsInstance(ledger, SQLiteLedgerPayload)
        self.assertEqual(ledger.mode, "ro")
        self.assertEqual(ledger.total_jobs, 3)
        self.assertIn("jobs", ledger.tables)
        self.assertEqual(ledger.tables["jobs"]["row_count"], 3)
        self.assertEqual(len(ledger.terminal_events), 1)

    def test_4_tier_dag_hierarchy_generation(self):
        hierarchy = self.engine.generate_dag_hierarchy()
        self.assertIsInstance(hierarchy, CortexHierarchyPayload)

        # Verify layer structure
        self.assertEqual(len(hierarchy.layers), 4)
        layer_names = [l.name for l in hierarchy.layers]
        self.assertIn("Governance Core", layer_names)
        self.assertIn("Execution Scopes", layer_names)
        self.assertIn("SQLite Jobs", layer_names)
        self.assertIn("Terminal Diodes", layer_names)

        # Verify summary stats
        self.assertEqual(hierarchy.summary.jobs_count, 3)
        self.assertEqual(hierarchy.summary.quarantined_count, 1)
        self.assertGreaterEqual(hierarchy.summary.scopes_count, 3)

        # Verify node types
        node_types = set(n.type for n in hierarchy.nodes)
        self.assertIn("root", node_types)
        self.assertIn("scope", node_types)
        self.assertIn("job", node_types)
        self.assertIn("diode", node_types)

    def test_rolling_60s_streaming_buffer_dual_axis(self):
        # Insert 3 sample streaming points
        pt1 = self.engine.record_streaming_point(
            credits_remaining=95000, credits_consumed=5000,
            burn_rate=12.5, rtt_ms=4.2, jobs_active=1, jobs_completed=2, total_probes=10
        )
        self.assertIsInstance(pt1, StreamingSeriesPoint)
        self.assertEqual(pt1.credits_remaining, 95000)
        self.assertEqual(pt1.burn_rate, 12.5)

        stream_resp = self.engine.get_streaming_series()
        self.assertIsInstance(stream_resp, StreamingSeriesResponse)
        self.assertEqual(stream_resp.status, "ok")
        self.assertEqual(len(stream_resp.series), 1)
        self.assertEqual(stream_resp.window_seconds, 60)


class HUDServerObservabilityIntegrationTests(unittest.TestCase):
    def test_hud_server_type_safe_endpoints_response(self):
        # Test registered routes in hud_server.TYPE_SAFE_ROUTER
        routes = hud_server.TYPE_SAFE_ROUTER._routes
        self.assertIn(("/api/cortex/streaming-series", "GET"), routes)
        self.assertIn(("/api/cortex/hierarchy", "GET"), routes)
        self.assertIn(("/api/sqlite/ledger", "GET"), routes)
        self.assertIn(("/api/observability/metrics", "GET"), routes)
        self.assertIn(("/api/observability/traces", "GET"), routes)
        self.assertIn(("/api/observability/health", "GET"), routes)

        # Dispatch GET /api/observability/metrics
        metrics_resp, status, headers = hud_server.TYPE_SAFE_ROUTER.dispatch(
            "/api/observability/metrics", "GET", headers={}
        )
        self.assertEqual(status, 200)
        self.assertEqual(metrics_resp["service_name"], "aios-hud-server")
        self.assertEqual(metrics_resp["encore_framework_version"], "1.58.8")
        self.assertIn("X-Encore-Trace-ID", headers)
        self.assertIn("traceparent", headers)

        # Dispatch GET /api/cortex/streaming-series
        stream_resp, status, headers = hud_server.TYPE_SAFE_ROUTER.dispatch(
            "/api/cortex/streaming-series", "GET", headers={}
        )
        self.assertEqual(status, 200)
        self.assertEqual(stream_resp["status"], "ok")
        self.assertIn("series", stream_resp)

        # Dispatch GET /api/cortex/hierarchy
        hierarchy_resp, status, headers = hud_server.TYPE_SAFE_ROUTER.dispatch(
            "/api/cortex/hierarchy", "GET", headers={}
        )
        self.assertEqual(status, 200)
        self.assertIn("nodes", hierarchy_resp)
        self.assertIn("layers", hierarchy_resp)
        self.assertIn("summary", hierarchy_resp)


if __name__ == "__main__":
    unittest.main()
