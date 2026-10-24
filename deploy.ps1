param(
    [string]$ProjectRoot = 'C:\Users\alesh\jev-workspace',
    [string]$PythonPath = '',
    [switch]$NoLaunch,
    [switch]$NoObserver,
    [switch]$ReadOnlyObserver
)
$ErrorActionPreference = 'Stop'
$deploymentRoot = Join-Path $ProjectRoot 'hud-interface'
New-Item -ItemType Directory -Force -Path $deploymentRoot | Out-Null
cd $deploymentRoot
# All source content below uses single-quoted here-strings. No variable expansion.
foreach ($name in @('server', 'observer')) {
    $pidFile = Join-Path $deploymentRoot "state\$name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -and $process.CommandLine.Contains($deploymentRoot)) {
            throw 'An existing JEV HUD process is running. Use hud-interface\stop.ps1 before redeployment.'
        }
    }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
$backupRoot = Join-Path $deploymentRoot ('backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-ffff'))
function Write-Source([string]$relativePath, [string]$content) {
    $destination = Join-Path $deploymentRoot $relativePath
    New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
    if (Test-Path -LiteralPath $destination) {
        $backup = Join-Path $backupRoot $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path $backup) | Out-Null
        Copy-Item -LiteralPath $destination -Destination $backup
    }
    [System.IO.File]::WriteAllText($destination, $content + "`n", $utf8)
}

$content = @'
__pycache__/
state/
inbox/
*.log
*.pid
*.lock
.venv/
'@
Write-Source '.gitignore' $content

$content = @'
"""Start JEV HUD. No third-party dependency is needed for the server."""
from hud.config import Config
from hud.server import Application, make_server
from hud.storage import file_lock


