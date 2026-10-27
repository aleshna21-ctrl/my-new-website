# 03: Resilient Sweeper, Crash Recovery & 3-Strike Hard Ejection

**What to build:** Implement `sweep()` and error recovery in `AsyncOrchestrator`. Automatically detect tasks stalled in `[ ACTIVE_* ]` lock states exceeding the configurable duration (`stalled_threshold_sec`), diagnose crash tracebacks from sandboxed execution or network timeouts, execute soft resets via resilience-warden (attempts 1 & 2), and escalate tasks with 3 strikes permanently to `[ NEEDS_REVIEW ]` with full diagnostic logging to `telemetry_log`.

**Blocked by:** 01: Authoritative Async Orchestrator Seam & Response Contracts

**Status:** closed

- [x] `sweep()` scans the ledger for tasks in `[ ACTIVE_* ]` states older than `stalled_threshold_sec` (default 60s)
- [x] Stalled tasks on attempts 1 & 2 soft-reset to their pending runnable state via resilience-warden
- [x] Sandboxed crash tracebacks swap assigned role to resilience-warden and increment attempt counter
- [x] 3rd failed attempt triggers hard ejection: destroys sandbox, logs diagnosis, and transitions row to `[ NEEDS_REVIEW ]`
- [x] Proactive baton pass (`NEEDS_SPECIALIST: <role>`) cleanly reassigns role and re-queues task
