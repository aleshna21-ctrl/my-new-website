# 03: Atomic Metadata Diode Outbox Persistence & Sanitization

**What to build:** Upgrade the one-way Metadata Diode in `job_ledger.py` to write sanitized notification events to `metadata_outbox.json` atomically. When a job reaches a notify state (`validated`, `approved`, `completed`, `quarantined`, `[ NEEDS_REVIEW ]`), the event is generated with strict identifier sanitization, written to a temporary file in the target directory, flushed to disk via `fsync`, and replaced atomically via `os.replace`.

**Blocked by:** 02: Authoritative JobLedger Repository Seam & LedgerSnapshot Contract

**Status:** closed

- [x] `emit_sanitized_metadata_event` writes outbox events via `NamedTemporaryFile` + `fsync` + `os.replace`
- [x] Non-opaque identifiers in `job_id` or `job_type` fail closed with `ValueError`
- [x] Notification events are triggered only on transitions to designated `NOTIFY_STATES`
- [x] Parent directories for the outbox file are created on demand
- [x] Corrupted temporary files are cleaned up on write errors without partial file exposure
