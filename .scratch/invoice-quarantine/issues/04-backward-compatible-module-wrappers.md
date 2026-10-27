# 04: Backward-Compatible Module Delegation & Singleton Wrappers

**What to build:** Implement module-level functions (`get_quarantine_data`, `repair_quarantine_row`, `reset_quarantine_fixture`, `get_adversarial_csv_path`) in `invoice_quarantine.py` forwarding to a default singleton `get_default_quarantine()`. Support dynamic monkeypatching and environment variable overrides (`INVOICE_QUARANTINE_CSV`, `DELIVERY_OFFLINE_DIR`) so that existing tests and call sites remain 100% operational without refactoring.

**Blocked by:** 02: Atomic Fixture Repair, Auto-Recovery & Baseline Reset

**Status:** ready-for-agent

- [ ] `get_default_quarantine()` provides a thread-safe singleton
- [ ] Top-level module functions (`get_quarantine_data`, `repair_quarantine_row`, `reset_quarantine_fixture`, `get_adversarial_csv_path`) delegate to `get_default_quarantine()`
- [ ] Supports `reset_default_quarantine()` for test isolation
- [ ] Existing callers can import top-level functions without code changes
