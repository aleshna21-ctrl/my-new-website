# 01: Eliminate os.chdir, Parameterize Storage & Encapsulate Connection Lifecycle

**What to build:** Remove process-level `os.chdir()` on module import from `job_ledger.py`, parameterize database and outbox file paths, and encapsulate SQLite connection opening with Write-Ahead Logging (`WAL` mode) and a 5000ms busy timeout. Support pure in-memory SQLite instances (`:memory:`) without filesystem dependencies.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] Remove `os.chdir()` on module import in `job_ledger.py`
- [x] Parameterize `db_path` and `outbox_path` with environment variable overrides and sensible local defaults
- [x] Support `sqlite3.connect(":memory:")` for fast in-memory execution
- [x] Configure `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;` on file-based SQLite connections
- [x] Ensure read-only connection mode (`mode=ro`) works safely for inspection queries
