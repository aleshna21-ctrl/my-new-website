# JEV Command Center build specification

The requested four-card HUD runs on 127.0.0.1:5050 using Python's standard library HTTP server and locally served ES modules. There is no Node build or runtime download. Pydantic 2 is required only by the offline financial telemetry writer.

## Boundary and data ownership

The connected HUD never opens the financial database or imports financial workers. A separate offline observer reads SQLite in read-only mode and publishes an atomic, bounded snapshot into a configured inbox. A one-time, additive offline installation creates a transactional SQLite event table and terminal-state trigger. It does not change business state transitions. This catches completed/quarantined transitions even between polls. The offline observer does not use networking. On physically separate machines, transfer the snapshot through the approved export process; do not start the observer on the connected host.

Folder separation and this process design provide application-level separation, not an OS-enforced air gap on a shared Windows host. Exported quarantine rows and risk profiles are sensitive, local-view data. SMTP receives only opaque references and event types. Financial source files are never emailed.

The GTM module owns only staged_outreach.json decisions, protected by a shared sidecar file lock, content fingerprints, optimistic revision checks and atomic replacement. Producers must use the supplied queue writer. Existing producers ignoring the shared lock cannot be made transactional by the HUD. CRM dispatch is not implemented here; the exported approval validator is mandatory for any downstream proxy.

## Precision and honesty

Money enters Pydantic as StrictStr; calculations use Decimal constructed from strings. Decimal values serialize as strings. JSON fractional literals are read as Decimal and emitted as strings; non-finite values and duplicate keys are rejected. The browser does no financial arithmetic. Row counts serialize as strings and are checked as Python integers per batch. Missing, malformed, stale, incomplete or running reconciliation telemetry cannot produce PASS. A per-batch breach cannot be hidden by an offsetting batch. PASS is a count invariant, not proof of monetary reconciliation, crash durability, or financial correctness.

## Fault isolation and security

Every module has an independent route, renderer and non-overlapping refresh loop. Hermes is probed on a separate daemon with a 1.5-second timeout, proxy bypass and redirect refusal. The HUD route reads only cached state. Attempts are historical telemetry; simulation is prominent. Estimated input plus output tokens are never represented as measured completion usage. No inference is initiated by the HUD.

The server binds only loopback. Host allowlisting, same-origin mutation checks and a per-process anti-CSRF token protect actions. No CORS, CDN, remote fonts, HTML rendering of draft text, arbitrary file path endpoints, arbitrary SMTP recipients or dynamic financial evaluation. This is a single-user local application, not a multi-tenant authentication service.

## Notifications

An independent observer imports durable events into a HUD-owned SQLite outbox using unique IDs. A separate sender uses SMTP TLS and fixed environment-configured recipients. The first observation of an existing terminal job is explicitly labeled initial observation. Retries are bounded; uncertain sends require manual review/retry because SMTP cannot guarantee exactly-once delivery. Credentials, body text, companies, financial data and raw provider errors never appear in emails or alert logs. Polling alone cannot guarantee every transient GTM edit; the supplied queue writer records durable review events under its lock.

## Acceptance gates

1. Exact high-precision money strings survive offline validation, API JSON and browser rendering.
2. A stopped Hermes endpoint does not delay other routes; missing/malformed source affects only its panel.
3. Missing/stale/incomplete counters show UNKNOWN/STALE; actual unequal final counters show BREACH.
4. Concurrent approval with an old queue revision fails; edited content invalidates approval; all unsafe status defaults fail closed.
5. SQLite event capture survives rapid terminal-to-requeue transitions. Repeated observation and restarts do not create duplicate queued notifications.
6. SMTP failure never reports sent; ambiguous delivery becomes uncertain. Real email requires configured SMTP. No test sends real email.
7. Each mutation rejects missing CSRF and foreign origins. Frontend has no financial Number/parseFloat conversion or untrusted innerHTML.
8. Deployment writes the complete package using single-quoted PowerShell here-strings and launches without an npm toolchain.
