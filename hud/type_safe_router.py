"""
hud/type_safe_router.py
AIOS Backend Framework: Type-Safe API Routing, Microservice Communication & Encore Observability.

Implements:
1. Pydantic-enforced type-safe API routing for microservices and dashboard communication.
2. Built-in Encore Observability (W3C traceparent, X-Encore-Trace-ID, span tracking, and latency percentiles).
3. Real-Time Visualization Skill integration for SQLite JSON metrics, 4-tier DAG hierarchy, and rolling 60s streaming buffer.
"""

from __future__ import annotations
import os
import time
import uuid
import sqlite3
import threading
import inspect
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable, Type, Union, Iterator
from pydantic import BaseModel, ValidationError

import sys
from pathlib import Path
_HUD_DIR = str(Path(__file__).resolve().parent.parent)
if _HUD_DIR not in sys.path or sys.path[0] != _HUD_DIR:
    sys.path.insert(0, _HUD_DIR)

from data_contracts import (
    StreamingSeriesPoint, StreamingSeriesResponse,
    DAGNode, DAGLink, DAGLayerInfo, HierarchySummary, CortexHierarchyPayload,
    SQLiteJobRecord, SQLiteLedgerPayload,
    EncoreSpanRecord, EncoreObservabilityMetrics,
    GatewayRPCRequest, GatewayRPCResponse
)

# --------------------------------------------------------------------------- #
# Encore Built-in Observability & Distributed Tracing Engine
# --------------------------------------------------------------------------- #

