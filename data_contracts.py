from pydantic import BaseModel, Field, field_validator
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Any

class Money(BaseModel):
    amount: str  # Enforced as string to prevent floating-point precision loss
    currency: str = "USD"

    @field_validator("amount")
    @classmethod
    def val_amount(cls, v: str) -> str:
        try:
            d = Decimal(v)
            if not d.is_finite():
                raise ValueError("Amount must be a finite number.")
            return str(d)
        except InvalidOperation:
            raise ValueError(f"Invalid monetary amount string: {v}")

    def to_decimal(self) -> Decimal:
        return Decimal(self.amount)

class LaborBaseline(BaseModel):
    hours_per_run: str
    hours_basis: str
    runs_per_year: int
    loaded_hourly_cost: Optional[Money] = None
    status: str
    evidence_ids: List[str] = Field(default_factory=list)

class DerivedCosts(BaseModel):
    annual_baseline_labor_cost: Optional[Money] = None
    formula: Optional[str] = None
    calculated_by: str = "python"

class ClientRiskProfile(BaseModel):
    client_id: str
    workflow: str
    labor: LaborBaseline
    derived: DerivedCosts
    evidence: List[str] = Field(default_factory=list)
    approval_status: str = "needs_confirmation"

class FailureEvent(BaseModel):
    type: str
    description: str
    reported_events: int
    period: str
    evidence_ids: List[str] = Field(default_factory=list)


# ============================================================================ #
# Hermes <-> AIOS Gateway Data Contracts
# ============================================================================ #

class GatewayRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int
    method: str
    params: dict = Field(default_factory=dict)
    timestamp_utc: Optional[str] = None


class GatewayRPCError(BaseModel):
    code: int
    message: str
    data: Optional[dict] = None


class GatewayRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    result: Optional[Any] = None
    error: Optional[GatewayRPCError] = None
    status: str = "ok"


class TaskExecutionRecord(BaseModel):
    task_id: str
    command: str
    params: dict = Field(default_factory=dict)
    status: str
    result: dict = Field(default_factory=dict)
    error: Optional[str] = None
    executed_at: str
    duration_ms: float


class CronJobRecord(BaseModel):
    id: str
    name: str
    expression: str
    description: str = ""
    target_method: str = "hermes.task.execute"
    params: dict = Field(default_factory=dict)
    enabled: bool = True
    last_run_utc: Optional[str] = None
    last_outcome: str = "pending"
    created_at: str


class KanbanTask(BaseModel):
    id: str
    title: str
    status: str = "todo"
    priority: int = 2
    vital: bool = False
    estimate_min: int = 30
    due: str = ""
    created_at: str
    done_at: str = ""


class KanbanBoardState(BaseModel):
    revision: int
    updated_at: str
    columns: List[dict] = Field(default_factory=list)
    tasks: List[KanbanTask] = Field(default_factory=list)


class HermesTelemetryNode(BaseModel):
    id: str = "hermes"
    name: str = "Hermes Inference"
    status: str
    model: str
    upstream: str
    authenticated: bool
    last_latency_ms: Optional[float] = None


class GatewayStatusPayload(BaseModel):
    status: str = "ok"
    service: str = "aios-gateway-host"
    protocol: str = "JSON-RPC 2.0 / REST Webhook"
    auth_method: str = "HMAC-SHA256 (Anti-Replay Nonce + Timestamp)"
    hermes_online: bool
    hermes_service: str
    endpoint_hermes: str
    endpoint_aios: str
    crons_total: int
    crons_enabled: int
    tasks_executed: int
    recent_tasks: List[dict] = Field(default_factory=list)
    replay_cache_size: int
    timestamp_utc: str


# ============================================================================ #
# Real-Time Visualization Skill & SQLite Ledger Contracts
# ============================================================================ #

class StreamingSeriesPoint(BaseModel):
    ts: str
    time_epoch: float
    credits_remaining: int
    credits_consumed: int
    burn_rate: float
    rtt_ms: float
    jobs_active: int
    jobs_completed: int
    throughput_ops_sec: float


class StreamingSeriesResponse(BaseModel):
    status: str = "ok"
    series: List[StreamingSeriesPoint]
    buffer_size: int = 60
    window_seconds: int = 60
    trace_id: Optional[str] = None


class DAGNode(BaseModel):
    id: str
    name: str
    type: str
    layer: int
    status: Optional[str] = "active"
    scope: Optional[str] = None
    job_id: Optional[str] = None
    state: Optional[str] = None
    attempts: Optional[int] = 0
    updated_at: Optional[str] = ""


class DAGLink(BaseModel):
    source: str
    target: str
    kind: str = "flow"


class DAGLayerInfo(BaseModel):
    layer: int
    name: str
    tier: str


class HierarchySummary(BaseModel):
    total_nodes: int
    total_links: int
    jobs_count: int
    scopes_count: int
    quarantined_count: int = 0


class CortexHierarchyPayload(BaseModel):
    nodes: List[DAGNode]
    links: List[DAGLink]
    layers: List[DAGLayerInfo]
    summary: HierarchySummary
    trace_id: Optional[str] = None


class SQLiteTableSummary(BaseModel):
    row_count: int
    columns: Optional[List[str]] = None


class SQLiteJobRecord(BaseModel):
    job_id: str
    scope_id: Optional[str] = None
    job_type: Optional[str] = None
    state: str
    attempt_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SQLiteLedgerPayload(BaseModel):
    db_path: str
    tables: dict[str, Any]
    jobs: List[SQLiteJobRecord]
    terminal_events: List[dict] = Field(default_factory=list)
    total_jobs: int
    mode: str = "ro"
    timestamp_utc: str
    trace_id: Optional[str] = None


# ============================================================================ #
# Encore Observability & Tracing Contracts
# ============================================================================ #

class EncoreSpanRecord(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    service: str
    name: str
    method: str
    start_time: float
    duration_ms: float
    status_code: int
    attributes: dict[str, Any] = Field(default_factory=dict)


class EncoreObservabilityMetrics(BaseModel):
    service_name: str = "aios-hud-server"
    encore_framework_version: str = "1.58.8"
    uptime_seconds: float
    total_requests: int
    active_spans: int
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_count: int
    error_rate_percent: float
    recent_traces_count: int
    timestamp_utc: str


