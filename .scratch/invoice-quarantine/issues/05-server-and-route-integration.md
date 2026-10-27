# 05: Server & Route Integration and Full Test Verification

**What to build:** Integrate the `InvoiceQuarantine` seam into `hud_server.py`, `hud/routes/quarantine_routes.py`, and `hud/gateway.py`. Remove the ~240 lines of embedded CSV parsing and row mutation from `hud_server.py`, delegating all quarantine operations to `invoice_quarantine`. Create comprehensive unit tests in `tests/test_deep_invoice_quarantine.py` and verify all existing repository tests pass cleanly.

**Blocked by:** 03: Deterministic In-Memory Test Double (FakeInvoiceQuarantine), 04: Backward-Compatible Module Delegation & Singleton Wrappers

**Status:** ready-for-agent

- [ ] `hud_server.py` delegates `get_quarantine_data()`, `repair_quarantine_row()`, and `reset_quarantine_fixture()` to `invoice_quarantine`
- [ ] `hud/routes/quarantine_routes.py` and `hud/gateway.py` interact cleanly across the seam
- [ ] Unit test suite `tests/test_deep_invoice_quarantine.py` verifies seam, validation rules, atomic swap, and `FakeInvoiceQuarantine`
- [ ] Existing `tests/test_quarantine_recovery.py` passes 100% without modification
- [ ] Full test suite passes without regressions (`python -m pytest -q` -> 218+ passed)
