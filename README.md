# JEV HUD / Command Center

A local command center at **http://127.0.0.1:5050**. The HTTP server, offline observer, GTM queue and SMTP dispatcher use the Python standard library. The optional financial telemetry writer uses Pydantic 2. All frontend assets are local; no npm, CDN, analytics, remote fonts or inference calls.

## Peer review and implemented guardrails

| Risk | Guardrail |
|---|---|
| JavaScript rounds money or large values | Money enters `offline_telemetry.Money` as `StrictStr`. Python computes with `Decimal` from strings. Numeric money is rejected at the profile boundary. API money and counters remain strings; browser renderers use `textContent`, never financial arithmetic. |
| Unreachable Hermes freezes the dashboard | A separate thread probes `127.0.0.1:8080/v1/models` with a 1.5-second timeout, no environment proxies and no redirects. Each card polls independently with a 4-second browser deadline. No UI request runs inference. |
| Connected tools access offline financial source | The HUD opens only its exported inbox. A separate offline observer reads the financial DB read-only after an explicit, additive trigger installation. It imports no core workers. SMTP serializes only opaque event references and fixed state labels. |

**A same-host deployment is logical separation, not a physical or OS-enforced air gap.** A process running under the same Windows account still has that account's filesystem/network permissions. For an actual air gap, run the observer on the offline machine, transfer its snapshot through the approved export boundary and start the HUD with `-NoObserver`. Quarantine/risk detail is sensitive data deliberately exported to the local viewer; minimize or omit it where policy requires. A truly disconnected machine cannot send external SMTP itself.

## Daily walkthrough

```text
+-----------------+-------------------+------------------+------------------+
| Hermes / model  | PASS/BREACH/UNKNOWN| Ledger pulse     | Email / last sent|
+-----------------+-------------------+------------------+------------------+
| 01 Hermes + repair attempts         | 02 Ledger + quarantine              |
| Usage / 4096; live vs simulated     | Counts; rows; exact risk profiles   |
+------------------------------------+-------------------------------------+
| 03 Human review                    | 04 Email alerts                     |
| Read draft -> Approve / Reject     | Pending / sent / uncertain / test   |
+------------------------------------+-------------------------------------+
```

Check the top ribbon. Open a quarantine or risk detail when a job needs attention. Read each draft and choose Approve or Reject. Check the email panel for delivery failures. Approval records a decision; it never sends outreach. An unknown or stale invariant is not a pass.

## Deployment

Run the self-contained `deploy.ps1`. It creates and changes into `C:\Users\alesh\jev-workspace\hud-interface`, writes all source files with single-quoted here-strings, validates a Python 3.11+ executable, then launches hidden observer/server processes. It does not download dependencies. Sources from a prior deployment are backed up before replacement; state and inbox files are retained.

```powershell
& .\deploy.ps1
# Explicit interpreter, if needed:
& .\deploy.ps1 -PythonPath 'C:\path\to\python.exe'
# True separate-host workflow: transfer snapshots yourself; no core access here:
& .\deploy.ps1 -NoObserver
```

The default observer installation adds `hud_terminal_events` and two SQLite triggers to the existing offline ledger. DDL is transactional; jobs and state-transition logic are not modified. Future completed/quarantined updates are captured in their transaction. Existing terminal rows are labeled initial observations. To keep the ledger completely unchanged, use `-ReadOnlyObserver`; the UI will explicitly warn that durable transition capture is absent. A missing ledger does not prevent the server or GTM panel from starting.

The installer validates the existing core venv rather than assuming it works. This project's inspected venv points to a missing Python. It falls back to the locally bundled Python or a working PATH executable. `-NoLaunch` writes only; `-ProjectRoot` supports a separate test installation. `stop.ps1` stops only PID records whose executable arguments match this deployment; run it before redeployment or configuration changes.

## SMTP configuration

Set these in the launching PowerShell session, then start the HUD. Passwords are not written to generated files or logs. An existing running server must be restarted to inherit changes.

```powershell
$env:JEV_SMTP_HOST = 'smtp.your-provider.example'
$env:JEV_SMTP_PORT = '587'
$env:JEV_SMTP_SECURITY = 'starttls' # or ssl, usually port 465
$env:JEV_SMTP_FROM = 'alerts@your-domain.example'
$env:JEV_SMTP_TO = 'you@your-domain.example'
$env:JEV_SMTP_USER = 'your-smtp-user'
$env:JEV_SMTP_PASSWORD = 'your-app-password'
```

The UI Test button sends only to configured recipients. SMTP is disabled until configured; events wait in `state/alerts.sqlite3`. Connection/auth failures retry at most three times with increasing delay. Any failure after sending begins, partial recipient acceptance, or interrupted send becomes **uncertain**, requiring mailbox verification and manual retry. A successful SMTP acceptance is not proof of inbox delivery. Exactly-once external SMTP delivery cannot be guaranteed. Stable Message-ID values and durable deduplication reduce duplicates.

