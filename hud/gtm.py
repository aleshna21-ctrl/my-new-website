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
