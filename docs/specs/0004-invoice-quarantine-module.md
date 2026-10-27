# Specification: Invoice Quarantine Invariant Module

**Status**: Ready for Agent (`ready-for-agent`)  
**Associated ADR**: [0004-invoice-quarantine-module.md](file:///c:/Users/alesh/jev-workspace/hud-interface/docs/adr/0004-invoice-quarantine-module.md)  
**Domain Glossary Reference**: [GLOSSARY.md](file:///c:/Users/alesh/jev-workspace/hud-interface/GLOSSARY.md)

---

## Problem Statement

Across the AIOS system, invoice data validation, anomaly quarantine handling, and zero-loss accounting invariant mathematics were coupled directly to the HTTP transport layer in `hud_server.py`. The HTTP socket server contained over 240 lines of low-level CSV file parsing, in-memory duplicate set tracking, ad-hoc string sanitization, and manual file overwriting.

This structural leak created significant friction:
1. **Domain Logic Smear**: The HTTP server was burdened with domain-specific rules (such as string-level financial precision, sub-penny detection, negative amount stripping, and `-REC` duplicate deconfliction).
2. **Coupled Testing**: Validating invoice quarantine rules or recovery algorithms required either spinning up the full HTTP server or monkeypatching internal server globals (`hud.get_adversarial_csv_path`), making tests slow, brittle, and prone to cross-test pollution.
3. **Atomic File Safety**: Row repair and auto-recovery operations directly modified CSV fixtures on disk without atomic replacement (`tempfile` + `fsync` + `os.replace`), risking file corruption or partial reads under concurrent access.

---

## Solution

Extract all invoice parsing, financial validation, zero-loss invariant verification, and fixture repair domain logic into an authoritative, deep `InvoiceQuarantine` module.

1. **Authoritative Invariant Seam**: Provide a focused 3-method seam (`inspect()`, `repair()`, `reset()`) absorbing all CSV parsing, `StrictStr` validation, and invariant calculations.
2. **Zero-Loss Accounting Invariant**: Strictly enforce the invariant `received == accepted + quarantined + duplicates` across all inspections and state transformations.
3. **Atomic Fixture Persistence**: Transition CSV fixture mutations to use temporary file generation with disk synchronization (`os.fsync`) and atomic file replacement (`os.replace`), keeping primary and secondary filesystem mirrors (`delivery-offline` & `hud-interface/data`) synchronized.
4. **Dual Response Contracts**: Expose `QuarantineInspectionSnapshot(dict)`, `QuarantineRepairResult(dict)`, and `QuarantineResetResult(dict)` providing typed property access while preserving complete dictionary compatibility for JSON serialization.
5. **Deterministic In-Memory Test Substitutability**: Provide a deterministic `FakeInvoiceQuarantine` double enabling fast, socketless, lock-free testing without touching filesystem CSV files.
6. **Module-Level Backward Compatibility**: Retain top-level functions (`get_quarantine_data`, `repair_quarantine_row`, `reset_quarantine_fixture`, `get_adversarial_csv_path`) delegating to a default singleton.
7. **Clean Server Delegation**: Refactor `hud_server.py`, `hud/routes/quarantine_routes.py`, and `hud/gateway.py` to interact strictly across the `InvoiceQuarantine` seam.

---

## User Stories

1. As an operator viewing the HUD Interface, I want quarantine metrics (`received`, `accepted`, `quarantined`, `duplicates`) and row classifications calculated by a dedicated domain module so that the HTTP server does not perform CSV math.
2. As an operator reviewing quarantined anomalies, I want the system to flag sub-penny fractional precisions (>2 decimal places) as malformed so that precision loss does not corrupt downstream accounting.
3. As an operator inspecting raw ingest streams, I want negative amount strings flagged immediately as malformed `StrictStr` violations rather than silently converted to negative floats.
4. As an operator reviewing invoice rows, I want rows with duplicate `InvoiceID`s classified as duplicates and excluded from accepted rows so that duplicate billing cannot occur.
5. As a compliance auditor, I want the zero-loss accounting invariant formula (`received == accepted + quarantined + duplicates`) evaluated deterministically on every inspection so that invariant breaches are flagged instantly.
6. As an operator editing a malformed row in the HUD cockpit, I want to manually update `invoice_id`, `amount`, or `date` through `/api/quarantine/repair` and have the fixture re-parsed immediately.
7. As an operator fixing a single sub-penny or negative row, I want `auto_recover=True` to strip invalid negative signs and round/truncate to standard two-decimal cent precision automatically.
8. As an operator executing batch remediation, I want `auto_recover_all=True` to fix all malformed amounts and deconflict all duplicate IDs with a `-REC` suffix in a single atomic transaction.
9. As an operator testing recovery behaviors, I want `/api/quarantine/reset` to restore the adversarial CSV fixture to its pristine baseline state reliably.
10. As a developer writing route unit tests, I want to instantiate `InvoiceQuarantine` with a temporary file path so that tests run in total isolation without mutating workspace fixtures.
11. As a developer writing visualization or gateway unit tests, I want to substitute `FakeInvoiceQuarantine` with pre-seeded in-memory invoice records so that tests run without disk I/O.
12. As an autonomous agent querying invoice health via the AIOS Gateway, I want `get_quarantine_data()` to return a complete, valid payload without depending on the HTTP server being online.
13. As a developer inspecting inspection results, I want `QuarantineInspectionSnapshot` to support both attribute access (`snapshot.metrics`) and dictionary access (`snapshot["metrics"]`).
14. As a system operator running on Windows, I want fixture repairs to write via atomic replacement (`NamedTemporaryFile` + `fsync` + `os.replace`) so that concurrent file access never encounters truncated or locked files.
15. As an operator managing dual-directory deployments, I want fixture updates in `delivery-offline` to automatically synchronize to fallback mirrors (`hud-interface/data`) when present.
16. As a security auditor, I want invalid amounts containing non-numeric characters (e.g. `not_a_number`) rejected with a clear error payload (`status="error"`) without corrupting the CSV file.

---

## Implementation Decisions

### 1. Authoritative Invariant Seam

```python
class InvoiceQuarantine:
    def __init__(
        self,
        csv_path: Optional[Union[str, Path]] = None,
        backup_path: Optional[Union[str, Path]] = None,
        sync_paths: Optional[List[Union[str, Path]]] = None
    ): ...

    def inspect(self) -> QuarantineInspectionSnapshot: ...
    def repair(
        self,
        row_idx: int = 0,
        invoice_id: Optional[str] = None,
        amount: Optional[str] = None,
        date: Optional[str] = None,
        auto_recover: bool = False,
        auto_recover_all: bool = False
    ) -> QuarantineRepairResult: ...
    def reset(self) -> QuarantineResetResult: ...
```

### 2. Dual Response Contracts

- **`QuarantineInspectionSnapshot(dict)`**:
  - Keys: `"fixture"`, `"path"`, `"metrics"`, `"invariant"`, `"rows"`
  - Properties: `.metrics`, `.invariant`, `.rows`, `.quarantined_samples`, `.passed`, `.received_count`, `.accepted_count`, `.quarantined_count`, `.duplicates_count`
- **`QuarantineRepairResult(dict)`**:
  - Keys: `"status"`, `"repaired_records"`, `"metrics"`, `"invariant"`, `"quarantined_count"`, `"duplicates_count"`, `"rows"`
  - Properties: `.status`, `.repaired_records`, `.metrics`, `.invariant`, `.rows`
- **`QuarantineResetResult(dict)`**:
  - Keys: `"status"`, `"message"`, `"data"`
  - Properties: `.status`, `.message`, `.data`

### 3. StrictStr Validation & Invariant Rules

- **Invoice ID**: Must not be empty or missing.
- **Amount**: Must be non-empty, non-negative, numeric decimal with at most 2 fractional digits.
- **Duplicate Tracking**: Tracks unique invoice IDs within the file; subsequent occurrences flag as `duplicate`.
- **Zero-Loss Identity**: `received == (accepted + quarantined + duplicates)` evaluated on every parse.

### 4. Atomic Fixture Replacement & Directory Synchronization

- File writes utilize `tempfile.NamedTemporaryFile(dir=parent, prefix=".quarantine-", suffix=".tmp", delete=False)`.
- Writes are flushed and synchronized with `os.fsync(temp_file.fileno())` before closing.
- Replaced atomically using `os.replace(temp_file.name, target_path)`.
- Secondary directories (such as `data/adversarial_fixture.csv`) are synced atomically upon modification.

### 5. `FakeInvoiceQuarantine` Test Double

- In-memory implementation containing internal row dictionaries.
- Implements `inspect()`, `repair()`, and `reset()` with identical validation rules.
- Maintains an audit log `calls` tracking all operations.
- Supports fault injection via `should_fail=True`.

### 6. Backward-Compatible Module Delegation

- Top-level module functions (`get_quarantine_data`, `repair_quarantine_row`, `reset_quarantine_fixture`, `get_adversarial_csv_path`) forward to `get_default_quarantine()`.
- `hud_server.py` delegates directly to `invoice_quarantine.py`, completely removing the 240 lines of CSV parsing and row mutation from the HTTP transport server.

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise external behavior across the `InvoiceQuarantine` seam (`inspect()`, `repair()`, `reset()`) or HTTP routes, not internal CSV file cursors.
- Tests must verify rejection of malformed StrictStr amounts (negative, non-numeric, sub-penny precision).
- Tests must verify zero-loss accounting invariant evaluates `passed=True` when sums balance.
- Tests must verify `auto_recover` and `auto_recover_all` resolve all anomalies cleanly.
- Tests using `FakeInvoiceQuarantine` must run with microsecond latency without touching disk.

### Target Modules

- `invoice_quarantine.py` (Seam methods, validation logic, atomic persistence, `FakeInvoiceQuarantine`).
- `tests/test_deep_invoice_quarantine.py` (Comprehensive unit tests for the new module).
- `tests/test_quarantine_recovery.py` (Existing test suite verifying full backward compatibility).
- `hud_server.py` and `hud/routes/quarantine_routes.py` (Integration verification).

### Prior Art

- `tests/test_deep_job_ledger.py`: Prior art for repository seam, atomic file replacement, dual response contracts, and in-memory fakes.
- `tests/test_quarantine_recovery.py`: Existing regression suite for row recovery and invariant verification.

---

## Out of Scope

- Database-backed invoice ingestion (e.g. streaming CSV rows directly into SQLite `jobs`). Invoices remain in CSV fixture format.
- Interactive multi-user concurrent merge conflict resolution. The module uses atomic file replacement.
- Changing JSON response payload structures expected by the HUD frontend (`metrics`, `invariant`, `quarantined_samples`, `rows`).

---

## Further Notes

- Maintains 100% wire and caller compatibility with the frontend HUD Interface and all 218 repository tests.
- Marked with triage label `ready-for-agent`.
