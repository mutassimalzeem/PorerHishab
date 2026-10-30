"""Read-only evidence-backed coaching, separate from financial facts."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.intelligence import IntelligencePeriod

CoachingType = Literal["cash_risk", "upcoming_obligations", "spending_spike", "repeated_spending", "savings_opportunity", "goal_risk"]
CoachingPriority = Literal["critical", "high", "medium", "low"]


class CoachingObligation(BaseModel):
    item_id: int
    title: str
    due_date: date
    original_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    timeline_event_id: str


class CoachingMonthlyValue(BaseModel):
    period: IntelligencePeriod
    amount: Decimal


class CoachingEvidence(BaseModel):
    period: IntelligencePeriod
    comparison_period: IntelligencePeriod | None = None
    starting_balance: Decimal | None = None
    balance_source: str | None = None
    scheduled_expense_reserve: Decimal | None = None
    uncertain_income: Decimal | None = None
    minimum_projected_balance: Decimal | None = None
    projected_end_balance: Decimal | None = None
    cash_after_known_obligations: Decimal | None = None
    safety_threshold: Decimal | None = None
    runway_status: str | None = None
    runway_mode: str | None = None
    first_shortfall_date: date | None = None
    first_shortfall_period: IntelligencePeriod | None = None
    category: str | None = None
    observed_value: Decimal | None = None
    reference_value: Decimal | None = None
    percentage_change: Decimal | None = None
    monthly_values: list[CoachingMonthlyValue] = Field(default_factory=list)
    obligations: list[CoachingObligation] = Field(default_factory=list)
    goal_id: int | None = None
    goal_name: str | None = None
    current_saved: Decimal | None = None
    target_amount: Decimal | None = None
    remaining_amount: Decimal | None = None
    target_date: date | None = None
    required_monthly: Decimal | None = None
    estimated_monthly_capacity: Decimal | None = None
    affordability: str | None = None


class CoachingRecommendation(BaseModel):
    id: str
    type: CoachingType
    priority: CoachingPriority
    title: str
    description: str
    recommended_action: str
    currency: Literal["BDT"] = "BDT"
    amount: Decimal | None
    as_of_date: date
    valid_until: date
    subject: str | None = None
    evidence_quality: Literal["recorded", "estimated", "limited"]
    source: Literal["financial_runway", "scheduled_cashflow", "category_spending", "goal_assessment"]
    source_id: str
    evidence: CoachingEvidence
    assumptions: list[str]
    limitations: list[str]


class FinancialCoaching(BaseModel):
    as_of_date: date
    period: IntelligencePeriod
    data_status: Literal["sufficient", "partial", "insufficient_data"]
    recommendations: list[CoachingRecommendation]
    limitations: list[str]
