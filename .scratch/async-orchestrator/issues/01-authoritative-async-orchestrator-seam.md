# 01: Authoritative Async Orchestrator Seam & Response Contracts

**What to build:** Build the core `AsyncOrchestrator` class in `async_orchestrator.py` providing the authoritative 3-method orchestration seam (`step()`, `sweep()`, `run_tick()`). The class composes `JobLedger`, `HermesAdapter`, and `EphemeralSandboxRunner` via constructor dependency injection. Implement dual-access response contracts `OrchestratorStepResult(dict)`, `OrchestratorTickSnapshot(dict)`, and `SweepResult(dict)` exposing typed properties while preserving complete dictionary compatibility for JSON serialization.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] `AsyncOrchestrator` accepts `ledger: Optional[JobLedger]`, `adapter: Optional[HermesAdapter]`, `sandbox: Optional[EphemeralSandboxRunner]`
- [x] Provides `step() -> Optional[OrchestratorStepResult]`
- [x] Provides `sweep(stalled_threshold_sec) -> List[SweepResult]`
- [x] Provides `run_tick() -> OrchestratorTickSnapshot`
- [x] `OrchestratorStepResult` inherits from `dict` with typed properties (`.task_id`, `.assigned_role`, `.from_state`, `.to_state`, `.action`, `.success`, `.error`)
- [x] `OrchestratorTickSnapshot` inherits from `dict` with typed properties (`.sweep_count`, `.stepped`, `.swept_tasks`, `.step_result`)

