# 02: Atomic Fixture Repair, Auto-Recovery & Baseline Reset

**What to build:** Implement `repair()` and `reset()` on `InvoiceQuarantine` supporting manual operator edits, single-row sanitization (`auto_recover=True` stripping negative signs and truncating to two decimal places), and global remediation (`auto_recover_all=True` fixing amounts and deconflicting duplicate IDs via `-REC` suffix). Ensure all file mutations execute atomically via temporary file replacement (`tempfile.NamedTemporaryFile` + `fsync` + `os.replace`) and synchronize to secondary directories (`data/adversarial_fixture.csv`).

**Blocked by:** 01: Authoritative Quarantine Seam & StrictStr Invariant Inspection

**Status:** ready-for-agent

- [ ] `repair()` validates `StrictStr` format before saving manual updates
- [ ] `repair(auto_recover=True)` cleanses negative sign and sub-penny precision on target row
- [ ] `repair(auto_recover_all=True)` cleanses all amounts and appends `-REC` to duplicate `InvoiceID`s
- [ ] `reset()` restores pristine fixture from `.original` backup or default baseline
- [ ] Fixture writes use `NamedTemporaryFile`, `os.fsync`, and `os.replace` with zero leaked `.tmp` files
- [ ] Synchronizes secondary mirror paths (`hud-interface/data/adversarial_fixture.csv`) when present
