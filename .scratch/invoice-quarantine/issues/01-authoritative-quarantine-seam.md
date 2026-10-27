# 01: Authoritative Quarantine Seam & StrictStr Invariant Inspection

**What to build:** Build the core `InvoiceQuarantine` class in `invoice_quarantine.py` encapsulating CSV parsing with UTF-8 BOM support (`utf-8-sig`), `StrictStr` financial validation (rejecting negative, non-numeric, or sub-penny >2 decimal precision), duplicate `InvoiceID` tracking, and zero-loss accounting invariant evaluation (`received == accepted + quarantined + duplicates`). Return inspection snapshots as a dual-access `QuarantineInspectionSnapshot(dict)` object with typed properties.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] `InvoiceQuarantine` provides `inspect() -> QuarantineInspectionSnapshot`
- [x] Enforces non-empty, non-negative numeric decimal strings with maximum 2 fractional digits
- [x] Flags missing `InvoiceID`s and duplicate `InvoiceID`s
- [x] Evaluates zero-loss invariant identity `received == accepted + quarantined + duplicates`
- [x] `QuarantineInspectionSnapshot` behaves as a dictionary (`snapshot["metrics"]`, `snapshot["invariant"]`, `snapshot["rows"]`) while exposing typed properties (`.metrics`, `.invariant`, `.rows`, `.quarantined_samples`, `.passed`)
