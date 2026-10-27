---
status: accepted
date: 2026-10-27
---

# Deepen the Autonomous Orchestrator and Multi-Agent Execution Seam

We encapsulate multi-agent matrix scheduling, sandbox execution jail management, model prompt dispatch, stalled lock sweeping, and crash recovery behind a deep, authoritative `AsyncOrchestrator` module that composes existing `JobLedger` and `HermesAdapter` seams.

## Context and Decision

Previously, `async_orchestrator_daemon.py` spanned 2,170 lines of monolithic code coupling five distinct concerns:
1. **Raw Database Manipulation**: Directly opened raw SQLite connections (`sqlite3.connect`) and executed hand-rolled SQL statements, bypassing the encapsulated `JobLedger` repository created in ADR-0003.
2. **Raw Hermes HTTP Requests**: Executed untyped `urllib.request` loopback HTTP calls directly to port 8080, bypassing the `HermesAdapter` seam created in ADR-0002.
3. **Monolithic Procedural Complexity**: Interleaved process jail management (`EphemeralSandboxRunner`), multi-agent persona prompts, matrix transition graphs, stalled task sweeping, and CLI daemon loops in a single file.
4. **Lack of Headless / In-Memory Testability**: Testing required disk-bound SQLite databases, monkey-patching socket calls, or running heavy subprocesses, making test execution slow and brittle.

We extract autonomous orchestration into an authoritative deep `AsyncOrchestrator` module:
1. **Authoritative Orchestration Seam**: Exposes a clean 3-method lifecycle seam (`step()`, `sweep()`, `run_tick()`) driving multi-agent workflows across the Job Ledger.
2. **First-Class Seam Composition**: Interacts with persistence strictly via `JobLedger` and inference strictly via `HermesAdapter`, eliminating raw SQL strings and raw HTTP socket logic.
3. **Dual Response Contracts**: `OrchestratorStepResult(dict)` and `OrchestratorTickSnapshot(dict)` inherit from `dict` for 100% JSON wire compatibility with the HUD cockpit and telemetry pipelines, while exposing typed properties (`.task_id`, `.assigned_role`, `.from_state`, `.to_state`, `.action`, `.success`).
4. **Isolated Sandboxed Execution**: Encapsulates ephemeral sandbox runs (Docker container or subprocess jail) with bounded execution timeouts and instant tempdir cleanup.
5. **Deterministic In-Memory Test Double (`FakeAsyncOrchestrator`)**: Operates in memory over `FakeJobLedger` and `FakeHermesAdapter` with microsecond latency, audit logging (`calls`), and fault injection (`should_fail=True`).
6. **Backward-Compatible Daemon Wrappers**: Retains `AsyncOrchestratorDaemon` as a thin supervisory shell managing background worker threads, graceful signal handling, and CLI argument parsing.

## Consequences

- `async_orchestrator_daemon.py` is dramatically simplified, delegating all domain logic and state machine progression to `AsyncOrchestrator`.
- Multi-agent orchestration tests run completely in memory without disk contention, open socket ports, or leaked temporary files.
- Stalled locks and crash tracebacks are handled deterministically through formal resilience warden soft resets and 3-strike ejections.