class EncoreObservabilityEngine:
    """
    Lightweight, high-performance in-memory observability engine modeled after
    Encore's distributed tracing and continuous system monitoring.
    """
    def __init__(self, service_name: str = "aios-hud-server", max_traces: int = 500):
        self.service_name = service_name
        self.max_traces = max_traces
        self.start_time = time.time()
        self._lock = threading.RLock()
        self._spans: deque[EncoreSpanRecord] = deque(maxlen=max_traces)
        self._latencies_ms: deque[float] = deque(maxlen=1000)
        self.total_requests = 0
        self.error_count = 0
        self.active_spans_count = 0

    def generate_trace_id(self) -> str:
        """Generates a 32-character hex trace ID compatible with W3C and Encore."""
        return uuid.uuid4().hex

    def generate_span_id(self) -> str:
        """Generates a 16-character hex span ID."""
        return uuid.uuid4().hex[:16]

    def build_traceparent(self, trace_id: str, span_id: str, sampled: bool = True) -> str:
        """Constructs standard W3C traceparent header: 00-{trace_id}-{span_id}-{flags}."""
        flags = "01" if sampled else "00"
        return f"00-{trace_id}-{span_id}-{flags}"

    def parse_traceparent(self, header_val: Optional[str]) -> Tuple[str, Optional[str]]:
        """Parses incoming traceparent header or generates fresh trace/span IDs."""
        if header_val and header_val.startswith("00-"):
            parts = header_val.split("-")
            if len(parts) >= 4 and len(parts[1]) == 32 and len(parts[2]) == 16:
                return parts[1], parts[2]
        return self.generate_trace_id(), None

    def start_span(self, name: str, method: str = "GET", parent_span_id: Optional[str] = None,
                   trace_id: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None) -> SpanContext:
        t_id = trace_id or self.generate_trace_id()
        s_id = self.generate_span_id()
        with self._lock:
            self.active_spans_count += 1
            self.total_requests += 1
        return SpanContext(
            engine=self,
            trace_id=t_id,
            span_id=s_id,
            parent_span_id=parent_span_id,
            service=self.service_name,
            name=name,
            method=method,
            attributes=attributes or {}
        )

    def _record_span(self, span: EncoreSpanRecord):
        with self._lock:
            self.active_spans_count = max(0, self.active_spans_count - 1)
            self._spans.append(span)
            self._latencies_ms.append(span.duration_ms)
            if span.status_code >= 400:
                self.error_count += 1

    def get_metrics(self) -> EncoreObservabilityMetrics:
        with self._lock:
            uptime = max(0.001, time.time() - self.start_time)
            lat_list = sorted(self._latencies_ms) if self._latencies_ms else [0.0]
            count = len(lat_list)
            p50 = lat_list[int(count * 0.50)]
            p95 = lat_list[min(count - 1, int(count * 0.95))]
            p99 = lat_list[min(count - 1, int(count * 0.99))]
            avg = sum(lat_list) / count if count else 0.0
            err_rate = (self.error_count / max(1, self.total_requests)) * 100.0

            return EncoreObservabilityMetrics(
                service_name=self.service_name,
                encore_framework_version="1.58.8",
                uptime_seconds=round(uptime, 2),
                total_requests=self.total_requests,
                active_spans=self.active_spans_count,
                avg_latency_ms=round(avg, 2),
                p95_latency_ms=round(p95, 2),
                p99_latency_ms=round(p99, 2),
                error_count=self.error_count,
                error_rate_percent=round(err_rate, 2),
                recent_traces_count=len(self._spans),
                timestamp_utc=datetime.now(timezone.utc).isoformat()
            )

    def get_recent_spans(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [s.model_dump() for s in list(self._spans)[-limit:][::-1]]


class SpanContext:
    def __init__(self, engine: EncoreObservabilityEngine, trace_id: str, span_id: str,
                 parent_span_id: Optional[str], service: str, name: str, method: str,
                 attributes: Dict[str, Any]):
        self.engine = engine
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.service = service
        self.name = name
        self.method = method
        self.attributes = attributes
        self.start_time = time.monotonic()
        self.status_code = 200

    def __enter__(self) -> SpanContext:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = round((time.monotonic() - self.start_time) * 1000.0, 3)
        if exc_type is not None:
            self.status_code = 500
            self.attributes["error"] = str(exc_val)
            self.attributes["error_type"] = exc_type.__name__

        rec = EncoreSpanRecord(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            service=self.service,
            name=self.name,
            method=self.method,
            start_time=self.start_time,
            duration_ms=duration_ms,
            status_code=self.status_code,
            attributes=self.attributes
        )
        self.engine._record_span(rec)

    def set_status(self, code: int):
        self.status_code = code

    def add_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    @property
    def traceparent(self) -> str:
        return self.engine.build_traceparent(self.trace_id, self.span_id)


# Global Observability Engine Instance
GLOBAL_OBSERVABILITY = EncoreObservabilityEngine()


# --------------------------------------------------------------------------- #
# Real-Time Visualization Skill Engine (SQLite JSON & DAG Layout)
# --------------------------------------------------------------------------- #

class RealTimeVisualizationEngine:
    """
    Implements the Next Cortex Real-Time Visualization skill:
    - Zero-loss read-only SQLite ledger inspections.
    - 4-Tier Multi-Level DAG layout for AIOS Governance -> Scopes -> Jobs -> Terminal Diodes.
    - Rolling 60-second circular buffer for dual-axis streaming SVG / Canvas charts.
    """
    def __init__(self, db_path_resolver: Callable[[], str]):
        self.db_path_resolver = db_path_resolver
        self._lock = threading.RLock()
        self._streaming_series: deque[StreamingSeriesPoint] = deque(maxlen=60)
        self.start_time = time.time()

    def get_sqlite_ledger(self, trace_id: Optional[str] = None) -> SQLiteLedgerPayload:
        """
        Executes read-only queries against SQLite job_ledger.db.
        Enforces immutable connection string: file:{db_path}?mode=ro.
        """
        db_path = self.db_path_resolver()
        tables_summary: Dict[str, Any] = {}
        recent_jobs: List[SQLiteJobRecord] = []
        terminal_events: List[dict] = []

        if not os.path.exists(db_path):
            return SQLiteLedgerPayload(
                db_path=db_path,
                tables={},
                jobs=[],
                terminal_events=[],
                total_jobs=0,
                mode="ro",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                trace_id=trace_id
            )

        from job_ledger import JobLedger
        ledger = JobLedger(db_path=db_path, read_only=True)
        try:
            with ledger.connect() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # 1. Discover all tables and row counts
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                table_names = [r["name"] for r in cur.fetchall()]
                for tbl in table_names:
                    try:
                        c = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                        tables_summary[tbl] = {"row_count": c}
                    except Exception:
                        tables_summary[tbl] = {"row_count": 0}

                # 2. Extract recent jobs adhering to the DAG transition protocol
                if "jobs" in table_names:
                    cur.execute(
                        "SELECT job_id, scope_id, job_type, state, attempt_count, created_at, updated_at "
                        "FROM jobs ORDER BY updated_at DESC LIMIT 50"
                    )
                    for r in cur.fetchall():
                        recent_jobs.append(SQLiteJobRecord(
                            job_id=str(r["job_id"]),
                            scope_id=str(r["scope_id"] or "default-scope"),
                            job_type=str(r["job_type"] or "job"),
                            state=str(r["state"]),
                            attempt_count=int(r["attempt_count"] or 0),
                            created_at=str(r["created_at"] or ""),
                            updated_at=str(r["updated_at"] or "")
                        ))

                # 3. Extract sealed terminal diode events
                if "hud_terminal_events" in table_names:
                    cur.execute("SELECT * FROM hud_terminal_events ORDER BY rowid DESC LIMIT 20")
                    for r in cur.fetchall():
                        terminal_events.append(dict(r))

        except Exception as exc:
            tables_summary["_error"] = str(exc)

        return SQLiteLedgerPayload(
            db_path=db_path,
            tables=tables_summary,
            jobs=recent_jobs,
            terminal_events=terminal_events,
            total_jobs=len(recent_jobs),
            mode="ro",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            trace_id=trace_id
        )

    def generate_dag_hierarchy(self, trace_id: Optional[str] = None) -> CortexHierarchyPayload:
        """
        Builds a multi-level DAG hierarchy graph from AIOS Governance -> Scopes -> SQLite Jobs -> Diodes.
        Optimized for 60fps hierarchical tree rendering in the HUD dashboard.
        """
        ledger = self.get_sqlite_ledger(trace_id=trace_id)
        jobs = ledger.jobs

        nodes: List[DAGNode] = [
            DAGNode(id="tier1-aios", name="AI OS Governance Core", type="root", layer=1, status="active"),
            DAGNode(id="tier1-ledger", name="Module 11 SQLite Ledger", type="root", layer=1, status="active"),
            DAGNode(id="tier1-hermes", name="Hermes Runtime (:8080)", type="root", layer=1, status="active")
        ]
        links: List[DAGLink] = [
            DAGLink(source="tier1-aios", target="tier1-ledger", kind="governance"),
            DAGLink(source="tier1-aios", target="tier1-hermes", kind="rpc")
        ]

        # Tier 2: Scopes
        scopes = sorted(set(j.scope_id or "default-scope" for j in jobs))
        for sc in scopes:
            sc_id = f"scope-{sc}"
            nodes.append(DAGNode(
                id=sc_id,
                name=f"Scope: {sc}",
                type="scope",
                layer=2,
                scope=sc,
                status="active"
            ))
            links.append(DAGLink(source="tier1-ledger", target=sc_id, kind="scope-cluster"))

        # Tier 3: Jobs
        for j in jobs:
            jid = j.job_id
            sc = j.scope_id or "default-scope"
            node_id = f"job-{jid}"
            nodes.append(DAGNode(
                id=node_id,
                name=f"{j.job_type}: {jid}",
                type="job",
                layer=3,
                scope=sc,
                job_id=jid,
                state=j.state,
                attempts=j.attempt_count,
                updated_at=j.updated_at
            ))
            links.append(DAGLink(source=f"scope-{sc}", target=node_id, kind="job-flow"))

        # Tier 4: Terminal Diode Events
        for ev in ledger.terminal_events[:10]:
            eid = ev.get("event_id") or f"ev-{ev.get('job_id', 'unknown')}"
            node_id = f"event-{eid}"
            nodes.append(DAGNode(
                id=node_id,
                name=f"Diode Event {eid}",
                type="diode",
                layer=4,
                status="sealed"
            ))
            parent_job = f"job-{ev.get('job_id', '')}"
            if any(n.id == parent_job for n in nodes):
                links.append(DAGLink(source=parent_job, target=node_id, kind="diode-seal"))

        layers = [
            DAGLayerInfo(layer=1, name="Governance Core", tier="Tier 1"),
            DAGLayerInfo(layer=2, name="Execution Scopes", tier="Tier 2"),
            DAGLayerInfo(layer=3, name="SQLite Jobs", tier="Tier 3"),
            DAGLayerInfo(layer=4, name="Terminal Diodes", tier="Tier 4")
        ]

        summary = HierarchySummary(
            total_nodes=len(nodes),
            total_links=len(links),
            jobs_count=len(jobs),
            scopes_count=len(scopes),
            quarantined_count=sum(1 for j in jobs if j.state == "quarantined")
        )

        return CortexHierarchyPayload(
            nodes=nodes,
            links=links,
            layers=layers,
            summary=summary,
            trace_id=trace_id
        )

    def record_streaming_point(self, credits_remaining: int, credits_consumed: int, burn_rate: float,
                               rtt_ms: float, jobs_active: int, jobs_completed: int,
                               total_probes: int) -> StreamingSeriesPoint:
        with self._lock:
            uptime = max(1.0, time.time() - self.start_time)
            throughput = round(float(total_probes) / uptime, 2)
            pt = StreamingSeriesPoint(
                ts=time.strftime("%H:%M:%S", time.gmtime()),
                time_epoch=round(time.time(), 2),
                credits_remaining=credits_remaining,
                credits_consumed=credits_consumed,
                burn_rate=burn_rate,
                rtt_ms=round(rtt_ms, 2),
                jobs_active=jobs_active,
                jobs_completed=jobs_completed,
                throughput_ops_sec=throughput
            )
            self._streaming_series.append(pt)
            return pt

    def get_streaming_series(self, trace_id: Optional[str] = None) -> StreamingSeriesResponse:
        with self._lock:
            return StreamingSeriesResponse(
                status="ok",
                series=list(self._streaming_series),
                buffer_size=len(self._streaming_series),
                window_seconds=60,
                trace_id=trace_id
            )


# --------------------------------------------------------------------------- #
# Type-Safe API Router & Microservice Communication Bus
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Deep Route Dispatch Models & Contracts
# --------------------------------------------------------------------------- #

@dataclass
class HTTPRequest:
    """
    Standard in-process representation of an incoming HTTP request.
    Decoupled from underlying network sockets to enable pure in-memory testing.
    """
    path: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    query: Dict[str, List[str]] = field(default_factory=dict)
    body: Any = None
    raw_body: bytes = b""


class HTTPResponse:
    """
    Unified response object from the deep dispatch module.
    Encapsulates status code, headers, and body payload (JSON dict, raw text, raw bytes, or stream generator).
    Transparently unpackable as a 3-tuple: payload, status_code, headers = response.
    """
    def __init__(self, status_code: int = 200, headers: Optional[Dict[str, str]] = None,
                 payload: Any = None, body: Any = None, content_type: Optional[str] = None):
        self.status_code = status_code
        self.headers: Dict[str, str] = headers.copy() if headers else {}
        self.payload = payload if payload is not None else body
        self.body = self.payload
        if content_type:
            self.headers["Content-Type"] = content_type
        elif "Content-Type" not in self.headers:
            if isinstance(self.body, (dict, list)):
                self.headers["Content-Type"] = "application/json; charset=utf-8"
            elif isinstance(self.body, str):
                self.headers["Content-Type"] = "text/html; charset=utf-8" if self.body.strip().startswith("<") else "text/plain; charset=utf-8"
            elif isinstance(self.body, bytes):
                self.headers["Content-Type"] = "application/octet-stream"

    @property
    def is_stream(self) -> bool:
        return hasattr(self.body, "__next__") and not isinstance(self.body, (bytes, str, list, dict))

    def json(self) -> Any:
        return self.payload if isinstance(self.payload, (dict, list)) else {}

    def __iter__(self):
        """Allows direct unpacking for backward-compatible tests: `payload, status, headers = response`."""
        return iter((self.payload, self.status_code, self.headers))

    def __repr__(self) -> str:
        return f"<HTTPResponse status={self.status_code} is_stream={self.is_stream}>"


class RouteDefinition:
    def __init__(self, path: str, method: str, handler: Callable,
                 request_model: Optional[Type[BaseModel]] = None,
                 response_model: Optional[Type[BaseModel]] = None,
                 service: str = "aios-hud-server",
                 is_prefix: bool = False):
        self.path = path
        self.method = method.upper()
        self.handler = handler
        self.request_model = request_model
        self.response_model = response_model
        self.service = service
        self.is_prefix = is_prefix or path.endswith("/*")


class TypeSafeRouter:
    """
    Type-safe API router and microservice communication bus.
    Validates request payload schemas with Pydantic, executes handlers inside
    Encore trace spans, and ensures verified, type-safe JSON serialization.
    """
    def __init__(self, observability: EncoreObservabilityEngine = GLOBAL_OBSERVABILITY):
        self.observability = observability
        self._routes: Dict[Tuple[str, str], RouteDefinition] = {}

    def register(self, path: str, method: str, handler: Callable,
                 request_model: Optional[Type[BaseModel]] = None,
                 response_model: Optional[Type[BaseModel]] = None,
                 service: str = "aios-hud-server",
                 is_prefix: bool = False):
        key = (path, method.upper())
        self._routes[key] = RouteDefinition(
            path=path,
            method=method,
            handler=handler,
            request_model=request_model,
            response_model=response_model,
            service=service,
            is_prefix=is_prefix
        )

    def dispatch(self, req_or_path: Union[HTTPRequest, str],
                 method: Optional[str] = None,
                 headers: Optional[Dict[str, str]] = None,
                 body: Optional[Any] = None,
                 query: Optional[Dict[str, List[str]]] = None) -> HTTPResponse:
        """
        Dispatches an HTTP request across the pure in-process seam.
        Supports both modern HTTPRequest object calls and legacy positional argument calls.
        Returns an HTTPResponse that also transparently unpacks as (payload, status_code, headers).
        """
        if isinstance(req_or_path, HTTPRequest):
            req = req_or_path
        else:
            req = HTTPRequest(
                path=req_or_path,
                method=(method or "GET").upper(),
                headers=headers or {},
                body=body,
                query=query or {}
            )

        # 0. Fast-path CORS OPTIONS preflight negotiation
        if req.method == "OPTIONS":
            cors_headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, traceparent, X-Gateway-Timestamp, X-Gateway-Nonce, X-Gateway-Signature, X-Idempotency-Key",
                "Access-Control-Max-Age": "86400"
            }
            return HTTPResponse(status_code=200, headers=cors_headers, payload={"status": "ok"})

        key = (req.path, req.method)
        route = self._routes.get(key)
        if not route:
            # Check prefix / wildcard matches
            for (p, m), r in self._routes.items():
                if m == req.method:
                    if r.is_prefix and (req.path.startswith(p[:-1]) if p.endswith("*") else req.path.startswith(p)):
                        route = r
                        break

        traceparent_raw = req.headers.get("traceparent") or req.headers.get("Traceparent")
        trace_id, parent_span_id = self.observability.parse_traceparent(traceparent_raw)

        if not route:
            with self.observability.start_span(f"HTTP {req.method} {req.path} [404]", method=req.method,
                                               trace_id=trace_id, parent_span_id=parent_span_id) as span:
                span.set_status(404)
                resp_headers = {
                    "Content-Type": "application/json; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "X-Encore-Trace-ID": span.trace_id,
                    "X-Encore-Span-ID": span.span_id,
                    "traceparent": span.traceparent
                }
                return HTTPResponse(
                    status_code=404,
                    headers=resp_headers,
                    payload={"error": f"Endpoint not found: {req.method} {req.path}", "status": "not_found"}
                )

        with self.observability.start_span(f"API {route.method} {route.path}", method=route.method,
                                           trace_id=trace_id, parent_span_id=parent_span_id) as span:
            span.add_attribute("service", route.service)
            span.add_attribute("path", req.path)

            # 1. Type-Safe Request Validation
            validated_req = None
            if route.request_model:
                try:
                    payload_to_validate = req.body if req.body is not None else {}
                    validated_req = route.request_model.model_validate(payload_to_validate)
                except ValidationError as ve:
                    span.set_status(400)
                    span.add_attribute("validation_errors", ve.errors())
                    resp_headers = {
                        "Content-Type": "application/json; charset=utf-8",
                        "Access-Control-Allow-Origin": "*",
                        "X-Encore-Trace-ID": span.trace_id,
                        "X-Encore-Span-ID": span.span_id,
                        "traceparent": span.traceparent
                    }
                    return HTTPResponse(
                        status_code=400,
                        headers=resp_headers,
                        payload={
                            "error": "Request validation failed",
                            "details": ve.errors(),
                            "status": "validation_error"
                        }
                    )

            # 2. Handler Execution with Trace Context
            try:
                kwargs: Dict[str, Any] = {
                    "trace_id": span.trace_id,
                    "span": span,
                    "request": req,
                    "path": req.path
                }
                if validated_req is not None:
                    kwargs["request_data"] = validated_req
                elif req.body is not None:
                    kwargs["body"] = req.body
                if req.query:
                    kwargs["query"] = req.query
                if req.headers:
                    kwargs["headers"] = req.headers

                sig = inspect.signature(route.handler)
                has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if not has_var_keyword:
                    call_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
                else:
                    call_kwargs = kwargs

                result = route.handler(**call_kwargs)

                # 3. Response Validation / Normalization
                if isinstance(result, HTTPResponse):
                    result.headers.setdefault("Access-Control-Allow-Origin", "*")
                    result.headers["X-Encore-Trace-ID"] = span.trace_id
                    result.headers["X-Encore-Span-ID"] = span.span_id
                    result.headers["traceparent"] = span.traceparent
                    result.headers["X-Encore-Service"] = route.service
                    span.set_status(result.status_code)
                    return result

                if route.response_model and isinstance(result, BaseModel):
                    final_payload = result.model_dump()
                elif route.response_model and isinstance(result, dict):
                    model_obj = route.response_model.model_validate(result)
                    final_payload = model_obj.model_dump()
                elif isinstance(result, BaseModel):
                    final_payload = result.model_dump()
                else:
                    final_payload = result

                span.set_status(200)
                resp_headers = {
                    "Content-Type": "application/json; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "X-Encore-Trace-ID": span.trace_id,
                    "X-Encore-Span-ID": span.span_id,
                    "traceparent": span.traceparent,
                    "X-Encore-Service": route.service
                }
                return HTTPResponse(status_code=200, headers=resp_headers, payload=final_payload)

            except Exception as exc:
                span.set_status(500)
                resp_headers = {
                    "Content-Type": "application/json; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "X-Encore-Trace-ID": span.trace_id,
                    "X-Encore-Span-ID": span.span_id,
                    "traceparent": span.traceparent
                }
                return HTTPResponse(
                    status_code=500,
                    headers=resp_headers,
                    payload={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "trace_id": span.trace_id,
                        "status": "internal_error"
                    }
                )
