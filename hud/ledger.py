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
