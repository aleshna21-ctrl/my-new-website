# 03: Deterministic In-Memory Test Double (FakeInvoiceQuarantine)

**What to build:** Create an in-memory test double (`FakeInvoiceQuarantine`) implementing the identical `InvoiceQuarantine` seam without touching the filesystem. The double supports pre-seeded rows, evaluates `StrictStr` validation and duplicate detection in memory, supports manual edits and auto-recovery, records an audit log of operations (`calls`), and supports simulated operational failures via `should_fail=True`.

**Blocked by:** 01: Authoritative Quarantine Seam & StrictStr Invariant Inspection

**Status:** closed

- [x] `FakeInvoiceQuarantine` implements `inspect()`, `repair()`, and `reset()`
- [x] Supports pre-seeded rows at initialization (`initial_rows`)
- [x] Enforces the same `StrictStr` format and duplicate rules in memory
- [x] Maintains an audit trail `calls` recording all `inspect`, `repair`, and `reset` actions
- [x] Supports simulated operational failures via `should_fail=True`
- [x] Can be substituted cleanly for `InvoiceQuarantine` in route and visualization tests
