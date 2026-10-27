---
status: accepted
date: 2026-10-27
---

# Extract the Invoice Quarantine Invariant Module

We consolidate CSV fixture ingestion, financial `StrictStr` validation, duplicate detection, zero-loss invariant calculation, atomic row editing, and baseline fixture restoration behind a dedicated `InvoiceQuarantine` module in `invoice_quarantine.py`.

## Context and Decision

Previously, over 240 lines of low-level CSV file mutation, string sanitization, and accounting invariant math were embedded directly inside the HTTP server transport layer (`hud_server.py`). The HTTP handler layer directly read CSV files, maintained in-memory duplicate sets, wrote string mutations directly to disk, and duplicated filesystem sync logic across both `delivery-offline` and `hud-interface/data` directories.

This coupling caused several architectural problems:
1. **Domain Logic Leaking into HTTP Server**: The HTTP request handler was responsible for business domain rules (such as sub-penny decimal precision, negative amount stripping, and `-REC` duplicate deconfliction).
2. **Lack of Headless Testability**: Testing invoice parsing and repair required instantiating the HTTP server or monkey-patching server globals (`hud.get_adversarial_csv_path`).
3. **Atomic File Safety**: Manual CSV row edits and auto-recovery writes risk partial file truncation under concurrent access or process interruption.

We extract all invoice validation and quarantine lifecycle logic into an authoritative deep `InvoiceQuarantine` module:
1. **Dedicated Invariant Seam**: Provides a high-level 3-method seam (`inspect()`, `repair()`, `reset()`) absorbing all CSV parsing, `StrictStr` validation, and invariant calculations.
2. **Zero-Loss Accounting Invariant**: Strictly enforces the identity `received == accepted + quarantined + duplicates` across all inspections and mutations.
3. **Atomic Fixture Replacement**: Upgrades CSV writes to use temporary file generation, disk synchronization (`os.fsync`), and atomic replacement (`os.replace`), while synchronizing secondary data mirrors automatically.
4. **Dual Response Contracts**: `QuarantineInspectionSnapshot(dict)` and `QuarantineRepairResult(dict)` inherit from `dict` for 100% JSON wire compatibility with the HUD frontend, while exposing typed properties (`.metrics`, `.invariant`, `.rows`, `.quarantined_samples`, `.passed`).
5. **Deterministic In-Memory Double (`FakeInvoiceQuarantine`)**: Provides a socketless, lock-free, in-memory double with pre-seeded invoice rows and audit logging (`calls`) for testing without disk I/O.
6. **Backward-Compatible Module Wrappers**: Retains top-level module functions (`get_quarantine_data`, `repair_quarantine_row`, `reset_quarantine_fixture`) delegating to a default singleton.

## Consequences

- `hud_server.py` sheds ~240 lines of CSV manipulation, delegating entirely to `InvoiceQuarantine`.
- Route handlers in `hud/routes/quarantine_routes.py` and probes in `hud/gateway.py` interact cleanly across the seam.
- Tests can run headlessly with zero filesystem cleanup via `FakeInvoiceQuarantine` or parameterized in-memory buffers.