def main():
    config = Config.from_env()
    # Acquire before constructing AlertCenter: a second server must not alter in-flight sends.
    with file_lock(config.home / 'state' / 'server', timeout=0):
        app = Application(config)
        server = make_server(app)
        app.start()
        print(f'JEV Command Center: http://127.0.0.1:{config.port}', flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            app.stop.set()
            server.server_close()


if __name__ == '__main__':
    main()
'@
Write-Source 'app.py' $content

$content = @'
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
'@
Write-Source 'docs/specs/0001-command-center.md' $content

$content = @'
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
'@
Write-Source 'docs/verification.md' $content

$content = @'
"""JEV local command center; no source-worker imports or import-time execution."""
'@
Write-Source 'hud/__init__.py' $content

$content = @'
import hashlib
import os
import re
import smtplib
import sqlite3
import ssl
import threading
import time
import uuid
from email.message import EmailMessage

from .gtm import review_events
from .ledger import snapshot
from .storage import database, utcnow


class AlertCenter:
    def __init__(self, config, env=None):
        self.config = config
        self.env = dict(os.environ if env is None else env)
        self.path = config.home / 'state' / 'alerts.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.health_lock = threading.Lock()
        self.health = {}
        self.last_test = 0
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS alerts (
                event_id TEXT PRIMARY KEY, reference TEXT NOT NULL, kind TEXT NOT NULL,
                event_state TEXT NOT NULL, recorded_at TEXT NOT NULL,
                delivery_state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                next_try INTEGER NOT NULL DEFAULT 0, sent_at TEXT, error TEXT)''')
            # SMTP may have accepted a message before a process crash. Do not resend silently.
            db.execute("UPDATE alerts SET delivery_state='uncertain', error='Interrupted send; verify mailbox before retry' WHERE delivery_state='sending'")

    def db(self):
        return database(self.path, timeout=2)

    def smtp_settings(self):
        e = self.env
        required = ['JEV_SMTP_HOST', 'JEV_SMTP_FROM', 'JEV_SMTP_TO']
        if not all(e.get(key) for key in required):
            return None
        mode = e.get('JEV_SMTP_SECURITY', 'starttls')
        if mode not in {'starttls', 'ssl'}:
            raise ValueError('SMTP requires starttls or ssl')
        port = int(e.get('JEV_SMTP_PORT', '465' if mode == 'ssl' else '587'))
        for key in required:
            if '\r' in e[key] or '\n' in e[key]:
                raise ValueError('Invalid SMTP setting')
        return {'host': e['JEV_SMTP_HOST'], 'port': port, 'mode': mode,
                'sender': e['JEV_SMTP_FROM'], 'recipients': [s.strip() for s in e['JEV_SMTP_TO'].split(',') if s.strip()],
                'user': e.get('JEV_SMTP_USER'), 'password': e.get('JEV_SMTP_PASSWORD')}

    def enqueue(self, event):
        # Strict allowlist: never serialize the event body into an email or log.
        if event.get('state') not in {'completed', 'quarantined', 'needs_review', 'test'}:
            return
        if event.get('kind') not in {'transition', 'initial_observation', 'review', 'test'}:
            raise ValueError('Unsupported notification kind')
        ref = event.get('reference', '')
        if not isinstance(ref, str) or not re.fullmatch('[0-9a-f]{16}', ref):
            raise ValueError('Notification reference must be opaque')
        identifier = event.get('event_id')
        if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
            raise ValueError('Invalid event identity')
        with self.db() as db:
            db.execute('''INSERT OR IGNORE INTO alerts
                (event_id,reference,kind,event_state,recorded_at) VALUES (?,?,?,?,?)''',
                       (identifier, ref, event['kind'], event['state'], utcnow()))

    def observe(self):
        health = {}
        for source in ('offline', 'gtm'):
            try:
                if source == 'offline':
                    data, stale = snapshot(self.config)
                    health['offline'] = 'stale snapshot' if stale else 'ok'
                    health['event_capture'] = bool(data.get('ledger', {}).get('event_capture'))
                    events = data.get('events', [])
                else:
                    events = review_events(self.config.queue)
                    health['gtm'] = 'ok'
                for event in events:
                    self.enqueue(event)
            except Exception as exc:
                health[source] = type(exc).__name__
        with self.health_lock:
            self.health = health

    def run_observer(self, stop):
        while not stop.is_set():
            self.observe()
            stop.wait(2)

    def queue_test(self):
        with self.health_lock:
            if time.monotonic() - self.last_test < 10:
                raise ValueError('Wait ten seconds between test alerts')
            self.last_test = time.monotonic()
        identifier = uuid.uuid4().hex
        self.enqueue({'event_id': 'test:' + identifier, 'reference': identifier[:16], 'kind': 'test', 'state': 'test'})

    def retry(self, identifier):
        with self.db() as db:
            changed = db.execute("UPDATE alerts SET delivery_state='pending', attempts=0, next_try=0, error=NULL WHERE event_id=? AND delivery_state IN ('failed','uncertain')", (identifier,)).rowcount
        if not changed:
            raise ValueError('Alert is not eligible for retry')

    def send_one(self):
        settings = self.smtp_settings()
        if not settings:
            return False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM alerts WHERE delivery_state='pending' AND next_try <= ? ORDER BY recorded_at LIMIT 1", (int(time.time()),)).fetchone()
            if not row:
                return False
            db.execute("UPDATE alerts SET delivery_state='sending', attempts=attempts+1 WHERE event_id=?", (row['event_id'],))
        message = EmailMessage()
        message['From'] = settings['sender']
        message['To'] = ', '.join(settings['recipients'])
        message['Subject'] = 'JEV notification: ' + row['event_state']
        message['Message-ID'] = '<' + hashlib.sha256(row['event_id'].encode()).hexdigest() + '@jev.local>'
        message.set_content('Event: ' + row['kind'] + '\nState: ' + row['event_state'] +
                            '\nReference: ' + row['reference'] + '\nOpen the local JEV HUD to inspect.\n')
        client = None
        send_started = False
        try:
            context = ssl.create_default_context()
            if settings['mode'] == 'ssl':
                client = smtplib.SMTP_SSL(settings['host'], settings['port'], timeout=5, context=context)
            else:
                client = smtplib.SMTP(settings['host'], settings['port'], timeout=5)
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            if settings['user']:
                client.login(settings['user'], settings['password'] or '')
            send_started = True
            refused = client.send_message(message)
            if refused:
                raise RuntimeError('Partial recipient acceptance')
            with self.db() as db:
                db.execute("UPDATE alerts SET delivery_state='sent', sent_at=?, error=NULL WHERE event_id=?", (utcnow(), row['event_id']))
        except Exception as exc:
            attempts = row['attempts'] + 1
            state = 'uncertain' if send_started else ('failed' if attempts >= 3 else 'pending')
            # Exception class only; provider responses can contain addresses or secrets.
            with self.db() as db:
                db.execute('UPDATE alerts SET delivery_state=?, next_try=?, error=? WHERE event_id=?',
                           (state, int(time.time()) + 30 * attempts, type(exc).__name__, row['event_id']))
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
        return True

    def run_sender(self, stop):
        while not stop.is_set():
            try:
                self.send_one()
            except Exception as exc:
                with self.health_lock:
                    self.health['sender_error'] = type(exc).__name__
            stop.wait(2)

    def view(self):
        try:
            armed = self.smtp_settings() is not None
            error = None
        except Exception as exc:
            armed, error = False, type(exc).__name__
        with self.db() as db:
            counts = {row[0]: str(row[1]) for row in db.execute('SELECT delivery_state,count(*) FROM alerts GROUP BY delivery_state')}
            logs = [dict(row) for row in db.execute('SELECT * FROM alerts ORDER BY recorded_at DESC LIMIT 100')]
            last = db.execute("SELECT max(sent_at) FROM alerts WHERE delivery_state='sent'").fetchone()[0]
        with self.health_lock:
            health = dict(self.health)
        return {'status': 'ok', 'armed': armed, 'configuration_error': error, 'last_sent_at': last,
                'counts': counts, 'logs': logs, 'sources': health,
                'notice': 'Armed means configured, not verified delivery. SMTP may deliver duplicates after a manually retried uncertain send.'}
'@
Write-Source 'hud/alerts.py' $content

$content = @'
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path
    queue: Path
    snapshot: Path
    port: int = 5050
    stale_seconds: int = 30

    @classmethod
    def from_env(cls):
        home = Path(__file__).resolve().parent.parent
        project = Path(os.environ.get('JEV_PROJECT_ROOT', str(home.parent)))
        return cls(home, Path(os.environ.get('JEV_GTM_QUEUE', str(project / 'gtm-research' / 'staged_outreach.json'))),
                   Path(os.environ.get('JEV_SNAPSHOT', str(home / 'inbox' / 'offline_snapshot.json'))),
                   int(os.environ.get('JEV_HUD_PORT', '5050')),
                   int(os.environ.get('JEV_STALE_SECONDS', '30')))
'@
Write-Source 'hud/config.py' $content

$content = @'
import hashlib
from pathlib import Path

from .storage import atomic_json, digest, file_lock, loads, read_bytes, read_json, utcnow

DECISION_FIELDS = {'status', 'approval_hash', 'reviewed_at', 'reviewed_by'}


class Conflict(ValueError):
    pass


def content_hash(draft):
    return digest({key: value for key, value in draft.items() if key not in DECISION_FIELDS})


def effective_status(draft):
    status = draft.get('status', 'needs_review')
    if status == 'approved' and draft.get('approval_hash') != content_hash(draft):
        return 'needs_review'
    return status if status in {'needs_review', 'approved', 'rejected', 'needs_research'} else 'needs_review'


def approved_drafts(path):
    """Downstream CRM proxies MUST call this gate; approval never sends anything."""
    return [d for d in read_queue(path)[0] if effective_status(d) == 'approved']


def read_queue(path):
    raw = read_bytes(path)
    drafts = loads(raw.decode('utf-8-sig'))
    if not isinstance(drafts, list) or any(not isinstance(d, dict) for d in drafts):
        raise ValueError('Queue must be a JSON list of draft objects')
    hashes = [content_hash(d) for d in drafts]
    if len(hashes) != len(set(hashes)):
        raise ValueError('Ambiguous duplicate drafts; give each a distinct draft_id')
    return drafts, hashlib.sha256(raw).hexdigest()


def view_queue(path):
    drafts, revision = read_queue(path)
    return {'status': 'ok', 'revision': revision, 'drafts': [dict(d, id=content_hash(d),
            effective_status=effective_status(d)) for d in drafts],
            'notice': 'Approve records a human decision only. No outreach is dispatched.'}


def decide(path, identifier, revision, decision):
    if decision not in {'approved', 'rejected'}:
        raise ValueError('Decision must be approved or rejected')
    with file_lock(path):
        drafts, current = read_queue(path)
        if revision != current:
            raise Conflict('Queue changed. Reload and review the current draft.')
        matches = [d for d in drafts if content_hash(d) == identifier]
        if len(matches) != 1 or effective_status(matches[0]) != 'needs_review':
            raise Conflict('Draft is no longer awaiting review')
        draft = matches[0]
        draft.update(status=decision, reviewed_at=utcnow(), reviewed_by='local-human')
        draft['approval_hash'] = identifier if decision == 'approved' else None
        # Detect noncooperating writers when possible; all producers must use write_queue.
        if read_queue(path)[1] != current:
            raise Conflict('Another writer changed the queue')
        atomic_json(path, drafts)
    return view_queue(path)


def write_queue(path, drafts):
    """Producer API. Persist new review events before publishing the queue.

    Recovery is at-least-once: an interruption may notify about a prepared draft;
    no email contains its content. Use stable draft_id values for identical drafts.
    """
    if not isinstance(drafts, list) or any(not isinstance(d, dict) for d in drafts):
        raise ValueError('Expected a list of drafts')
    drafts = [dict(d) for d in drafts]
    if len({content_hash(d) for d in drafts}) != len(drafts):
        raise ValueError('Duplicate draft identities')
    event_path = Path(str(path) + '.events.json')
    with file_lock(path):
        old = read_queue(path)[0] if Path(path).exists() else []
        previous = {content_hash(d): effective_status(d) for d in old}
        events = read_json(event_path) if event_path.exists() else []
        if not isinstance(events, list):
            raise ValueError('Invalid review event journal')
        for draft in drafts:
            key = content_hash(draft)
            # Producers cannot create or preserve approval without the exact original decision.
            prior = next((d for d in old if content_hash(d) == key), None)
            for field in DECISION_FIELDS:
                draft.pop(field, None)
            if prior:
                draft.update({k: v for k, v in prior.items() if k in DECISION_FIELDS})
            draft['status'] = effective_status(draft)
            if draft['status'] == 'needs_review' and previous.get(key) != 'needs_review':
                events.append({'event_id': 'gtm:' + key, 'reference': key[:16], 'kind': 'review',
                               'state': 'needs_review', 'recorded_at': utcnow()})
        atomic_json(event_path, events)
        atomic_json(path, drafts)


def review_events(path):
    drafts, _ = read_queue(path)
    # Initial discovery of legacy writers is also deduplicated by content fingerprint.
    events = [{'event_id': 'gtm:' + content_hash(d), 'reference': content_hash(d)[:16], 'kind': 'review',
               'state': 'needs_review', 'recorded_at': utcnow()} for d in drafts if effective_status(d) == 'needs_review']
    journal = Path(str(path) + '.events.json')
    if journal.exists():
        durable = read_json(journal)
        if not isinstance(durable, list):
            raise ValueError('Invalid review event journal')
        events.extend(durable)
    return events
'@
Write-Source 'hud/gtm.py' $content

$content = @'
import threading
import time
import urllib.request

from .ledger import snapshot
from .storage import loads, utcnow


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Hermes redirects are refused')


class HermesProbe:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {'connected': False, 'state': 'standby', 'models': [], 'checked_at': None}

    def probe(self):
        started = time.monotonic()
        result = {'connected': False, 'state': 'standby', 'models': [], 'checked_at': utcnow()}
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open('http://127.0.0.1:8080/v1/models', timeout=1.5) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError('Model response exceeds bound')
                data = loads(raw)
            ids = [item['id'] for item in data['data'] if isinstance(item, dict) and isinstance(item.get('id'), str)]
            result.update(connected=True, state='connected', models=ids[:10])
        except Exception as exc:
            result['error'] = type(exc).__name__
        result['latency_ms'] = str(round((time.monotonic() - started) * 1000))
        with self.lock:
            self.state = result

    def run(self, stop):
        while not stop.is_set():
            self.probe()
            stop.wait(5)

    def get(self, config):
        with self.lock:
            result = dict(self.state)
        result['endpoint'] = 'http://127.0.0.1:8080/v1'
        result['max_tokens'] = 4096
        try:
            data, stale = snapshot(config)
            telemetry = data.get('hermes')
            if not isinstance(telemetry, dict):
                raise ValueError('No inference telemetry')
            attempts = telemetry.get('attempts', [])
            if not isinstance(attempts, list):
                raise ValueError('Invalid attempts list')
            result['telemetry'] = telemetry
            result['snapshot_stale'] = stale
            result['repair_bound_breach'] = len(attempts) > 2 or telemetry.get('max_retries') != 1
            result['usage_note'] = 'estimated_tokens includes prompt and output; it is not measured completion usage.'
        except Exception as exc:
            result['telemetry'] = None
            result['telemetry_error'] = type(exc).__name__
        return result
'@
Write-Source 'hud/hermes.py' $content

$content = @'
from .storage import age_seconds, read_json, validate_money_strings


def snapshot(config):
    data = read_json(config.snapshot)
    if not isinstance(data, dict) or data.get('schema_version') != '1.0':
        raise ValueError('Unsupported offline snapshot')
    age = age_seconds(data['exported_at'])
    if age < -5:
        raise ValueError('Snapshot timestamp is in the future')
    return data, age > config.stale_seconds


def evaluate_report(report):
    if not isinstance(report, dict) or report.get('final') is not True:
        return {'status': 'UNKNOWN', 'reason': 'No final reconciliation report'}
    batches = report.get('batches')
    if not isinstance(batches, list) or not batches:
        return {'status': 'UNKNOWN', 'reason': 'No batch counters'}
    totals = {key: 0 for key in ('received', 'accepted', 'quarantined', 'duplicates')}
    failures = []
    ids = set()
    for batch in batches:
        if not isinstance(batch, dict) or not isinstance(batch.get('batch_id'), str) or batch['batch_id'] in ids:
            raise ValueError('Batch IDs must be present and unique')
        ids.add(batch['batch_id'])
        for key in totals:
            value = batch.get(key)
            if type(value) is not int or value < 0:
                raise ValueError('Counters must be non-negative Python integers')
            totals[key] += value
        if batch['received'] != batch['accepted'] + batch['quarantined'] + batch['duplicates']:
            failures.append(batch['batch_id'])
    return {'status': 'BREACH' if failures else 'PASS',
            'reason': 'Final reported batches; count invariant only',
            'totals': {k: str(v) for k, v in totals.items()}, 'failed_batches': failures,
            'recorded_at': report.get('recorded_at'), 'job_id': report.get('job_id')}


def get_ledger(config):
    data, stale = snapshot(config)
    section = data.get('ledger', {})
    if section.get('status') != 'ok':
        raise ValueError(section.get('error', 'Ledger unavailable'))
    invariant = evaluate_report(data.get('reconciliation'))
    if invariant['status'] == 'PASS':
        try:
            report_age = age_seconds(invariant['recorded_at'])
            if report_age < -5:
                raise ValueError('Future report')
            if stale or report_age > config.stale_seconds:
                invariant['status'] = 'STALE'
        except (TypeError, ValueError, KeyError):
            invariant.update(status='UNKNOWN', reason='Report timestamp is missing or invalid')
        matching = [j for j in section.get('jobs', []) if j.get('job_id') == invariant.get('job_id')]
        if not matching or matching[0].get('state') not in {'validated', 'completed', 'quarantined'}:
            invariant.update(status='UNKNOWN', reason='Report is not linked to a final inspected job')
    try:
        validate_money_strings(data.get('risk_profiles'))
    except (ValueError, ArithmeticError):
        data['risk_profiles'] = None
        data.setdefault('errors', {})['risk_profiles'] = 'Invalid financial amount; string required'
    return {'status': 'stale' if stale else 'ok', 'exported_at': data['exported_at'],
            'jobs': section.get('jobs', []), 'counts': section.get('counts', {}),
            'invariant': invariant, 'quarantine': data.get('quarantine'),
            'risk_profiles': data.get('risk_profiles'), 'source_errors': data.get('errors', {}),
            'event_capture': section.get('event_capture', False),
            'notice': 'Read-only exported snapshot. No financial worker is executed by the HUD.'}
'@
Write-Source 'hud/ledger.py' $content

$content = @'
import hmac
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .alerts import AlertCenter
from .gtm import Conflict, decide, view_queue
from .hermes import HermesProbe
from .ledger import get_ledger
from .storage import dumps, loads


def isolated(function):
    try:
        return function()
    except Exception as exc:
        return {'status': 'unavailable', 'error': type(exc).__name__, 'message': 'Source missing, busy or invalid. Other panels remain independent.'}


class Application:
    def __init__(self, config):
        self.config = config
        self.token = secrets.token_urlsafe(32)
        self.probe = HermesProbe()
        try:
            self.alerts = AlertCenter(config)
        except Exception:
            self.alerts = None
        self.stop = threading.Event()
        self.threads = []

    def start(self):
        targets = [self.probe.run]
        if self.alerts:
            targets.extend((self.alerts.run_observer, self.alerts.run_sender))
        for target in targets:
            thread = threading.Thread(target=target, args=(self.stop,), daemon=True)
            thread.start()
            self.threads.append(thread)

    def get(self, route):
        handlers = {'/api/hermes': lambda: self.probe.get(self.config),
                    '/api/offline-ledger': lambda: get_ledger(self.config),
                    '/api/gtm-queue': lambda: view_queue(self.config.queue),
                    '/api/alerts': lambda: self.alerts.view() if self.alerts else {'status': 'unavailable', 'error': 'AlertStoreUnavailable'}}
        if route == '/api/session':
            return {'token': self.token}
        if route == '/api/hud':
            ledger = isolated(handlers['/api/offline-ledger'])
            hermes = isolated(handlers['/api/hermes'])
            alerts = isolated(handlers['/api/alerts'])
            return {'hermes': hermes, 'ledger': ledger, 'alerts': alerts}
        if route not in handlers:
            raise KeyError(route)
        return isolated(handlers[route])

    def post(self, route, payload):
        if route == '/api/gtm-queue':
            if set(payload) != {'id', 'revision', 'decision'} or any(type(v) is not str for v in payload.values()):
                raise ValueError('Expected id, revision and decision strings')
            return decide(self.config.queue, payload['id'], payload['revision'], payload['decision'])
        if route == '/api/alerts':
            if not self.alerts:
                raise ValueError('Alert store unavailable; other modules remain usable')
            if payload == {'action': 'test'}:
                self.alerts.queue_test()
            elif set(payload) == {'action', 'event_id'} and payload['action'] == 'retry' and type(payload['event_id']) is str:
                self.alerts.retry(payload['event_id'])
            else:
                raise ValueError('Unsupported alert action')
            return self.alerts.view()
        raise KeyError(route)


def make_server(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'JEV-HUD'

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            # Request bodies, query strings and source data never enter logs.
            pass

        def safe_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{app.config.port}', f'localhost:{app.config.port}'}

        def respond(self, status, body, content_type='application/json; charset=utf-8'):
            raw = body if isinstance(body, bytes) else dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.safe_host():
                return self.respond(403, {'error': 'Loopback host required'})
            route = urlsplit(self.path).path
            try:
                if route.startswith('/api/'):
                    return self.respond(200, app.get(route))
                route = '/static/index.html' if route == '/' else route
                if not route.startswith('/static/'):
                    raise KeyError(route)
                root = (app.config.home / 'static').resolve()
                path = (app.config.home / route.lstrip('/')).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise KeyError(route)
                content_type = 'text/javascript' if path.suffix == '.js' else (mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
                return self.respond(200, path.read_bytes(), content_type + '; charset=utf-8')
            except KeyError:
                self.respond(404, {'error': 'Not found'})
            except Exception as exc:
                self.respond(503, {'error': type(exc).__name__})

        def do_POST(self):
            if not self.safe_host():
                return self.respond(403, {'error': 'Loopback host required'})
            origin = self.headers.get('Origin')
            if origin != 'http://' + self.headers['Host'] or not hmac.compare_digest(self.headers.get('X-HUD-Token', ''), app.token):
                return self.respond(403, {'error': 'Same-origin human-review session required'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or self.headers.get('Transfer-Encoding'):
                return self.respond(415, {'error': 'Bounded JSON request required'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid body length')
                payload = loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('Expected a JSON object')
                return self.respond(200, app.post(urlsplit(self.path).path, payload))
            except Conflict as exc:
                self.respond(409, {'error': str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except KeyError:
                self.respond(404, {'error': 'Not found'})
            except Exception as exc:
                self.respond(503, {'error': type(exc).__name__})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False

    return Server(('127.0.0.1', app.config.port), Handler)
'@
Write-Source 'hud/server.py' $content

$content = @'
import contextlib
import hashlib
import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024


@contextlib.contextmanager
def database(path, **kwargs):
    connection = sqlite3.connect(path, **kwargs)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def age_seconds(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def no_constant(value):
    raise ValueError('Non-finite JSON number')


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, parse_float=Decimal, parse_constant=no_constant,
                      object_pairs_hook=unique_keys)


def safe_value(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('Non-finite decimal')
        return str(value)
    if isinstance(value, float):
        raise TypeError('Binary floating-point values are prohibited in payloads')
    if isinstance(value, dict):
        return {str(k): safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    return value


def validate_money_strings(value):
    """Reject numeric money at the exported-profile boundary, before serialization."""
    if isinstance(value, dict):
        if 'amount' in value:
            if type(value['amount']) is not str:
                raise ValueError('Financial amount must enter as a string')
            number = Decimal(value['amount'])
            if not number.is_finite():
                raise ValueError('Financial amount must be finite')
        for child in value.values():
            validate_money_strings(child)
    elif isinstance(value, list):
        for child in value:
            validate_money_strings(child)


def dumps(value):
    return json.dumps(safe_value(value), ensure_ascii=False, allow_nan=False, indent=2)


def read_bytes(path, limit=MAX_BYTES):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('File exceeds configured limit')
    return raw


def read_json(path):
    return loads(read_bytes(path).decode('utf-8-sig'))


def digest(value):
    raw = json.dumps(safe_value(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = dumps(value).encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('Snapshot exceeds configured limit')
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def file_lock(path, timeout=3):
    """All writers must use the same persistent sidecar lock file."""
    path = Path(str(path) + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('File writer busy')
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
'@
Write-Source 'hud/storage.py' $content

$content = @'
"""Run in the offline context. No network calls and no worker imports."""
import argparse
from contextlib import contextmanager
import hashlib
import sqlite3
import time
from pathlib import Path

from hud.storage import atomic_json, database, read_json, utcnow


@contextmanager
def connect_readonly(path):
    with database(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=1) as connection:
        connection.execute('PRAGMA query_only=ON')
        yield connection


def install_event_capture(path):
    """Additive DDL only, executed separately in the offline context."""
    if not Path(path).is_file():
        raise FileNotFoundError('Financial ledger must already exist')
    with database(path, timeout=5) as db:
        db.execute('BEGIN IMMEDIATE')
        columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
        if not {'job_id', 'state'}.issubset(columns):
            raise ValueError('Expected jobs(job_id, state) ledger contract')
        first_install = not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hud_terminal_events'").fetchone()
        db.execute('''CREATE TABLE IF NOT EXISTS hud_terminal_events (
            event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, state TEXT NOT NULL,
            recorded_at TEXT NOT NULL, kind TEXT NOT NULL)''')
        db.execute('''CREATE TRIGGER IF NOT EXISTS hud_terminal_update_v1
            AFTER UPDATE OF state ON jobs
            WHEN OLD.state <> NEW.state AND NEW.state IN ('completed','quarantined')
            BEGIN
              INSERT INTO hud_terminal_events VALUES (
                lower(hex(randomblob(16))), NEW.job_id, NEW.state,
                strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'transition');
            END''')
        db.execute('''CREATE TRIGGER IF NOT EXISTS hud_terminal_insert_v1
            AFTER INSERT ON jobs WHEN NEW.state IN ('completed','quarantined')
            BEGIN
              INSERT INTO hud_terminal_events VALUES (
                lower(hex(randomblob(16))), NEW.job_id, NEW.state,
                strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'initial_observation');
            END''')
        # INSERT OR IGNORE makes bootstrap idempotent without claiming a historical transition.
        if first_install:
            db.execute('''INSERT OR IGNORE INTO hud_terminal_events
                SELECT 'initial:' || job_id, job_id, state,
                strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'initial_observation'
                FROM jobs WHERE state IN ('completed','quarantined')''')


def export_once(core, destination):
    core, destination = Path(core), Path(destination)
    result = {'schema_version': '1.0', 'exported_at': utcnow(), 'errors': {}}
    try:
        with connect_readonly(core / 'job_ledger.db') as db:
            db.execute('BEGIN')
            rows = [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY updated_at DESC LIMIT 200')]
            counts = {row[0]: str(row[1]) for row in db.execute('SELECT state, count(*) FROM jobs GROUP BY state')}
            capture = db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name IN ('hud_terminal_update_v1','hud_terminal_insert_v1')").fetchone()[0] == 2
            events = [dict(row) for row in db.execute('SELECT * FROM hud_terminal_events ORDER BY recorded_at')] if capture else []
        # No scope IDs or arbitrary database columns cross this export boundary.
        jobs = [{key: str(row[key]) if row[key] is not None else None for key in
                 ('job_id', 'job_type', 'state', 'attempt_count', 'created_at', 'updated_at') if key in row} for row in rows]
        result['ledger'] = {'status': 'ok', 'jobs': jobs, 'counts': counts, 'event_capture': capture}
        result['events'] = [{'event_id': 'offline:' + row['event_id'],
                             'reference': hashlib.sha256(row['job_id'].encode()).hexdigest()[:16],
                             'kind': row['kind'], 'state': row['state'], 'recorded_at': row['recorded_at']}
                            for row in events]
    except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
        result['ledger'] = {'status': 'unavailable', 'error': type(exc).__name__}
        result['events'] = []
    for key, filename in [('hermes', 'inference_telemetry.json'), ('reconciliation', 'reconciliation_report.json'),
                          ('quarantine', 'quarantined_rows.json'), ('risk_profiles', 'risk_profiles.json')]:
        try:
            result[key] = read_json(core / filename)
        except (OSError, ValueError, TypeError) as exc:
            result[key] = None
            result['errors'][key] = type(exc).__name__
    atomic_json(destination, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--install-events', action='store_true', help='Add transactional event table/triggers to existing ledger')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.install_events:
        install_event_capture(args.core / 'job_ledger.db')
    while True:
        try:
            export_once(args.core, args.output)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            print('Offline snapshot export failed:', type(exc).__name__, flush=True)
            if not args.watch:
                raise
        if not args.watch:
            break
        time.sleep(2)


if __name__ == '__main__':
    main()
'@
Write-Source 'offline_observer.py' $content

$content = @'
"""Financial-worker hook. No networking. Call only after the batch is finalized."""
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, field_validator

from hud.storage import atomic_json, file_lock, utcnow, validate_money_strings


class Money(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    amount: StrictStr
    currency: StrictStr = 'USD'

    @field_validator('amount')
    @classmethod
    def exact_amount(cls, value):
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError('Money must be finite')
        return value

    @field_validator('currency')
    @classmethod
    def currency_code(cls, value):
        if len(value) != 3 or not value.isascii() or not value.isalpha() or value != value.upper():
            raise ValueError('Use a three-letter uppercase currency')
        return value


class BatchCounts(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    batch_id: StrictStr
    received: StrictInt
    accepted: StrictInt
    quarantined: StrictInt
    duplicates: StrictInt

    @field_validator('received', 'accepted', 'quarantined', 'duplicates')
    @classmethod
    def nonnegative(cls, value):
        if value < 0:
            raise ValueError('Negative counter')
        return value


def annual_labor_cost(hours_per_run: str, runs_per_year: int, rate: Money) -> Money:
    """Team-total hours only. No rounding policy is silently imposed."""
    if type(hours_per_run) is not str or type(runs_per_year) is not int or runs_per_year < 0:
        raise ValueError('Hours must be a decimal string; runs a nonnegative integer')
    hours = Decimal(hours_per_run)
    if not hours.is_finite() or hours < 0 or Decimal(rate.amount) < 0:
        raise ValueError('Non-finite/negative labor inputs')
    with localcontext() as ctx:
        ctx.prec = max(50, len(hours_per_run) + len(rate.amount) + len(str(runs_per_year)) + 10)
        amount = hours * Decimal(str(runs_per_year)) * Decimal(rate.amount)
    return Money(amount=format(amount, 'f'), currency=rate.currency)


def publish_reconciliation(core, job_id: str, batches: list[BatchCounts], quarantined_rows=None, risk_profiles=None):
    """Persist actual caller-supplied measurements. Does not infer or fabricate them.

    The invariant is checked by the HUD so BREACH evidence can also be recorded.
    Pass already validated ClientRiskProfile.model_dump(mode='json') objects.
    """
    if type(job_id) is not str or not batches or not all(isinstance(b, BatchCounts) for b in batches):
        raise ValueError('A job ID and validated batch counters are required')
    if len({b.batch_id for b in batches}) != len(batches):
        raise ValueError('Duplicate batch IDs')
    core = Path(core)
    validate_money_strings(risk_profiles)
    report = {'final': True, 'job_id': job_id, 'recorded_at': utcnow(), 'batches': [b.model_dump() for b in batches]}
    with file_lock(core / 'reconciliation_report.json'):
        # Separate detail files are tagged so the viewer can identify their job/version.
        for filename, payload in [('quarantined_rows.json', quarantined_rows), ('risk_profiles.json', risk_profiles)]:
            atomic_json(core / filename, {'job_id': job_id, 'recorded_at': report['recorded_at'], 'data': payload})
        atomic_json(core / 'reconciliation_report.json', report)
'@
Write-Source 'offline_telemetry.py' $content

$content = @'
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
'@
Write-Source 'README.md' $content

$content = @'
# Only offline_telemetry.py requires this package; the HUD and observer are stdlib.
pydantic>=2.10,<3
'@
Write-Source 'requirements-offline.txt' $content

$content = @'
// Independent imports: a failed renderer does not prevent sibling modules from starting.
for (const name of ['hud','hermes','ledger','gtm','alerts']) {
  import(`/static/modules/${name}.js`).then(module=>module.start()).catch(error=>{
    const target=document.getElementById(name); if(target)target.textContent=`Renderer unavailable: ${error.message}`;
  });
}
'@
Write-Source 'static/app.js' $content

$content = @'
export const el = (tag, text, cls) => {const node = document.createElement(tag); if (text !== undefined) node.textContent = String(text); if (cls) node.className = cls; return node;};
export function details(label, value) {const node=el('details'); node.append(el('summary',label),el('pre',typeof value==='string'?value:JSON.stringify(value,null,2))); return node;}
export function note(text, cls='note') {return el('p',text,cls);}
export async function request(path, payload) {
  const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),4000);
  try {
    const options={signal:controller.signal,cache:'no-store'};
    if(payload!==undefined){const session=await fetch('/api/session',{signal:controller.signal,cache:'no-store'}).then(r=>r.json()); Object.assign(options,{method:'POST',headers:{'Content-Type':'application/json','X-HUD-Token':session.token},body:JSON.stringify(payload)});}
    const response=await fetch(path,options); const data=await response.json();
    if(!response.ok) throw new Error(data.error||'Request failed');
    if(data.status==='unavailable') throw new Error(`${data.error}: ${data.message}`);
    return data;
  } finally {clearTimeout(timer);}
}
export function poll(id,path,render,period=5000){
  const root=document.getElementById(id); let stopped=false; let pending=false;
  const tick=async()=>{if(stopped||pending)return;pending=true;try{
    const data=await request(path);
    // Keep details open without freezing health/freshness when a panel has keyboard focus.
    const expanded=new Set([...root.querySelectorAll('details[open]')].map(n=>n.querySelector('summary')?.textContent));
    const active=document.activeElement;const focusIndex=[...root.querySelectorAll('button,summary')].indexOf(active);
    const scrolls=[...root.querySelectorAll('.scroll,.table-wrap')].map(n=>n.scrollTop);
    render(root,data);
    root.querySelectorAll('details').forEach(n=>{n.open=expanded.has(n.querySelector('summary')?.textContent);});
    root.querySelectorAll('.scroll,.table-wrap').forEach((n,i)=>{n.scrollTop=scrolls[i]||0;});
    if(focusIndex>=0)root.querySelectorAll('button,summary')[focusIndex]?.focus({preventScroll:true});
  }catch(error){root.replaceChildren(note('Unavailable','state amber'),note(error.message),note('This module will retry automatically.'));}finally{pending=false;if(!stopped)setTimeout(tick,period);}};
  tick(); return {refresh:tick,stop:()=>{stopped=true;}};
}
export function table(headers,rows){const wrap=el('div',undefined,'table-wrap'), t=el('table'), head=el('thead'),tr=el('tr');headers.forEach(v=>tr.append(el('th',v)));head.append(tr);t.append(head);const body=el('tbody');rows.forEach(values=>{const r=el('tr');values.forEach(v=>r.append(el('td',v??'—')));body.append(r);});t.append(body);wrap.append(t);return wrap;}
export function stats(values){const grid=el('div',undefined,'stat-grid');Object.entries(values).forEach(([key,value])=>{const cell=el('div',undefined,'stat');cell.append(el('small',key),el('strong',value));grid.append(cell);});return grid;}
'@
Write-Source 'static/core.js' $content

$content = @'
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>JEV / Command Center</title><link rel="stylesheet" href="/static/style.css"><script type="module" src="/static/app.js"></script></head>
<body>
<header class="ribbon"><a class="brand" href="/" aria-label="JEV Command Center">JEV<span>CONTROL</span></a><div id="hud" class="pills" aria-label="System health"><div class="pill">Loading system telemetry…</div></div><span class="local"><i></i> LOCAL SESSION</span></header>
<main>
<div class="page-title"><div><p class="eyebrow">OPERATIONS / COMMAND CENTER</p><h1>Every record. Accounted for.</h1><p class="subtitle">Inspect the offline core. Review the next move.</p></div><div class="boundary">LOOPBACK ONLY<span>Financial values remain exact strings</span></div></div>
<div class="workbench">
<section class="card" aria-labelledby="hermes-title"><div class="card-heading"><div><span class="module">01 / INFERENCE</span><h2 id="hermes-title">Hermes & repair loop</h2></div><span class="chip">READ ONLY</span></div><div id="hermes" class="module-body" aria-live="polite"><p>Waiting for local runtime…</p></div></section>
<section class="card" aria-labelledby="ledger-title"><div class="card-heading"><div><span class="module">02 / FINANCIAL CORE</span><h2 id="ledger-title">Ledger & quarantine</h2></div><span class="chip">EXPORTED SNAPSHOT</span></div><div id="ledger" class="module-body" aria-live="polite"><p>Waiting for offline snapshot…</p></div></section>
<section class="card" aria-labelledby="gtm-title"><div class="card-heading"><div><span class="module">03 / HUMAN REVIEW</span><h2 id="gtm-title">Outreach approval gate</h2></div><span class="chip amber">HUMAN DECISION</span></div><div id="gtm" class="module-body"><p>Loading staged drafts…</p></div></section>
<section class="card" aria-labelledby="alerts-title"><div class="card-heading"><div><span class="module">04 / NOTIFICATIONS</span><h2 id="alerts-title">Email alert center</h2></div><span class="chip">METADATA ONLY</span></div><div id="alerts" class="module-body"><p>Loading dispatcher…</p></div></section>
</div>
<footer><span>JEV ENGINE <b>/</b> LOCAL-FIRST OPERATIONS</span><span>Approval records a decision. It never sends outreach.</span></footer>
</main>
</body></html>
'@
Write-Source 'static/index.html' $content

$content = @'
import {el,poll,note,details,request} from '../core.js';
function render(root,data){
  const body=[el('p',data.armed?'Dispatcher armed':'SMTP not configured',`state ${data.armed?'good':'amber'}`),note(data.armed?'TLS enabled. Delivery is confirmed only after SMTP acceptance.':'Set SMTP environment variables and restart. Events remain in the local outbox.'),note(`Last confirmed send: ${data.last_sent_at||'none'}`),note(`Pending: ${data.counts.pending||'0'} · Sent: ${data.counts.sent||'0'} · Failed: ${data.counts.failed||'0'} · Uncertain: ${data.counts.uncertain||'0'}`)];
  const test=el('button','Queue test alert');test.type='button';test.disabled=!data.armed;test.addEventListener('click',async()=>{test.disabled=true;try{render(root,await request('/api/alerts',{action:'test'}));}catch(error){root.append(note(error.message,'bad'));test.disabled=false;}});body.push(test,note('Recipient comes only from SMTP configuration. No client data leaves through alerts.'));
  const logs=el('div',undefined,'scroll');
  for(const item of data.logs){const line=el('div',undefined,'alert-line');line.append(el('b',`${item.event_state} · ${item.delivery_state}`),note(`${item.reference} · ${item.sent_at||item.recorded_at}`));if(item.error)line.append(note(item.error,'note amber'));
    if(['failed','uncertain'].includes(item.delivery_state)){const retry=el('button','Retry after mailbox check','secondary');retry.addEventListener('click',async()=>{if(item.delivery_state==='uncertain'&&!confirm('SMTP delivery is uncertain. Verify your mailbox first; retrying can produce a duplicate. Continue?'))return;retry.disabled=true;try{render(root,await request('/api/alerts',{action:'retry',event_id:item.event_id}));}catch(error){line.append(note(error.message,'bad'));retry.disabled=false;}});line.append(retry);}logs.append(line);}
  if(!data.logs.length)logs.append(el('div','No alert events observed yet.','empty'));
  body.push(logs,details('Source watcher health',data.sources),note(data.notice));root.replaceChildren(...body);
}
export function start(){poll('alerts','/api/alerts',render);}
'@
Write-Source 'static/modules/alerts.js' $content

$content = @'
import {el,poll,note,request} from '../core.js';
function render(root,data){
  const body=[note(data.notice)]; const pending=data.drafts.filter(d=>d.effective_status==='needs_review');
  body.push(el('p',`${pending.length} awaiting your review`,'state'));
  const list=el('div',undefined,'scroll');
  for(const draft of data.drafts){const card=el('article',undefined,'draft');const row=el('div',undefined,'row');row.append(el('h3',draft.company_name||draft.recipient_ref||'Untitled draft'),el('span',draft.effective_status,'badge '+(draft.effective_status==='needs_review'?'amber':'')));card.append(row,note(`To: ${draft.recipient_ref||'not specified'}`),el('p',draft.subject||'(No subject)','subject'),el('div',draft.body||'(No body)','body'));
    if(draft.effective_status==='needs_review'){const actions=el('div',undefined,'actions');for(const [label,decision] of [['Approve','approved'],['Reject','rejected']]){const button=el('button',label,decision==='rejected'?'secondary':'');button.type='button';button.addEventListener('click',async()=>{actions.querySelectorAll('button').forEach(b=>b.disabled=true);try{render(root,await request('/api/gtm-queue',{id:draft.id,revision:data.revision,decision}));}catch(error){card.append(note(error.message,'note bad'));actions.querySelectorAll('button').forEach(b=>b.disabled=false);}});actions.append(button);}card.append(actions);}
    list.append(card);
  }
  if(!data.drafts.length)list.append(el('div','No staged outreach. New drafts will appear here for review.','empty'));
  body.push(list);root.replaceChildren(...body);
}
export function start(){poll('gtm','/api/gtm-queue',render);}
'@
Write-Source 'static/modules/gtm.js' $content

$content = @'
import {el,poll,note,details} from '../core.js';
export function start(){poll('hermes','/api/hermes',(root,data)=>{
  const body=[]; const telemetry=data.telemetry;
  body.push(el('p',data.connected?'Runtime connected':'Runtime on standby',`state ${data.connected?'good':'amber'}`));
  body.push(note(`${data.endpoint} · Probe ${data.latency_ms||'—'} ms`));
  body.push(note(`Active model: ${data.models?.join(', ')||'not reported'}`));
  if(!telemetry){body.push(el('div','No inference history has been exported yet. Endpoint health is independent of history.','empty'));root.replaceChildren(...body);return;}
  if(telemetry.is_simulated||String(telemetry.execution_mode).includes('simulat'))body.push(note('SIMULATED RESULT — not evidence of a live Hermes inference.','badge amber'));
  if(data.snapshot_stale)body.push(note('Snapshot is stale. The probe above is independent and current.','note amber'));
  body.push(note(`Last inference: ${telemetry.timestamp_utc||'unknown'} · ${telemetry.status||'unknown'}`));
  const usage=telemetry.usage?.completion_tokens;
  if(Number.isSafeInteger(usage)&&usage>=0){body.push(note(`Measured completion usage: ${usage} / 4096 tokens`));const meter=el('progress',undefined,'meter');meter.max=4096;meter.value=usage;meter.setAttribute('aria-label','Completion token usage');body.push(meter);if(usage>4096)body.push(note('Token limit exceeded in reported telemetry.','bad'));}
  else body.push(note('Completion tokens: unknown / 4096 · adapter reports estimates only.'));
  if(data.repair_bound_breach)body.push(note('REPAIR BOUND BREACH — expected at most two attempts.','bad'));
  for(const attempt of telemetry.attempts.slice(0,2)){const node=el('div',undefined,'attempt');node.append(el('b',`Attempt ${attempt.attempt} ${attempt.attempt===2?'· bounded repair':''}`),note(attempt.outcome||'No outcome'),note(`Estimated input + output tokens: ${attempt.estimated_tokens??'unknown'}`));if(attempt.error)node.append(details('Validation / endpoint log',attempt.error));body.push(node);}
  if(telemetry.attempts.length<2)body.push(note('Attempt 2: not used. One repair is the maximum.'));
  root.replaceChildren(...body);
});}
'@
Write-Source 'static/modules/hermes.js' $content

$content = @'
import {el,poll} from '../core.js';
export function start(){poll('hud','/api/hud',(root,data)=>{
  const h=data.hermes,l=data.ledger,a=data.alerts; const invariant=l.invariant?.status||'UNKNOWN';
  const model=h.models?.join(', ')||'No active model reported';
  const items=[['HERMES LOOPBACK',h.connected?'Connected':'Standby',model,h.connected?'good':'amber'],
    ['ZERO-LOSS COUNTS',invariant,'Received = Accepted + Quarantined + Duplicates',invariant==='PASS'?'good':invariant==='BREACH'?'bad':'amber'],
    ['LEDGER PULSE',l.status==='unavailable'?'Unavailable':`${l.counts?.running||'0'} running · ${l.counts?.completed||'0'} complete`,l.status==='unavailable'?'Counts unknown':`${l.counts?.quarantined||'0'} quarantined${l.status==='stale'?' · STALE':''}`,''],
    ['EMAIL DISPATCHER',a.armed?'Armed':'Not configured',a.last_sent_at?`Last sent ${a.last_sent_at}`:'No confirmed delivery',a.armed?'good':'amber']];
  root.replaceChildren(...items.map(([title,value,detail,cls])=>{const node=el('div',undefined,'pill');node.append(el('small',title),el('strong',value,cls),el('div',detail,'detail'));node.title=detail;return node;}));
});}
'@
Write-Source 'static/modules/hud.js' $content

$content = @'
import {el,poll,note,details,table,stats} from '../core.js';
export function start(){poll('ledger','/api/offline-ledger',(root,data)=>{
  const inv=data.invariant; const body=[el('p',`${inv.status} · reconciliation counts`,`state ${inv.status==='PASS'?'good':inv.status==='BREACH'?'bad':'amber'}`),note(inv.reason)];
  if(inv.totals)body.push(stats(inv.totals));else body.push(el('div','No final batch counters were published. Job completion alone does not prove reconciliation.','empty'));
  if(inv.failed_batches?.length)body.push(note(`Failing batches: ${inv.failed_batches.join(', ')}`,'bad'));
  if(inv.recorded_at)body.push(note(`Report: ${inv.recorded_at} · Job ${inv.job_id||'unspecified'}`));
  body.push(table(['Job','State','Attempts','Updated'],data.jobs.map(j=>[j.job_id,j.state,j.attempt_count,j.updated_at])));
  body.push(note(`${data.jobs.length} most recent rows · Export ${data.exported_at}${data.status==='stale'?' · STALE':''}`));
  body.push(details('Quarantined rows',data.quarantine??'Not exported. No rows are inferred from job state.'));
  body.push(details('Exact Decimal risk profiles',data.risk_profiles??'Not exported. Financial values will render as exact strings.'));
  body.push(note(data.event_capture?'Transactional terminal-event capture installed.':'Event capture is not installed; every transition cannot be guaranteed.','note '+(data.event_capture?'':'amber')));
  if(Object.keys(data.source_errors||{}).length)body.push(details('Source availability',data.source_errors));
  root.replaceChildren(...body);
});}
'@
Write-Source 'static/modules/ledger.js' $content

$content = @'
:root{color-scheme:dark;--bg:#0c1016;--surface:#141b24;--line:#2a3442;--muted:#a3b0c2;--text:#eef4fc;--mint:#7ce6bf;--amber:#f3c572;--red:#ff9094}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}.ribbon{position:sticky;top:0;z-index:5;min-height:92px;display:flex;align-items:center;gap:24px;padding:16px 32px;background:#111720;border-bottom:1px solid var(--line)}.brand{text-decoration:none;color:var(--text);font-size:25px;font-weight:850;letter-spacing:2px;line-height:1}.brand span{display:block;font-size:9px;letter-spacing:3px;margin-top:7px;color:var(--mint)}.pills{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:10px;flex:1}.pill{border:1px solid var(--line);border-radius:9px;background:#18212b;padding:9px 12px;min-width:0}.pill small{display:block;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:1px}.pill strong{display:block;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pill .detail{font-size:10px;color:var(--muted)}.local{font:10px ui-monospace,monospace;white-space:nowrap;color:var(--muted)}.local i{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--mint);margin-right:6px}main{max-width:1640px;margin:auto;padding:34px 36px}.page-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:28px}.eyebrow{color:var(--mint);font:10px ui-monospace,monospace;letter-spacing:2px;margin:0 0 10px}h1{font-size:30px;letter-spacing:-1px;margin:0;font-weight:650}.subtitle{color:var(--muted);margin:7px 0 0}.boundary{font:10px ui-monospace,monospace;letter-spacing:1px;text-align:right;color:var(--mint)}.boundary span{display:block;color:var(--muted);margin-top:7px;font-size:10px;letter-spacing:0}.workbench{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}.card{background:var(--surface);border:1px solid var(--line);border-radius:13px;min-width:0;overflow:hidden}.card-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:20px 22px;border-bottom:1px solid var(--line)}.module{color:var(--muted);font:10px ui-monospace,monospace;letter-spacing:1.4px}h2{margin:4px 0 0;font-size:18px;font-weight:600}.chip,.badge{font-size:9px;font-weight:700;letter-spacing:.7px;padding:4px 7px;border:1px solid var(--line);border-radius:5px;white-space:nowrap;color:var(--muted)}.module-body{padding:20px 22px;min-height:220px}.good{color:var(--mint)}.amber{color:var(--amber)}.bad{color:var(--red)}.muted,.note{color:var(--muted)}.note{font-size:12px;margin:12px 0}.state{font-size:20px;font-weight:650;margin:0 0 12px}.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.stat{padding:10px;background:#0e151d;border:1px solid var(--line);border-radius:7px;min-width:0}.stat small{display:block;color:var(--muted);font-size:10px}.stat strong{font:19px ui-monospace,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#c5d5e8;background:#0d141c;padding:12px;border-radius:7px;font:11px/1.6 ui-monospace,monospace;max-height:240px;overflow:auto}details{margin:12px 0}summary{cursor:pointer;color:var(--muted);font-size:12px}button{background:var(--mint);border:1px solid transparent;border-radius:6px;color:#08251b;padding:8px 13px;font-weight:700;font-size:12px;cursor:pointer}button.secondary{background:transparent;color:var(--muted);border-color:#516074}button:disabled{opacity:.5;cursor:wait}button:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid var(--amber);outline-offset:4px}.actions{display:flex;gap:8px;margin-top:12px}.draft{padding:15px;background:#101720;border:1px solid var(--line);border-radius:8px;margin-bottom:12px}.draft h3{margin:0;font-size:14px}.draft .subject{font-weight:600;font-size:12px;margin:12px 0 8px}.draft .body{white-space:pre-wrap;font-size:12px;color:#bfccdc;max-height:160px;overflow:auto}.table-wrap{overflow:auto;max-height:245px}table{border-collapse:collapse;width:100%;font-size:11px}th,td{text-align:left;border-bottom:1px solid var(--line);padding:8px 7px;white-space:nowrap}th{color:var(--muted);font-weight:500}td:first-child{max-width:180px;overflow:hidden;text-overflow:ellipsis}.empty{border:1px dashed #435168;border-radius:8px;padding:18px;color:var(--muted)}.meter{height:6px;accent-color:var(--mint);width:100%}.alert-line{padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}.scroll{max-height:300px;overflow:auto}.attempt{border-left:2px solid #516074;padding-left:12px;margin:14px 0}.attempt b{font-size:12px}footer{display:flex;justify-content:space-between;gap:16px;margin-top:24px;color:#8291a7;font:10px ui-monospace,monospace}footer b{color:var(--mint);margin:0 6px}@media(min-width:1500px){.module-body{min-height:245px}}@media(max-width:1100px){.local{display:none}.ribbon{padding:12px 20px;gap:16px}.pills{grid-template-columns:repeat(2,1fr)}main{padding:26px 20px}.chip{font-size:8px}.card-heading{padding:16px}.module-body{padding:16px}}@media(max-width:760px){.workbench{grid-template-columns:1fr}.boundary{display:none}h1{font-size:25px}.ribbon{position:relative}.brand{font-size:20px}.pills{gap:6px}.pill{padding:7px}.pill strong{font-size:11px}.pill .detail{display:none}main{padding:22px 14px}footer{flex-direction:column}.stat-grid{gap:5px}.stat strong{font-size:16px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
'@
Write-Source 'static/style.css' $content

$content = @'
$ErrorActionPreference = 'Stop'
$deploymentRoot = $PSScriptRoot
foreach ($name in @('server', 'observer')) {
    $pidFile = Join-Path $deploymentRoot "state\$name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $expected = if ($name -eq 'server') { Join-Path $deploymentRoot 'app.py' } else { Join-Path $deploymentRoot 'offline_observer.py' }
        if ($process -and $process.CommandLine -and $process.CommandLine.Contains($expected)) {
            Stop-Process -Id $processId -ErrorAction Stop
            Write-Host "Stopped JEV $name ($processId)."
        }
        Remove-Item -LiteralPath $pidFile
    }
}
'@
Write-Source 'stop.ps1' $content

$content = @'
import concurrent.futures
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from hud.alerts import AlertCenter
from hud.config import Config
from hud.gtm import Conflict, approved_drafts, content_hash, decide, effective_status, read_queue, view_queue, write_queue
from hud.hermes import HermesProbe
from hud.ledger import evaluate_report, get_ledger
from hud.server import Application, make_server
from hud.storage import atomic_json, database, dumps, loads, read_json, utcnow, validate_money_strings
from offline_observer import export_once, install_event_capture
from offline_telemetry import BatchCounts, Money, annual_labor_cost, publish_reconciliation


class SystemTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = self.root / 'delivery-offline'
        self.core.mkdir()
        self.home = self.root / 'hud-interface'
        self.home.mkdir()
        self.queue = self.root / 'gtm' / 'staged_outreach.json'
        self.snapshot = self.home / 'inbox' / 'offline_snapshot.json'
        self.config = Config(self.home, self.queue, self.snapshot)
        self.dbpath = self.core / 'job_ledger.db'
        with database(self.dbpath) as db:
            db.execute('CREATE TABLE jobs(job_id TEXT PRIMARY KEY,job_type TEXT,state TEXT,attempt_count INTEGER,created_at TEXT,updated_at TEXT)')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', ('j1','reconcile','running',1,utcnow(),utcnow()))
        atomic_json(self.queue, [{'company_name':'Fixture','subject':'Review <script>','body':'Do not send','status':'needs_review'}])

    def tearDown(self):
        self.temp.cleanup()

    def event(self, suffix='one'):
        return {'event_id':suffix,'reference':'0123456789abcdef','kind':'transition','state':'completed'}

    def smtp(self):
        return {'JEV_SMTP_HOST':'invalid.example','JEV_SMTP_FROM':'owner@example.invalid', 'JEV_SMTP_TO':'owner@example.invalid'}

    def finish(self):
        with database(self.dbpath) as db:
            db.execute("UPDATE jobs SET state='completed' WHERE job_id='j1'")

    def test_money_exact_from_string(self):
        money = Money(amount='9007199254740993.12345678901234567890')
        self.assertEqual(json.loads(dumps(money.model_dump()))['amount'], money.amount)
        self.assertEqual(annual_labor_cost('1.25',12,Money(amount='54.00')).amount, '810.0000')
        for bad in [1.2, 1, True, 'NaN', 'Infinity']:
            with self.assertRaises((ValueError, ArithmeticError)):
                Money(amount=bad)

    def test_numeric_money_rejected(self):
        for raw in ['{"amount": 0.1}', '{"amount": 9007199254740993}']:
            with self.assertRaises(ValueError):
                validate_money_strings(loads(raw))

    def test_json_duplicate_nonfinite_float(self):
        for raw in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.assertRaises(ValueError): loads(raw)
        self.assertEqual(loads('{"x":0.1}')['x'], Decimal('0.1'))
        with self.assertRaises(TypeError): dumps({'amount':0.1})

    def test_count_invariant_per_batch(self):
        report={'final':True,'batches':[{'batch_id':'a','received':2,'accepted':1,'quarantined':0,'duplicates':0},
                                         {'batch_id':'b','received':0,'accepted':1,'quarantined':0,'duplicates':0}]}
        self.assertEqual(evaluate_report(report)['status'],'BREACH')
        self.assertEqual(evaluate_report(None)['status'],'UNKNOWN')
        report['batches'][0]['received']=True
        with self.assertRaises(ValueError): evaluate_report(report)

    def test_snapshot_export_missing_optional(self):
        export_once(self.core,self.snapshot)
        result=get_ledger(self.config)
        self.assertEqual(result['invariant']['status'],'UNKNOWN')
        self.assertEqual(result['jobs'][0]['job_id'],'j1')
        self.assertIsNone(result['risk_profiles'])

    def test_final_report_and_staleness(self):
        self.finish()
        publish_reconciliation(self.core,'j1',[BatchCounts(batch_id='b1',received=4,accepted=2,quarantined=1,duplicates=1)],
                               risk_profiles={'labor':{'amount':'9007199254740993.0001','currency':'USD'}})
        export_once(self.core,self.snapshot)
        result=get_ledger(self.config)
        self.assertEqual(result['invariant']['status'],'PASS')
        self.assertEqual(result['risk_profiles']['data']['labor']['amount'],'9007199254740993.0001')
        snapshot=read_json(self.snapshot)
        snapshot['exported_at']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        atomic_json(self.snapshot,snapshot)
        self.assertEqual(get_ledger(self.config)['invariant']['status'],'STALE')

    def test_running_job_cannot_pass(self):
        publish_reconciliation(self.core,'j1',[BatchCounts(batch_id='b1',received=1,accepted=1,quarantined=0,duplicates=0)])
        export_once(self.core,self.snapshot)
        self.assertEqual(get_ledger(self.config)['invariant']['status'],'UNKNOWN')

    def test_durable_events_fast_transitions(self):
        install_event_capture(self.dbpath)
        with database(self.dbpath) as db:
            for state in ['quarantined','queued','running','completed']:
                db.execute('UPDATE jobs SET state=? WHERE job_id=?',(state,'j1'))
        result=export_once(self.core,self.snapshot)
        self.assertEqual([e['state'] for e in result['events']],['quarantined','completed'])
        self.assertTrue(result['ledger']['event_capture'])
        install_event_capture(self.dbpath)
        with database(self.dbpath) as db:
            db.execute('BEGIN')
            db.execute("UPDATE jobs SET state='quarantined'")
            db.rollback()
            self.assertEqual(db.execute('SELECT count(*) FROM hud_terminal_events').fetchone()[0],2)

    def test_no_ledger_creation_on_missing_source(self):
        missing=self.root/'missing'
        export_once(missing,self.snapshot)
        self.assertFalse(missing.exists())
        self.assertEqual(read_json(self.snapshot)['ledger']['status'],'unavailable')

    def test_approval_and_content_invalidation(self):
        view=view_queue(self.queue)
        result=decide(self.queue,view['drafts'][0]['id'],view['revision'],'approved')
        self.assertEqual(len(approved_drafts(self.queue)),1)
        draft=result['drafts'][0]
        draft['body']='Edited content'
        self.assertEqual(effective_status(draft),'needs_review')
        with self.assertRaises(Conflict): decide(self.queue,view['drafts'][0]['id'],view['revision'],'rejected')

    def test_concurrent_decisions_one_winner(self):
        view=view_queue(self.queue)
        def run(decision):
            try:
                decide(self.queue,view['drafts'][0]['id'],view['revision'],decision)
                return 'won'
            except Conflict: return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(2) as executor:
            self.assertEqual(sorted(executor.map(run,['approved','rejected'])),['conflict','won'])

    def test_producer_cannot_self_approve(self):
        draft={'draft_id':'new','body':'test','status':'approved'}
        draft['approval_hash']=content_hash(draft)
        write_queue(self.queue,[draft])
        self.assertEqual(view_queue(self.queue)['drafts'][0]['effective_status'],'needs_review')
        self.assertTrue(Path(str(self.queue)+'.events.json').exists())

    def test_outbox_dedup_and_restart(self):
        alerts=AlertCenter(self.config,env={})
        alerts.enqueue(self.event());alerts.enqueue(self.event())
        self.assertEqual(alerts.view()['counts']['pending'],'1')
        with alerts.db() as db: db.execute("UPDATE alerts SET delivery_state='sending'")
        reloaded=AlertCenter(self.config,env={})
        self.assertEqual(reloaded.view()['counts']['uncertain'],'1')
        self.assertFalse(reloaded.send_one())

    def test_smtp_connection_failure_is_not_sent(self):
        alerts=AlertCenter(self.config,env=self.smtp());alerts.enqueue(self.event())
        with patch('hud.alerts.smtplib.SMTP',side_effect=OSError('secret-provider-data')): alerts.send_one()
        state=alerts.view()
        self.assertIsNone(state['last_sent_at'])
        self.assertNotIn('secret-provider-data',dumps(state))
        self.assertEqual(state['counts']['pending'],'1')

    def test_smtp_ambiguous_send(self):
        alerts=AlertCenter(self.config,env=self.smtp());alerts.enqueue(self.event())
        client=MagicMock();client.send_message.side_effect=TimeoutError('uncertain')
        with patch('hud.alerts.smtplib.SMTP',return_value=client):alerts.send_one()
        self.assertEqual(alerts.view()['counts']['uncertain'],'1')

    def test_smtp_metadata_only(self):
        alerts=AlertCenter(self.config,env=self.smtp());event=self.event();event['body']='sensitive financial amount';alerts.enqueue(event)
        client=MagicMock();client.send_message.return_value={}
        with patch('hud.alerts.smtplib.SMTP',return_value=client): alerts.send_one()
        message=client.send_message.call_args.args[0]
        self.assertNotIn('sensitive financial amount',message.as_string())
        self.assertEqual(alerts.view()['counts']['sent'],'1')

    def test_module_isolation(self):
        app=Application(self.config)
        self.assertEqual(app.get('/api/offline-ledger')['status'],'unavailable')
        self.assertEqual(app.get('/api/gtm-queue')['status'],'ok')
        self.queue.write_text('broken',encoding='utf-8')
        self.assertEqual(app.get('/api/gtm-queue')['status'],'unavailable')
        self.assertEqual(app.get('/api/alerts')['status'],'ok')

    def test_corrupt_alert_database_isolated(self):
        state=self.home/'state';state.mkdir();(state/'alerts.sqlite3').write_bytes(b'not SQLite')
        app=Application(self.config)
        self.assertEqual(app.get('/api/alerts')['status'],'unavailable')
        self.assertEqual(app.get('/api/gtm-queue')['status'],'ok')

    def test_hermes_offline_and_simulation_honesty(self):
        atomic_json(self.core/'inference_telemetry.json',{'max_retries':1,'attempts':[{'estimated_tokens':45}], 'is_simulated':True})
        export_once(self.core,self.snapshot)
        probe=HermesProbe()
        with patch('hud.hermes.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError()
            probe.probe()
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],1.5)
        data=probe.get(self.config)
        self.assertFalse(data['connected'])
        self.assertTrue(data['telemetry']['is_simulated'])
        self.assertNotIn('usage',data['telemetry'])

    def test_http_csrf_host_and_independent_routes(self):
        app=Application(replace(self.config,port=0))
        server=make_server(app)
        port=server.server_address[1]
        app.config=replace(app.config,port=port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
            connection.request('POST','/api/alerts',body='{"action":"test"}',headers={'Content-Type':'application/json'})
            response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request('GET','/api/gtm-queue',headers={'Host':'evil.example'})
            response=connection.getresponse();self.assertEqual(response.status,403);response.read()
            connection.request('GET','/api/gtm-queue')
            response=connection.getresponse();self.assertEqual(response.status,200);response.read()
            connection.request('POST','/api/alerts',body='{"action":"test"}',headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{port}','X-HUD-Token':app.token})
            response=connection.getresponse();self.assertEqual(response.status,200);response.read()
            connection.close()
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
'@
Write-Source 'tests/test_system.py' $content

New-Item -ItemType Directory -Force -Path (Join-Path $deploymentRoot 'state'), (Join-Path $deploymentRoot 'inbox') | Out-Null
if ($NoLaunch) { Write-Host "Sources written to $deploymentRoot"; return }
$candidates = @()
if ($PythonPath) { $candidates += $PythonPath }
$candidates += (Join-Path $ProjectRoot 'delivery-offline\venv\Scripts\python.exe')
$candidates += (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
$command = Get-Command python -ErrorAction SilentlyContinue
if ($command) { $candidates += $command.Source }
$selectedPython = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
        try {
            & $candidate -c 'import sys; assert sys.version_info >= (3,11)' 2>$null
            if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
        } catch { }
    }
}
if (-not $selectedPython) { throw 'No working Python 3.11+ found. Re-run with -PythonPath.' }
$env:JEV_PROJECT_ROOT = $ProjectRoot
$observerScript = Join-Path $deploymentRoot 'offline_observer.py'
$coreDirectory = Join-Path $ProjectRoot 'delivery-offline'
$snapshotPath = Join-Path $deploymentRoot 'inbox\offline_snapshot.json'
if (-not $NoObserver) {
    $observerArgs = @($observerScript, '--core', $coreDirectory, '--output', $snapshotPath)
    if (-not $ReadOnlyObserver -and (Test-Path -LiteralPath (Join-Path $coreDirectory 'job_ledger.db'))) { $observerArgs += '--install-events' }
    & $selectedPython @observerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Offline observer bootstrap failed; fix source/export errors before launch.' }
    $watchArgs = '"' + $observerScript + '" --core "' + $coreDirectory + '" --output "' + $snapshotPath + '" --watch'
    $observer = Start-Process -FilePath $selectedPython -ArgumentList $watchArgs -WorkingDirectory $deploymentRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $deploymentRoot 'state\observer.log') -RedirectStandardError (Join-Path $deploymentRoot 'state\observer-error.log')
    [System.IO.File]::WriteAllText((Join-Path $deploymentRoot 'state\observer.pid'), [string]$observer.Id, $utf8)
}
$serverScript = Join-Path $deploymentRoot 'app.py'
$server = Start-Process -FilePath $selectedPython -ArgumentList ('"' + $serverScript + '"') -WorkingDirectory $deploymentRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $deploymentRoot 'state\server.log') -RedirectStandardError (Join-Path $deploymentRoot 'state\server-error.log')
[System.IO.File]::WriteAllText((Join-Path $deploymentRoot 'state\server.pid'), [string]$server.Id, $utf8)
$port = if ($env:JEV_HUD_PORT) { $env:JEV_HUD_PORT } else { '5050' }
$ready = $false
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    Start-Sleep -Milliseconds 250
    $server.Refresh()
    if ($server.HasExited) { throw 'HUD exited during startup. Read state\server-error.log.' }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/session" -UseBasicParsing -TimeoutSec 1
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if (-not $ready) { throw 'HUD startup was not confirmed. Inspect state logs.' }
Write-Host "JEV HUD ready: http://127.0.0.1:$port"
Write-Host 'SMTP requires your environment configuration. No outreach is sent by this installer.'
