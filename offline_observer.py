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
