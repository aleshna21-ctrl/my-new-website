# 04: Deterministic In-Memory Test Double (FakeJobLedger)

**What to build:** Create an in-memory test double (`FakeJobLedger`) implementing the identical `JobLedger` repository seam without touching the filesystem or creating SQLite tables. The double supports pre-seeded jobs, in-memory state transitions validating against `VALID_TRANSITIONS`, configurable error injection, and an audit trail of operations for fast, lock-free unit and route testing.

**Blocked by:** 02: Authoritative JobLedger Repository Seam & LedgerSnapshot Contract

**Status:** closed

- [x] `FakeJobLedger` implements all methods of the `JobLedger` repository seam
- [x] Supports pre-seeded jobs at initialization (`initial_jobs`)
- [x] Enforces the same `VALID_TRANSITIONS` state machine rules in memory
- [x] Maintains an audit trail `calls` recording all `queue`, `claim`, and `transition` actions
- [x] Supports simulated operational failures via `should_fail=True`
- [x] Can be substituted cleanly for `JobLedger` in route and visualization tests
