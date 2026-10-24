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
