from pydantic import BaseModel, Field, field_validator
from decimal import Decimal, InvalidOperation
from typing import List, Optional

class Money(BaseModel):
    amount: str  # Enforced as string to prevent floating-point precision loss
    currency: str = "USD"

    @field_validator("amount")
    @classmethod
    def val_amount(cls, v: str) -> str:
        try:
            d = Decimal(v)
            if not d.is_finite():
                raise ValueError("Amount must be a finite number.")
            return str(d)
        except InvalidOperation:
            raise ValueError(f"Invalid monetary amount string: {v}")

    def to_decimal(self) -> Decimal:
        return Decimal(self.amount)

class LaborBaseline(BaseModel):
    hours_per_run: str
    hours_basis: str
    runs_per_year: int
    loaded_hourly_cost: Optional[Money] = None
    status: str
    evidence_ids: List[str] = Field(default_factory=list)

class DerivedCosts(BaseModel):
    annual_baseline_labor_cost: Optional[Money] = None
    formula: Optional[str] = None
    calculated_by: str = "python"

class ClientRiskProfile(BaseModel):
    client_id: str
    workflow: str
    labor: LaborBaseline
    derived: DerivedCosts
    evidence: List[str] = Field(default_factory=list)
    approval_status: str = "needs_confirmation"

class FailureEvent(BaseModel):
    type: str
    description: str
    reported_events: int
    period: str
    evidence_ids: List[str] = Field(default_factory=list)
