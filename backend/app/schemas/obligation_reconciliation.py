from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class AllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_id: int
    amount: Decimal
    active: bool
    confirmed_at: datetime
    revoked_at: datetime | None

class MatchCandidate(BaseModel):
    transaction_id: int
    date: date
    amount: Decimal
    description: str | None
    merchant: str | None
    category: str | None
    amount_difference: Decimal
    date_distance_days: int
    amount_signal: Literal["exact", "within_tolerance", "partial"]
    category_match: bool
    text_overlap: bool
    confidence: Literal["medium", "low"]
    limitations: list[str]

class ObligationReconciliation(BaseModel):
    item_id: int
    original_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    status: Literal["cancelled", "paid", "partial", "review_required", "unmatched", "overdue", "not_due", "insufficient_data"]
    timing: Literal["overdue", "due", "not_due"]
    ambiguous: bool
    candidates: list[MatchCandidate]
    allocations: list[AllocationRead]
    date_tolerance_days: int
    amount_tolerance: Decimal
    limitations: list[str]

class ReconciliationPage(BaseModel):
    items: list[ObligationReconciliation]
    total: int
    limit: int
    offset: int

class ConfirmAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_full_settlement: bool = False
