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
