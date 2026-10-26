# Next Cortex Dashboard Governance Rules

## 1. Local Quota & Credit Monitoring
- **Local-Only Communication**: All quota tracking, credit counters, and model rate telemetry must communicate strictly via local loopback (`http://127.0.0.1:5050` or `http://127.0.0.1:8080`) with zero external network leaks.
- **Credit Invariants**:
  - Unmetered local inference models (e.g., `qwen3:4b` via Hermes on port 8080) consume 0 cloud credits.
  - Cloud inference tokens are decremented against the rolling quota budget (default 100,000 units).
  - Quota reset countdowns must display relative remaining hours and minutes until the next replenishment window.

## 2. Automated Task & Auto-Accept Agent Policies
- **Operator Supervision**:
  - Read-only operations (`reconciliation`, `status`, `health`, `probe`) can execute automatically when `auto_accept` is enabled.
  - Destructive or write operations (`rm`, `drop`, `delete_cron`, raw ledger overwrites) require explicit operator review.
- **Deduplication**:
  - Automated tasks must attach unique idempotency keys (`X-Idempotency-Key`) to prevent double-execution under transient network buffering.

## 3. SQLite Ledger Diode Integrity
- The connected HUD interface must only query `job_ledger.db` in read-only mode (`file:job_ledger.db?mode=ro`).
- Job state transitions must respect the valid DAG:
  `queued -> running -> validated -> approved -> completed` (or `quarantined`).
