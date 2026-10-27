---
status: accepted
date: 2026-10-27
---

# Deep Job Ledger Module & SQLite Storage Encapsulation

We consolidate SQLite database connections, Write-Ahead Logging (WAL) concurrency, state machine transitions, and metadata diode outbox persistence behind an authoritative `JobLedger` module in `job_ledger.py`.

## Context and Decision

Previously, interaction with `job_ledger.db` was fragmented across the codebase. `hud_server.py` and `hud/type_safe_router.py` opened direct `sqlite3.connect` handles, issued raw SQL queries, and duplicated fallback path resolution. Furthermore, `job_ledger.py` mutated the process working directory on import via `os.chdir()`, creating global side effects and complicating in-memory test isolation. When job transitions reached notification states, `metadata_outbox.json` was written non-atomically, posing a corruption risk for concurrent observers.

We unified all ledger data access behind a deep `JobLedger` repository interface. The module provides:
1. **Encapsulated SQLite Connection Lifecycle**: Configures Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and a 5000ms busy timeout on connection creation.
2. **Elimination of Global Side-Effects**: Removed `os.chdir()` on module import and parameterized database and outbox file paths, enabling in-memory SQLite instances (`:memory:`) and isolated testing.
3. **Atomic Diode Persistence**: Outbox notifications use atomic temporary file replacement (`os.replace` + `os.fsync`), guaranteeing observers never read partial JSON files.
4. **Dual Response Contract**: `LedgerSnapshot(dict)` provides rich property access (`.counts`, `.jobs`, `.active_count`, `.completed_count`) while preserving 100% dictionary backward compatibility for callers and serialization.
5. **Test Substitutability (`FakeJobLedger`)**: An in-memory test double provides deterministic testing without touching the disk or acquiring SQLite locks.
6. **Backward-Compatible Module Wrappers**: Preserves existing module-level function imports (`queue_job`, `claim_job`, `update_job_state`, `list_jobs`) by delegating to a shared default singleton (`get_default_ledger()`).

## Consequences

- Callers, HTTP routes (`/api/offline-ledger`, `/api/sqlite/ledger`), and visualization engines interact solely with `JobLedger` rather than opening raw SQLite connections or embedding SQL queries.
- Tests can execute completely in memory using `:memory:` or `FakeJobLedger`, eliminating disk locking and cross-test pollution.
- Working directory mutations on import are eliminated, ensuring predictable relative path handling across the process.
