# 04: Deterministic In-Memory Test Double (FakeAsyncOrchestrator)

**What to build:** Implement `FakeAsyncOrchestrator` in `async_orchestrator.py` providing an in-memory double of the identical `AsyncOrchestrator` seam. The test double accepts `FakeJobLedger` and `FakeHermesAdapter`, simulates task stepping and sweeper actions without spawning OS subprocesses or touching disk, records an audit trail in `calls`, and supports simulated operational failure via `should_fail=True`.

**Blocked by:** 01: Authoritative Async Orchestrator Seam & Response Contracts

**Status:** closed

- [x] `FakeAsyncOrchestrator` implements `step()`, `sweep()`, and `run_tick()`
- [x] Operates seamlessly with `FakeJobLedger` and `FakeHermesAdapter`
- [x] Maintains an audit trail `calls` recording all `step`, `sweep`, and `run_tick` actions
- [x] Supports simulated operational failure via `should_fail=True`
- [x] Runs with microsecond latency without disk I/O or subprocess jails
- [x] Exhibits 100% behavioral parity with `AsyncOrchestrator` on matrix state progressions and ejections
