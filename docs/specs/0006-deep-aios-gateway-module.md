# Specification: Deep AIOS Gateway & Two-Way Communication Seam

**Status**: Implemented (`implemented`)  
**Associated ADR**: [0006-deep-aios-gateway-module.md](file:///c:/Users/alesh/jev-workspace/hud-interface/docs/adr/0006-deep-aios-gateway-module.md)  
**Domain Glossary Reference**: [GLOSSARY.md](file:///c:/Users/alesh/jev-workspace/hud-interface/GLOSSARY.md)

---

## Problem Statement

Across the AIOS system, the communication bridge coordinating requests between the operator cockpit, autonomous Hermes agents, and scheduled cron routines currently lives in `hud/gateway.py` spanning over 1,023 lines of procedural code. 

This monolithic structure exhibits critical architectural friction:
1. **Mutable Global Singletons**: Exposes `GLOBAL_NONCE_CACHE`, `GLOBAL_SYNC_TRACKER`, `GLOBAL_FEEDBACK_LOOP`, and `GLOBAL_IDEMPOTENCY_REGISTRY` as mutable module-level state. Concurrent requests or test runs contaminate shared state, requiring manual reset workarounds in unit tests.
2. **Raw Disk I/O in Handlers**: Cron schedules and task execution logs are managed by direct file reads and writes to `data/cron_registry.json` and `data/gateway_tasks.json` with threading locks, preventing isolated in-memory testing.
3. **Unabstracted Socket Calls**: Outbound JSON-RPC requests initiate live network connections via `urllib.request` inside `send_signed_rpc`, making it impossible to test two-way communication without running live servers or monkey-patching socket libraries.
4. **Side-Effect Leakage in Command Execution**: Built-in commands such as `second_brain_scan` directly trigger external migration scripts that write files across local directories and Google Drive (`G:\My Drive\second-brain`) during automated test execution.
5. **Coupling to Dashboard Subsystems**: Methods like `hermes.board.mutate` directly import `hud/os_dashboard.py`, tightly coupling gateway communication to specific UI storage details.

---

## Solution

Extract two-way gateway coordination into an authoritative, deep `AIOSGateway` module at the workspace root (`aios_gateway.py`), accompanied by pluggable storage and transport seams, a deterministic in-memory fake (`FakeAIOSGateway`), and a backward-compatible wrapper in `hud/gateway.py`.

1. **Authoritative Gateway Seam**: Provide a consolidated 5-method lifecycle seam (`handle_inbound()`, `send_rpc()`, `crons()`, `tasks()`, `health()`) governing all two-way communication.
2. **Encapsulated Security Invariants**: Enforce HMAC-SHA256 signature verification, canonical string hashing, clock-skew bounding (`<= 300s`), and sliding-window anti-replay caching within the gateway instance.
3. **Pluggable Dual Storage Seam**: Abstract persistence behind a `GatewayStorage` interface with `DiskGatewayStorage` for production and `InMemoryGatewayStorage` for tests.
4. **Pluggable Dual Transport Seam**: Abstract network transmission behind a `GatewayTransport` interface with `UrllibTransport` for production and `InMemoryTransport` for socketless agent simulations.
5. **Pluggable Command and Method Registry**: Decouple task execution via an extensible registry (`register_command()`, `register_method()`), with safe built-in defaults (`ping`, `audit_invariants`) and zero host file mutation during tests.
6. **Dual Response Contracts**: Expose `GatewayResult(dict)`, `CronJobSnapshot(dict)`, and `TaskExecutionSnapshot(dict)` providing rich typed attribute access while preserving complete dictionary compatibility for JSON serialization and HUD routes.
7. **Deterministic In-Memory Test Double (`FakeAIOSGateway`)**: Enable socketless, diskless testing with microsecond latency, recorded calls inspection (`calls`), and fault injection (`should_fail=True`).
8. **Backward-Compatible Supervisory Wrapper**: Refactor `hud/gateway.py` to delegate all operations and legacy module functions to `AIOSGateway`.

---

## User Stories

1. As an operator sending commands from the HUD interface, I want my requests signed with HMAC-SHA256 and verified at the gateway so that unauthorized or tampered commands are rejected.
2. As a security engineer, I want duplicate nonces rejected within a sliding 600-second window so that replay attacks cannot execute duplicate actions.
3. As a security engineer, I want requests with clock skew exceeding 300 seconds rejected so that stale captured requests cannot be executed.
4. As an autonomous reasoning agent, I want to dispatch outbound JSON-RPC calls across the gateway with automatic canonical header signing so that peer services can authenticate my identity.
5. As an operator configuring automated routines, I want to list, create, update, and delete scheduled cron jobs through the gateway so that recurring tasks run on defined schedules.
6. As a cron orchestrator, I want to manually trigger a registered cron job immediately so that maintenance pulses can be executed on demand.
7. As an operator inspecting system execution history, I want the gateway to record task execution outcomes with execution duration, sequence IDs, and ACK status.
8. As an operator viewing system health, I want the gateway to track round-trip latency (RTT) and probe outcomes in a rolling feedback loop.
9. As a developer writing route unit tests, I want to instantiate `FakeAIOSGateway` with `InMemoryGatewayStorage` so that tests run with microsecond latency and zero disk writes.
10. As a developer testing agent interaction, I want `FakeAIOSGateway` to use `InMemoryTransport` with pre-configured canned responses so that outgoing RPC dispatch is tested without network sockets.
11. As a developer testing fault recovery, I want `FakeAIOSGateway` to support fault injection (`should_fail=True`) so that network and signature failure pathways are deterministically verifiable.
12. As a developer inspecting RPC outcomes, I want `GatewayResult` to support both property access (`result.status`, `result.sequence_id`) and dictionary indexing (`result["status"]`).
13. As an operator executing maintenance tasks, I want command execution isolated from host filesystem scripts so that tests never write files to external Google Drive paths.
14. As an operator submitting requests with idempotency keys, I want identical subsequent requests to return cached results so that duplicate executions are prevented.
15. As a frontend route handler in `hud/routes/gateway_routes.py`, I want to pass incoming HTTP requests across a single seam method (`handle_inbound()`) without manually orchestrating 6 separate validation steps.
16. As a telemetry monitor, I want every state mutation to advance a monotonically increasing sequence ID so that client streams can detect dropped frames or missed updates.
17. As an external service integrating with AIOS, I want mutual Bearer token authentication supported as a fallback when HMAC headers are not supplied.
18. As a legacy subsystem depending on `hud.gateway`, I want all existing function signatures (`verify_gateway_request`, `compute_signature`, `execute_gateway_rpc`) preserved so that no existing code breaks.

---

## Implementation Decisions

### 1. Authoritative Gateway Seam (`aios_gateway.py`)

The primary module exposes a clean, high-leverage interface:

```python
class AIOSGateway:
    def __init__(
        self,
        secret: str = DEFAULT_GATEWAY_SECRET,
        storage: Optional[GatewayStorage] = None,
        transport: Optional[GatewayTransport] = None,
        clock_skew_seconds: float = 300.0,
        nonce_ttl_seconds: float = 600.0,
        command_handlers: Optional[Dict[str, Callable]] = None,
        method_handlers: Optional[Dict[str, Callable]] = None,
    ):
        ...

    def handle_inbound(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        raw_body: bytes | str | None = None
    ) -> GatewayResult:
        """Single entry-point for inbound HTTP requests. Enforces auth, anti-replay, RPC routing, sequence tracking, and ACK framing."""
        ...

    def send_rpc(
        self,
        target_url: str,
        method: str,
        params: Dict[str, Any],
        timeout: float = 10.0,
        idempotency_key: Optional[str] = None
    ) -> GatewayResult:
        """Signs and dispatches an outbound JSON-RPC request via the pluggable transport seam."""
        ...

    def list_crons(self) -> List[CronJobSnapshot]: ...
    def update_cron(self, cron_id: str, updates: Dict[str, Any]) -> CronJobSnapshot: ...
    def trigger_cron(self, cron_id: str) -> GatewayResult: ...
    def delete_cron(self, cron_id: str) -> bool: ...

    def list_tasks(self, limit: int = 50) -> List[TaskExecutionSnapshot]: ...
    def record_task(self, record: Dict[str, Any]) -> TaskExecutionSnapshot: ...

    def health(self) -> Dict[str, Any]: ...
    def register_command(self, name: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]): ...
    def register_method(self, name: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]): ...
```

### 2. Dual-Access Response Contracts

Inheriting from `dict` ensures 100% JSON wire compatibility and zero breakage of existing dictionary indexing:

```python
class GatewayResult(dict):
    @property
    def status(self) -> str: return self.get("status", "ok")
    @property
    def result(self) -> Any: return self.get("result")
    @property
    def error(self) -> Optional[dict]: return self.get("error")
    @property
    def ack(self) -> Optional[dict]: return self.get("ack")
    @property
    def sequence_id(self) -> int: return self.get("sequence_id", 0)
    @property
    def authenticated(self) -> bool: return bool(self.get("authenticated", False))
```

### 3. Dual Storage Seam (`GatewayStorage`)

- `GatewayStorage` Protocol defining `load_crons()`, `save_crons()`, `load_tasks()`, `save_tasks()`.
- `DiskGatewayStorage`: Thread-safe atomic file writes with `.tmp` staging and `os.replace`.
- `InMemoryGatewayStorage`: Pure in-memory dictionaries with zero disk locks or I/O.

### 4. Dual Transport Seam (`GatewayTransport`)

- `GatewayTransport` Protocol defining `send(url: str, headers: Dict[str, str], body: bytes, timeout: float) -> Tuple[int, Dict[str, str], bytes]`.
- `UrllibTransport`: Production HTTP client using `urllib.request.build_opener(urllib.request.ProxyHandler({}))`.
- `InMemoryTransport`: Test double recording outgoing calls (`sent_requests: List`) and returning registered mock responses.

### 5. Deterministic In-Memory Double (`FakeAIOSGateway`)

Extends or wraps `AIOSGateway` initialized with `InMemoryGatewayStorage` and `InMemoryTransport`:
- Exposes `calls: List[dict]` recording all inbound and outbound dispatches.
- Exposes `should_fail: bool` and `fail_error: str` for fault injection.
- Exposes `mock_responses: Dict[str, Any]` for canned method results.

### 6. Backward-Compatible Wrapper (`hud/gateway.py`)

- Delegates to an internal default `AIOSGateway` instance.
- Retains legacy functions: `verify_gateway_request`, `compute_signature`, `execute_gateway_rpc`, `execute_task_command`, `load_cron_registry`, `update_cron_job`, `trigger_cron_job`, `delete_cron_job`, `load_task_history`, `record_task_history`, `send_signed_rpc`.
- Exposes module singletons `GLOBAL_NONCE_CACHE`, `GLOBAL_SYNC_TRACKER`, `GLOBAL_FEEDBACK_LOOP`, `GLOBAL_IDEMPOTENCY_REGISTRY` mapped to the default instance.

---

## Testing Decisions

1. **Test Highest Seam**: All tests exercise `AIOSGateway` and `FakeAIOSGateway` through `handle_inbound()` and `send_rpc()` rather than probing private internals.
2. **Socketless Testing**: Inbound tests pass synthesized request headers/bodies; outbound tests use `InMemoryTransport`. No local OS network ports are bound during testing.
3. **Zero Host Mutation**: Tests use `InMemoryGatewayStorage` so no `.json` files are created or modified on disk.
4. **Security Invariant Verification**: Verify clock skew rejection, duplicate nonce rejection within TTL, payload tampering rejection, and Bearer token fallback.
5. **Full Parity Verification**: Verify that all 18 tests in `tests/test_hermes_gateway.py` continue to pass without modification.

---

## Out of Scope

1. Replacing the frontend dashboard UI in `static/os.html` or `prototype-3-cockpit-split.html`.
2. Modifying the HMAC algorithm (HMAC-SHA256 remains the authoritative protocol standard).
3. Altering the JSON-RPC 2.0 message envelope structure.

---

## Further Notes

- Candidate 6 completes the deep extraction of all major subsystem communication seams.
- Extracted code adheres strictly to the `/codebase-design` vocabulary: `module`, `interface`, `depth`, `seam`, `adapter`, `leverage`, `locality`.
