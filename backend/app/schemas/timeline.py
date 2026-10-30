"""Read-only events: history and projections have explicitly separate impact scopes."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel
from app.schemas.intelligence import IntelligencePeriod

EventType = Literal["transaction", "obligation_payment", "obligation", "forecast_expense", "forecast_income", "runway_checkpoint"]
Certainty = Literal["actual", "confirmed", "scheduled", "estimated", "uncertain"]
ImpactScope = Literal["actual_history", "future_projection", "context"]


class TimelineEvidence(BaseModel):
    transaction_id: int | None = None
    obligation_id: int | None = None
    allocation_id: int | None = None
    account_id: int | None = None
    account_name: str | None = None
    category: str | None = None
    transaction_amount: Decimal | None = None
    fee: Decimal | None = None
    period: IntelligencePeriod | None = None
    mode: Literal["historical", "known_obligations"] | None = None
    scheduled_expense_reserve: Decimal | None = None
    expected_expense_reserve: Decimal | None = None
    projected_balance: Decimal | None = None
    minimum_balance: Decimal | None = None


class TimelineEvent(BaseModel):
    id: str
    date: date
    event_type: EventType
    certainty: Certainty
    direction: Literal["income", "expense", "neutral"]
    amount: Decimal | None
    currency: str
    title: str | None
    description: str | None = None
    source: Literal["transaction", "obligation_allocation", "scheduled_cashflow", "financial_runway"]
    source_id: str
    balance_impact: Decimal
    impact_scope: ImpactScope
    cash_impacting: bool
    original_amount: Decimal | None = None
    allocated_amount: Decimal | None = None
    remaining_amount: Decimal | None = None
    reserved_amount: Decimal | None = None
    status: str | None = None
    evidence: TimelineEvidence


class FinancialTimeline(BaseModel):
    currency: Literal["BDT"] = "BDT"
    as_of_date: date
    period: IntelligencePeriod
    projection_period: IntelligencePeriod | None
    starting_balance: Decimal | None
    balance_source: str
    ending_projected_balance: Decimal | None
    runway_status: str | None
    events: list[TimelineEvent]
    event_counts: dict[Certainty, int]
    assumptions: list[str]
    limitations: list[str]
