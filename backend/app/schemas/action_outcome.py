"""Derived action outcomes: observations, never causal claims (AI-15I)."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.coaching import CoachingType

OutcomeStatus = Literal["pending", "insufficient_data", "improved", "unchanged", "worsened"]
OutcomeMetric = Literal[
    "category_spending",
    "recorded_net_cashflow",
    "minimum_projected_balance",
    "obligation_remaining",
    "goal_saved_amount",
    "unsupported",
]
OutcomeDirection = Literal["lower_is_better", "higher_is_better", "neutral"]
OutcomeInterpretation = Literal[
    "decreased",
    "increased",
    "unchanged",
    "pending",
    "insufficient_data",
    "obligation_settled",
    "obligation_partially_settled",
    "obligation_not_settled",
    "goal_history_unavailable",
]
SettlementStatus = Literal["not_settled", "partially_settled", "fully_settled"]


class OutcomeWindow(BaseModel):
    """Inclusive observation window. ``days`` may be zero before any follow-up."""

    start: date
    end: date
    days: int = Field(ge=0)
    is_complete: bool


class OutcomeObligation(BaseModel):
    """Authoritative obligation values copied from AI-15B/AI-15C."""

    item_id: int
    title: str
    due_date: date
    status: str
    original_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal


class OutcomeEvidence(BaseModel):
    """Structured evidence so an observation remains auditable."""

    currency: Literal["BDT"] = "BDT"
    category: str | None = None
    baseline_transaction_count: int | None = None
    follow_up_transaction_count: int | None = None
    obligations: list[OutcomeObligation] = Field(default_factory=list)
    baseline_runway_status: str | None = None
    follow_up_runway_status: str | None = None
    baseline_runway_mode: str | None = None
    follow_up_runway_mode: str | None = None


class ActionOutcome(BaseModel):
    """One acted-on recommendation compared before and after the report."""

    recommendation_id: str
    recommendation_type: CoachingType
    subject: str | None = None
    action_reported_on: date
    status: OutcomeStatus
    metric: OutcomeMetric
    direction: OutcomeDirection
    baseline: OutcomeWindow
    follow_up: OutcomeWindow
    baseline_value: Decimal | None = None
    follow_up_value: Decimal | None = None
    absolute_change: Decimal | None = None
    percentage_change: Decimal | None = None
    settlement_status: SettlementStatus | None = None
    interpretation: OutcomeInterpretation
    causal_claim: Literal[False] = False
    evidence_quality: Literal["recorded", "estimated", "limited"]
    evidence: OutcomeEvidence
    limitations: list[str]


class ActionOutcomeSummary(BaseModel):
    tracked: int
    improved: int
    unchanged: int
    worsened: int
    pending: int
    insufficient_data: int


class ActionOutcomeReport(BaseModel):
    as_of_date: date
    currency: Literal["BDT"] = "BDT"
    items: list[ActionOutcome]
    summary: ActionOutcomeSummary
    limitations: list[str]
