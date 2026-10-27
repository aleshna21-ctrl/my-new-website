# 02: Atomic Fixture Repair, Auto-Recovery & Baseline Reset

**What to build:** Implement `repair()` and `reset()` on `InvoiceQuarantine` supporting manual operator edits, single-row sanitization (`auto_recover=True` stripping negative signs and truncating to two decimal places), and global remediation (`auto_recover_all=True` fixing amounts and deconflicting duplicate IDs via `-REC` suffix). Ensure all file mutations execute atomically via temporary file replacement (`tempfile.NamedTemporaryFile` + `fsync` + `os.replace`) and synchronize to secondary directories (`data/adversarial_fixture.csv`).

**Blocked by:** 01: Authoritative Quarantine Seam & StrictStr Invariant Inspection

**Status:** closed

- [x] `repair()` validates `StrictStr` format before saving manual updates
- [x] `repair(auto_recover=True)` cleanses negative sign and sub-penny precision on target row
- [x] `repair(auto_recover_all=True)` cleanses all amounts and appends `-REC` to duplicate `InvoiceID`s
- [x] `reset()` restores pristine fixture from `.original` backup or default baseline
- [x] Fixture writes use `NamedTemporaryFile`, `os.fsync`, and `os.replace` with zero leaked `.tmp` files
- [x] Synchronizes secondary mirror paths (`hud-interface/data/adversarial_fixture.csv`) when present
