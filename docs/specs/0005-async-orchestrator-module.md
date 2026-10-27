# Specification: Deep Async Orchestrator Daemon & Multi-Agent Execution Seam

**Status**: Implemented (`implemented`)  
**Associated ADR**: [0005-async-orchestrator-module.md](file:///c:/Users/alesh/jev-workspace/hud-interface/docs/adr/0005-async-orchestrator-module.md)  
**Domain Glossary Reference**: [GLOSSARY.md](file:///c:/Users/alesh/jev-workspace/hud-interface/GLOSSARY.md)

---

## Problem Statement

Across the AIOS system, the asynchronous message broker and multi-agent execution pipeline in `async_orchestrator_daemon.py` spans over 2,170 lines of procedural, monolithic code. It directly performs raw SQLite connection handling and ad-hoc SQL execution on `job_ledger.db`, bypassing the deep `JobLedger` repository module extracted in ADR-0003. Furthermore, it initiates direct, unabstracted loopback HTTP socket requests to port 8080 via `urllib.request`, bypassing the unified `HermesAdapter` module extracted in ADR-0002.

This structural coupling creates severe friction:
1. **Architectural Seam Bypassing**: Two deep modules specifically built to encapsulate storage (`JobLedger`) and local model inference (`HermesAdapter`) are ignored, recreating raw SQL string formatting, schema duplication, and unvalidated network calls.
2. **Coupled Monolith**: Multi-agent persona prompts, sandboxed execution jails, matrix state machine transitions, stalled task sweeping, crash recovery, and daemon loop lifecycles are entangled in a single file without modular separation.
3. **Slow, Fragile Testing**: Validating orchestration behaviors, state transitions, or crash recoveries requires either creating filesystem SQLite databases or running complex monkeypatches on socket libraries, preventing fast, deterministic, in-memory testing.
4. **Lack of In-Memory Test Doubles**: Downstream test suites (such as HUD route dispatch and chaos suites) have no test double for the orchestrator, forcing them to mock low-level internals or run full daemon processes.

---

## Solution

Encapsulate autonomous matrix scheduling, sandbox execution jail management, prompt dispatch, stalled lock sweeping, and crash recovery behind an authoritative, deep `AsyncOrchestrator` module that composes existing `JobLedger` and `HermesAdapter` seams.

1. **Authoritative Orchestration Seam**: Expose a clean 3-method lifecycle seam (`step()`, `sweep()`, `run_tick()`) driving multi-agent workflows deterministically.
2. **First-Class Seam Composition**: Interact with persistence strictly via `JobLedger` and inference strictly via `HermesAdapter`, completely eliminating raw SQL strings and raw HTTP socket calls.
3. **Dual Response Contracts**: Expose `OrchestratorStepResult(dict)` and `OrchestratorTickSnapshot(dict)` providing rich attribute access while preserving complete dictionary compatibility for JSON serialization and HUD telemetry.
4. **Deterministic In-Memory Test Substitutability**: Provide a deterministic `FakeAsyncOrchestrator` double operating over `FakeJobLedger` and `FakeHermesAdapter`, enabling fast, socketless, lock-free testing without filesystem or subprocess overhead.
5. **Robust Matrix State Machine Progression**: Enforce strict lifecycle transitions across the Multi-Agent Matrix (Ingestion -> Extraction -> Synthesis -> Code/Content Path -> Staged Review / Done) with concurrency locking and 3-strike hard ejections.
6. **Resilient Sweeper & Recovery**: Automatically detect tasks stalled in `[ ACTIVE_* ]` locks exceeding a configurable duration, executing soft resets via resilience-warden or escalating to `[ NEEDS_REVIEW ]`.
7. **Module-Level Backward Compatibility**: Retain `AsyncOrchestratorDaemon` as a backward-compatible supervisory wrapper preserving CLI flags, background loop lifecycles, and graceful signal handling.

---

## User Stories

1. As an operator viewing the HUD Interface, I want multi-agent tasks to transition deterministically through defined matrix states so that I can inspect the progress of complex workflows in real time.
2. As an operator reviewing stalled tasks, I want tasks trapped in active locks for more than 60 seconds automatically detected and soft-reset so that agent deadlocks do not block the system.
3. As an operator inspecting task failures, I want tasks that fail three consecutive times to be permanently escalated to `[ NEEDS_REVIEW ]` with full diagnostic tracebacks logged to telemetry.
4. As an autonomous agent, I want task claims to be transactionally locked so that two concurrent workers never process the same task simultaneously.
5. As an autonomous agent requesting specialized assistance, I want to emit a proactive baton pass (`NEEDS_SPECIALIST: <role>`) that cleanly re-assigns the task role and re-queues it for the next tick.
6. As a security officer, I want sandboxed code execution isolated within an ephemeral jail (stripped environment, temporary working directory, non-interactive shell) so that generated code cannot access the host filesystem or network.
7. As a security auditor, I want sensitive deliverables to be routed strictly to offline-restricted storage rather than shared staging buffers.
8. As a developer writing route unit tests, I want to instantiate `AsyncOrchestrator` with in-memory doubles (`FakeJobLedger`, `FakeHermesAdapter`) so that unit tests execute with microsecond latency and zero disk cleanup.
9. As a developer testing edge cases, I want `FakeAsyncOrchestrator` to support fault injection (`should_fail=True`) and audit logging (`calls`) to verify error handling pathways.
10. As a developer inspecting orchestration outcomes, I want `OrchestratorStepResult` to support both property access (`result.to_state`) and dictionary indexing (`result["to_state"]`).
11. As a system administrator deploying on Windows, I want the orchestrator daemon to handle SIGINT/SIGTERM gracefully, closing active subprocesses and clearing active locks before exit.
12. As a systems architect, I want `AsyncOrchestrator` to interact with SQLite strictly through `JobLedger` rather than opening raw SQLite database connections.
13. As an inference consumer, I want `AsyncOrchestrator` to dispatch model prompts through `HermesAdapter`, inheriting bounded schema repair, fallback simulation, and usage telemetry.
14. As an operator running CLI batch jobs, I want `python async_orchestrator_daemon.py --once` to execute exactly one tick and exit with a structured JSON status report.
15. As a telemetry observer, I want every state transition, crash diagnosis, and sweeper reset logged to `telemetry_log` with high-precision ISO 8601 timestamps.
16. As a code fabricator, I want generated Python scripts wrapped in markdown code blocks to be automatically extracted and verified before execution in the sandbox.
17. As a content drafter, I want verified deliverables routed through the boundary enforcer before final dispatch to ensure formatting and domain safety rules are upheld.
18. As a compliance reviewer, I want all financial trading or market speculation directives rejected immediately at the boundary enforcement stage.

---

## Implementation Decisions

### 1. Authoritative Orchestration Seam

```python
class AsyncOrchestrator:
    def __init__(
        self,
        ledger: Optional[JobLedger] = None,
        adapter: Optional[HermesAdapter] = None,
        sandbox: Optional[EphemeralSandboxRunner] = None,
        poll_interval: float = 5.0,
        stalled_threshold_sec: float = 60.0,
        max_strikes: int = 3
    ): ...

    def step(self) -> Optional[OrchestratorStepResult]: ...
    def sweep(self, stalled_threshold_sec: Optional[float] = None) -> List[SweepResult]: ...
    def run_tick(self) -> OrchestratorTickSnapshot: ...
```

### 2. Dual Response Contracts

- **`OrchestratorStepResult(dict)`**:
  - Keys: `"task_id"`, `"scope_id"`, `"assigned_role"`, `"from_state"`, `"to_state"`, `"action"`, `"success"`, `"error"`, `"repaired"`, `"timestamp"`
  - Properties: `.task_id`, `.scope_id`, `.assigned_role`, `.from_state`, `.to_state`, `.action`, `.success`, `.error`, `.repaired`, `.timestamp`
- **`OrchestratorTickSnapshot(dict)`**:
  - Keys: `"timestamp"`, `"sweep_count"`, `"stepped"`, `"swept_tasks"`, `"step_result"`
  - Properties: `.timestamp`, `.sweep_count`, `.stepped`, `.swept_tasks`, `.step_result`
- **`SweepResult(dict)`**:
  - Keys: `"task_id"`, `"old_state"`, `"new_state"`, `"action"`, `"stalled_duration_sec"`, `"reason"`
  - Properties: `.task_id`, `.old_state`, `.new_state`, `.action`, `.stalled_duration_sec`, `.reason`

### 3. Encapsulated Seam Composition

- **Persistence**: Replaces all internal `sqlite3.connect` and `conn.execute` statements with calls to `JobLedger` methods (`claim_job()`, `update_job_state()`, `get_job()`, `list_jobs()`, `query()`).
- **Inference**: Replaces internal `urllib.request` calls with calls to `HermesAdapter.chat()` or `HermesAdapter.complete()`, leveraging the model adapter's bounded retries and schema repair.
- **Sandboxed Execution**: Preserves `EphemeralSandboxRunner` with subprocess jail and Docker container support, isolating code execution to disposable temporary directories.

### 4. Hardened Multi-Agent State Matrix

- **Ingestion Path**: `[ NEW_PAYLOAD ]` -> boundary-enforcer -> `[ PAYLOAD_CLEAN ]` -> structural-extractor -> `[ SYNTHESIS_PENDING ]`.
- **Logic Branching**: `[ SYNTHESIS_PENDING ]` -> logic-synthesizer -> branches dynamically to `[ NEEDS_CODE ]` or `[ NEEDS_CONTENT ]`.
- **Sandbox Code Path**: `[ NEEDS_CODE ]` -> systems-engineer -> `[ BLUEPRINT_READY ]` -> code-fabricator -> Ephemeral Sandbox execution -> `[ DONE ]`.
- **Content Deliverable Path**: `[ NEEDS_CONTENT ]` -> content-drafter -> `[ DRAFT_READY ]` -> boundary-enforcer -> `[ DRAFT_VERIFIED ]` -> execution-dispatcher -> `[ DONE ]`.
- **Recovery & Ejection**: Crash tracebacks swap assigned role to resilience-warden; 3 strikes permanently escalate row to `[ NEEDS_REVIEW ]`.

### 5. Deterministic In-Memory Test Double (`FakeAsyncOrchestrator`)

- An in-memory test double accepting `FakeJobLedger` and `FakeHermesAdapter`.
- Simulates step progression, prompt generation, code extraction, and sweep recovery without subprocess spawns or disk I/O.
- Records all actions in an audit list `calls` (`[{"action": "step", ...}, {"action": "sweep", ...}]`).
- Supports simulated operational failure via `should_fail=True`.

### 6. Backward-Compatible Daemon Shell

- `AsyncOrchestratorDaemon` wraps `AsyncOrchestrator`, maintaining the legacy CLI interface (`--once`, `--interval`, `--model`, `--endpoint`), threaded background worker loop, and OS signal handlers (`SIGINT`, `SIGTERM`).

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise external behavior across the `AsyncOrchestrator` seam (`step()`, `sweep()`, `run_tick()`), not internal string formatting or private helper methods.
- Tests must verify multi-agent progression from `[ NEW_PAYLOAD ]` through each matrix state to `[ DONE ]`.
- Tests must verify that reaching 3 strikes transitions the task to `[ NEEDS_REVIEW ]`.
- Tests must verify that stalled tasks exceeding the threshold are soft-reset by `sweep()`.
- Tests utilizing `FakeAsyncOrchestrator` must run with microsecond latency without disk access or process creation.

### Target Modules

- `async_orchestrator.py`: The authoritative deep orchestrator seam, response contracts, matrix transitions, and in-memory fake double.
- `async_orchestrator_daemon.py`: The backward-compatible supervisory shell and CLI runner delegating across the seam.
- `tests/test_deep_async_orchestrator.py`: Unit and integration test suite for the new module.
- `tests/test_sandboxed_durable_execution.py`, `tests/test_hardened_state_machine.py`, `tests/test_async_orchestrator_daemon.py`: Existing regression suites verifying full backward compatibility.

### Prior Art

- `tests/test_deep_job_ledger.py`: Prior art for repository seam extraction, dual response contracts, and in-memory test doubles.
- `tests/test_deep_invoice_quarantine.py`: Prior art for zero-leak atomic file safety, dual response contracts, and exact behavioral parity testing.
- `tests/test_deep_hermes_adapter.py`: Prior art for adapter seam extraction, fallback simulation, and call auditing.

---

## Out of Scope

- Migrating the underlying execution runtime from Python subprocess/Docker to remote cloud kubernetes clusters.
- Introducing external message brokers (RabbitMQ, Kafka, Redis). SQLite `job_ledger.db` remains the authoritative ledger.
- Altering the existing HOTL persona definitions or system prompt mandates.

---

## Further Notes

- Maintains 100% wire and caller compatibility with the frontend HUD Interface and all 240 repository tests.
- Marked with triage label `ready-for-agent`.