## Offline telemetry contract and integration

`offline_observer.py` expects the actual `jobs` table columns present in this project: `job_id`, `state`, `updated_at`, plus optional `job_type`, `attempt_count`, `created_at`. It exposes at most 200 recent jobs, but all-state counts cover the table. It reads the existing `inference_telemetry.json` without importing the adapter.

The existing reconciliation harness prints its counts; it does not publish counters, quarantine rows or risk profiles. The UI therefore correctly starts at **UNKNOWN** for that evidence. Use `offline_telemetry.publish_reconciliation` at the real pipeline's finalization boundary. Install/copy `offline_telemetry.py` plus `hud/__init__.py` and `hud/storage.py` into an offline-accessible helper directory, or add the trusted helper directory to the offline Python path. This hook uses no networking.

```python
from offline_telemetry import BatchCounts, publish_reconciliation

# These must be the real counters, rows and validated profile from the worker.
publish_reconciliation(
    core_directory,
    job_id,
    [BatchCounts(batch_id=batch_id, received=received, accepted=accepted,
                 quarantined=quarantined, duplicates=duplicates)],
    quarantined_rows=quarantined_rows,
    risk_profiles=client_risk_profile.model_dump(mode='json'),
)
```

This publishes `reconciliation_report.json`, `quarantined_rows.json` and `risk_profiles.json`. All profiles must already pass the project's ClientRiskProfile contract. The helper enforces strict Money strings but does not substitute a new business risk-profile schema or recalculate the existing SOW. No financial formulas run in the browser. `annual_labor_cost` illustrates exact team-total-hour arithmetic and does not assume savings or silently round currencies.

Every batch is checked separately. PASS requires a final report tied to an inspected final-state job, fresh export and fresh report. The default freshness bound is 30 seconds, configurable using `JEV_STALE_SECONDS`; an old valid report becomes STALE, not a new PASS. Row counts alone cannot prove monetary balance or true zero-loss durability. Risk/quarantine detail includes its own job ID and recorded timestamp and should be interpreted with that scope.

The current adapter publishes combined input/output estimates, not measured completion-token usage. The HUD reports measured usage as unknown / 4096 until telemetry includes `usage.completion_tokens`. Explicit simulation is marked SIMULATED. Attempt count greater than two or a retry setting other than one raises a repair-bound warning. The HUD does not enforce the core's inference/state logic; that remains the adapter/worker's responsibility.

## GTM producer and downstream proxy integration

`staged_outreach.json` is a list of draft objects. No draft ID is required for existing unique content. Supply a stable `draft_id` for otherwise identical drafts. Omitted/unknown status defaults to needs_review; needs_research cannot be approved from this screen. Edits invalidate prior approval hashes.

All producers must use `hud.gtm.write_queue(path, drafts)` rather than `Set-Content` or direct writes. This takes the same OS sidecar lock, strips producer-supplied approvals, persists review events and atomically replaces the queue. Producers ignoring the lock can still race this application; a digest check detects many but not all such races. The durable review journal uses content identity; the same unchanged draft is notified once. An interrupted producer can leave a prepared-review notification without its queue update; emails contain no draft content.

The downstream CRM proxy must use `hud.gtm.approved_drafts(path)` at dispatch time. A status string alone is insufficient. This HUD does not invoke the existing demonstration CRM module or claim that adding an interface retroactively secures other scripts that bypass its gate. Protect file permissions and route real CRM dispatch through the validator.

## Routes and fault isolation

| Route | Purpose |
|---|---|
| GET /api/hud | Independent health summaries |
| GET /api/hermes | Cached probe plus exported attempt telemetry |
| GET /api/offline-ledger | Read-only snapshot, invariant and details |
| GET/POST /api/gtm-queue | Review queue / human decision |
| GET/POST /api/alerts | Durable delivery log / test or manual retry |
| GET /api/session | Same-origin anti-CSRF token |

Each route and renderer stands alone. A malformed alert database disables only alerts until repaired and restarted. Requests bind exclusively to 127.0.0.1 and require a loopback Host. POST also requires matching Origin plus an unpredictable per-process token. This protects against remote browser-driven mutations, not other malicious local processes with the user's privileges. No arbitrary paths, recipients or SQL arrive from the browser.

Files are bounded at 16 MiB; oversized or malformed exports fail visibly. Event retention is intentionally loss-averse: journals grow until explicitly archived under an operator retention policy. Monitor the bound; no unacknowledged events are silently discarded. Local JSON replacement and file flush improve crash safety but do not claim immunity to disk failure or power loss on every filesystem.

## Run checks

```powershell
& $PythonPath -m unittest discover -s tests -v
```

Tests use temporary ledgers, drafts and fake SMTP. They never approve real drafts or send email. Browser verification should additionally exercise responsive layout and readable missing-source states. See `docs/specs/0001-command-center.md` for the acceptance gates.
#   a p l h a 2  
 