# Specification: Deep Job Ledger Module & SQLite Storage Encapsulation

**Status**: Ready for Agent (`ready-for-agent`)  
**Associated ADR**: [0003-deep-job-ledger-module.md](file:///c:/Users/alesh/jev-workspace/hud-interface/docs/adr/0003-deep-job-ledger-module.md)  
**Domain Glossary Reference**: [GLOSSARY.md](file:///c:/Users/alesh/jev-workspace/hud-interface/GLOSSARY.md)

---

## Problem Statement

Across the AIOS system, interactions with the Job Ledger and its underlying SQLite storage (`job_ledger.db`) were fragmented. Server request handlers and visualization engines made raw `sqlite3.connect` calls, embedded ad-hoc SQL strings, and duplicated fallback path discovery logic across multiple files.

Furthermore, importing `job_ledger.py` invoked `os.chdir()` at the module level, mutating the global process working directory on Windows and creating cross-module side effects. During job state transitions, the one-way Metadata Diode wrote notification events to `metadata_outbox.json` non-atomically, risking corrupted reads by concurrent observers. Finally, tests had to either modify filesystem files on disk or wrestle with file-locking contention.

---

## Solution

Encapsulate all database connection management, query execution, state transition graphs, and metadata diode notifications behind an authoritative, deep `JobLedger` repository module.

1. **Authoritative Repository Seam**: Consolidate table schemas, index management, state validation, and aggregated snapshot queries (`counts` and `jobs`) into a single `JobLedger` class.
2. **Concurrency & Resilience**: Configure Write-Ahead Logging (`WAL` mode) and a 5000ms busy timeout on connection creation to absorb concurrent read/write contention.
3. **No Process-Level Side Effects**: Remove `os.chdir()` on module import and parameterize storage paths (`db_path`, `outbox_path`), enabling in-memory SQLite (`:memory:`) and isolated test execution.
4. **Atomic Diode Persistence**: Transition metadata outbox writes to use temporary file generation with disk synchronization (`os.fsync`) and atomic file replacement (`os.replace`).
5. **Dual Response Contracts**: Expose `LedgerSnapshot(dict)` providing rich attribute access while preserving complete dictionary compatibility for JSON serialization.
6. **In-Memory Test Substitutability**: Provide a deterministic `FakeJobLedger` double enabling fast, socketless, lock-free testing across the system.
7. **Module-Level Backward Compatibility**: Retain top-level functions (`queue_job`, `claim_job`, `update_job_state`, `list_jobs`, `get_job`, `init_db`) forwarding to a default singleton.

---

## User Stories

1. As an operator viewing the HUD Interface, I want ledger state snapshots (`queued`, `running`, `validated`, `approved`, `completed`, `quarantined`) to be returned instantly without blocking active background workers.
2. As a concurrent dashboard client, I want database queries to utilize Write-Ahead Logging (WAL) and busy timeouts so that frequent reads never trigger `database is locked` errors.
3. As an autonomous agent, I want state machine transitions to enforce valid lifecycle paths so that invalid transitions (such as transitioning from `completed` to `running`) fail closed immediately.
4. As an autonomous agent claiming work from the inbox, I want job claiming to be atomic and transactional so that two workers never claim the same job simultaneously.
5. As an external observer monitoring job lifecycle events, I want outbox notifications from the Metadata Diode to be written atomically so that I never parse partially written or truncated JSON files.
6. As a security auditor, I want outbox events emitted through the Metadata Diode to be strictly sanitized, containing only opaque identifiers and state names with zero client, financial, or scope leakage.
7. As a developer writing tests for ledger HTTP endpoints, I want to instantiate `JobLedger` with `:memory:` so that test suites run with microsecond latency and zero filesystem cleanup.
8. As a developer testing the visualization engine, I want to substitute `FakeJobLedger` with pre-seeded job records to verify DAG generation and time-series points deterministically.
9. As a developer importing legacy ledger functions, I want `queue_job()`, `claim_job()`, and `update_job_state()` to remain operational without refactoring existing call sites.
10. As an operator inspecting system health, I want active job counts and completed job counts aggregated by the ledger module rather than calculated via ad-hoc SQL in the server loop.
11. As a system administrator deploying on Windows, I want importing the ledger module to never alter the process working directory via `os.chdir()`.
12. As an agent logging audit events, I want attempt counters and timestamps (`created_at`, `updated_at`) updated automatically on every state transition.
13. As a developer inspecting snapshots, I want `LedgerSnapshot` to support both attribute access (`snapshot.counts`) and dictionary access (`snapshot["counts"]`).
14. As an operator triggering a test cycle, I want `/api/offline-ledger/cycle` to queue, claim, validate, approve, and complete a test job transactionally.
15. As a compliance auditor, I want jobs transitioning to quarantine or review states (`[ NEEDS_REVIEW ]`) to flag `requires_review=True` in the metadata diode stream.

---

## Implementation Decisions

### 1. Authoritative Repository Seam

```python
class JobLedger:
    def __init__(self, db_path: Optional[Union[str, Path]] = None,
                 outbox_path: Optional[Union[str, Path]] = None,
                 read_only: bool = False): ...

    def init_db(self) -> None: ...
    def get_snapshot(self) -> LedgerSnapshot: ...
    def queue_job(self, job_id: str, scope_id: str, job_type: str) -> None: ...
    def claim_job(self) -> Optional[str]: ...
    def update_job_state(self, job_id: str, target_state: str) -> bool: ...
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]: ...
    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]: ...
```

### 2. SQLite Connection Configuration

- Connections are opened with a 5000ms timeout (`sqlite3.connect(..., timeout=5.0)`).
- On file-based databases, `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;` are applied upon connection.
- Read-only operations support URI mode `file:{path}?mode=ro`.

### 3. Elimination of `os.chdir()`

- Remove lines 13–17 from `job_ledger.py`.
- Resolve paths using explicit parameters with fallback resolution to environment variables (`DELIVERY_OFFLINE_DIR`, `JOB_LEDGER_DB`) and local defaults.

### 4. Atomic Outbox Persistence

- Replace direct `open(OUTBOX_FILE, "w")` with atomic swap pattern:
  `NamedTemporaryFile(dir=parent, prefix=".outbox-", suffix=".tmp")` + `fsync()` + `os.replace()`.

### 5. `LedgerSnapshot(dict)` Dual Contract

- Inherits from `dict`, containing `"counts"`, `"jobs"`, and `"timestamp_utc"`.
- Exposes typed properties: `.counts`, `.jobs`, `.active_count`, `.completed_count`, `.total_count`.

### 6. `FakeJobLedger` Test Double

- Stores jobs in an in-memory dictionary.
- Implements the exact same seam methods (`get_snapshot`, `queue_job`, `claim_job`, `update_job_state`, `list_jobs`).
- Records an audit log of all transition and queue operations.

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise external behavior across the `JobLedger` seam (`queue_job`, `claim_job`, `update_job_state`, `get_snapshot`) or HTTP routes, not private SQLite cursors.
- Tests must verify state machine validation rejects illegal transitions (e.g. `completed -> queued`).
- In-memory execution (`:memory:`) and `FakeJobLedger` must execute cleanly without filesystem side effects.

### Target Modules

- `job_ledger.py` (Seam methods, state validation, WAL configuration, atomic outbox persistence, `FakeJobLedger`).
- `hud/routes/ledger_routes.py` (Route integration for `/api/offline-ledger`, `/api/offline-ledger/cycle`, `/api/sqlite/ledger`).
- `hud_server.py` (Delegation of `get_offline_ledger_and_invariant` to `JobLedger`).

### Prior Art

- `tests/test_deep_hermes_adapter.py`: Prior art for dual response contracts, in-memory fake test doubles, and atomic file replacement.
- `tests/test_hardened_state_machine.py`: Existing state machine transition verification.

---

## Out of Scope

- Distributed consensus or multi-node clustering (Raft/Paxos). The ledger is strictly local-process and local-file based.
- Network RPC servers inside `job_ledger.py`. Network access is handled by the AIOS Gateway and HUD HTTP server.
- Modifying underlying SQLite schema tables (`jobs`, `agent_states`, `quarantine_log`) to preserve database compatibility.

---

## Further Notes

- Maintains 100% wire and caller compatibility with the frontend HUD Interface and all 211 repository tests.
- Marked with triage label `ready-for-agent`.
