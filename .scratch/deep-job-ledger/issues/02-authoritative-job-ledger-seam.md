# 02: Authoritative JobLedger Repository Seam & LedgerSnapshot Contract

**What to build:** Build the core `JobLedger` repository class in `job_ledger.py` encapsulating state machine transitions, job creation, claiming, and aggregated snapshot queries. Return snapshots as a dual-access `LedgerSnapshot(dict)` object with typed properties. Maintain top-level module functions (`queue_job`, `claim_job`, `update_job_state`, `list_jobs`, `get_job`, `init_db`) forwarding to `get_default_ledger()` for 100% backward compatibility.

**Blocked by:** 01: Eliminate os.chdir, Parameterize Storage & Encapsulate Connection Lifecycle

**Status:** closed

- [x] `JobLedger` provides `init_db()`, `queue_job()`, `claim_job()`, `update_job_state()`, `get_job()`, `list_jobs()`, and `get_snapshot()`
- [x] State transitions enforce the strict `VALID_TRANSITIONS` lifecycle graph, failing closed on invalid state paths
- [x] `LedgerSnapshot` behaves as a dictionary (`snapshot["counts"]`, `snapshot["jobs"]`) while exposing typed properties (`.counts`, `.jobs`, `.active_count`, `.completed_count`)
- [x] Job claiming atomically claims the oldest queued job and updates state to `running`
- [x] Module-level functions (`queue_job`, `claim_job`, `update_job_state`, `list_jobs`) delegate to `get_default_ledger()`
