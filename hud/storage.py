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
