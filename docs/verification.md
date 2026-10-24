# Verification — 2026-10-17

## Confirmed

- 20 Python behavioral tests pass on Windows / Python 3.12.14. Tests exercise strict money strings, precision beyond JavaScript's integer range, non-finite/duplicate JSON rejection, per-batch invariants, fresh/stale/running evidence, atomic approval conflicts, producer approval stripping, durable SQLite transitions including rollback, alert restart deduplication, SMTP failure/uncertainty, metadata-only messages, corrupt-store isolation and HTTP Host/Origin/token protection.
- PowerShell parsed the complete generated installer without errors and wrote a separate test installation. The default installer then deployed the real HUD and launched it on 127.0.0.1:5050.
- Browser inspection confirmed four working panels while Hermes was unavailable, explicit SIMULATED history, UNKNOWN reconciliation, real ledger rows, two pending human reviews and an unconfigured SMTP dispatcher.
- A separate server at port 5051 used an isolated synthetic draft and missing offline source. Clicking Approve in the browser changed that fixture to approved while the missing-ledger and offline-Hermes panels remained readable. No real draft was approved or rejected.
- Quarantine disclosure expanded to show a truthful missing-export state. Browser focus no longer prevents freshness polling; open disclosures survive refreshes.
- Live read-only route checks returned in approximately 5–278 ms during the observed sample while the Hermes probe was failing separately. This is a smoke check, not a performance guarantee.
- No external email or outreach was sent. SMTP tests used mocks. No dependencies were downloaded.

## Integration facts and remaining limits

- The offline ledger now has the additive `hud_terminal_events` table and two transactional triggers. Four pre-existing completed jobs were recorded as initial observations. Business records and transition code were not edited.
- The existing harness does not persist batch counters, quarantine rows or risk-profile artifacts. Until its real finalization code calls the included offline telemetry hook, those viewers correctly show missing evidence and the invariant stays UNKNOWN. The HUD does not manufacture a successful reconciliation.
- The adapter reports estimated combined tokens and simulated history; actual completion usage remains unknown. Live model inference has not been validated by this work.
- SMTP credentials/recipient configuration is absent. Six metadata notifications are queued locally (four initial terminal observations and two review drafts). Real provider acceptance/inbox delivery remains untested.
- Existing GTM producers must adopt the shared `write_queue` function, and downstream CRM proxies must adopt `approved_drafts`, for end-to-end gate enforcement outside the HUD. Uncooperative writers or proxies cannot be secured by a dashboard alone.
- Same-host process separation is not an OS-enforced air gap. Use the separate-host export mode for that requirement.
- UI inspection used the current desktop viewport; mobile CSS is included but mobile device emulation was not executed.
