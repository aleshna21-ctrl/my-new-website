# 05: Server & Route Integration and Full Test Verification

**What to build:** Integrate the `JobLedger` repository seam into `hud_server.py`, `hud/routes/ledger_routes.py`, and `RealTimeVisualizationEngine`. Replace raw SQLite connections and inline queries with calls to `ledger.get_snapshot()` and `ledger.list_jobs()`. Verify that all 211 unit and integration tests pass cleanly with zero regressions.

**Blocked by:** 03: Atomic Metadata Diode Outbox Persistence & Sanitization, 04: Deterministic In-Memory Test Double (FakeJobLedger)

**Status:** closed

- [x] `hud_server.py::get_offline_ledger_and_invariant()` queries `JobLedger.get_snapshot()`
- [x] `hud/routes/ledger_routes.py` routes (`/api/offline-ledger`, `/api/offline-ledger/cycle`) interact via `JobLedger`
- [x] Raw `sqlite3.connect` and inline SQL strings are eliminated from server route handlers
- [x] Unit test suite verifies `JobLedger` seam, concurrency pragmas, atomic diode, and `FakeJobLedger`
- [x] Full repository test suite passes without regressions (`python -m pytest -q` -> 218 passed)
