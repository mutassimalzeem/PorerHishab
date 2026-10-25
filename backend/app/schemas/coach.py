"""Validated contracts for deterministic coaching and optional explanations."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
GoalStatus = Literal["active", "completed", "cancelled"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalCreate(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    target_amount: PositiveMoney
    current_saved: Money | None = None
    target_date: date

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class GoalUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    target_amount: PositiveMoney | None = None
    current_saved: Money | None = None
    target_date: date | None = None
    status: GoalStatus | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        for field in ("name", "target_amount", "target_date", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        if self.name is not None:
            self.name = GoalCreate.name_not_blank(self.name)
        return self


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    name: str
    description: str | None
    target_amount: Decimal
    current_saved: Decimal | None
    target_date: date
    status: GoalStatus
    created_at: datetime
    updated_at: datetime
    saved_source: str = "user_reported; unknown when null; not reconciled with accounts"


class GoalPage(BaseModel):
    items: list[GoalRead]
    total: int
    limit: int
    offset: int


class GoalPlan(BaseModel):
    goal_id: int
    as_of_date: date
    remaining_amount: Decimal | None
    required_weekly: Decimal | None
    required_monthly: Decimal | None
    estimated_monthly_capacity: Decimal | None
    affordability: Literal["unknown", "appears_feasible", "at_risk", "completed", "cancelled", "overdue"]
    assumptions: list[str]
    limitations: list[str]


class Coverage(BaseModel):
    start_date: date
    end_date: date
    transaction_count: int
    first_transaction_date: date | None
    last_transaction_date: date | None
    limitations: list[str]


class Recommendation(BaseModel):
    id: str
    category: str
    title: str
    evidence: dict[str, Any]
    estimated_monthly_saving: Decimal
    estimated_annual_saving: Decimal
    confidence: Literal["low", "medium"]
    assumptions: list[str]


class RecommendationPage(BaseModel):
    coverage: Coverage
    recommendations: list[Recommendation]
    limitations: list[str]


class Nudge(BaseModel):
    key: str
    type: str
    severity: Literal["info", "warning", "critical"]
    title: str
    evidence: dict[str, Any]
    period_start: date
    period_end: date
    expires_on: date
    next_action: str
    status: Literal["active"] = "active"


class NudgePage(BaseModel):
    as_of_date: date
    insights: list[Nudge]
    limitations: list[str]


class CoachCashflowRequest(StrictModel):
    starting_balance: Money
    months_ahead: int = Field(default=3, ge=1, le=12)


class CoachMonth(BaseModel):
    month: str
    historical_income_estimate: Decimal | None
    historical_expense_estimate: Decimal | None
    scheduled_expenses: Decimal
    uncertain_scheduled_income: Decimal
    reserved_expenses: Decimal
    projected_balance: Decimal | None
    balance_without_future_income: Decimal


class CoachCashflowResponse(BaseModel):
    as_of_date: date
    starting_balance: Decimal
    months: list[CoachMonth]
    coverage: Coverage
    assumptions: list[str]
    limitations: list[str]


class CoachPurchaseRequest(StrictModel):
    purchase_amount: PositiveMoney
    starting_balance: Money
    safety_buffer: Money
    horizon_days: int = Field(default=30, ge=1, le=366)


class CoachPurchaseResponse(BaseModel):
    status: Literal["safe", "caution", "not_recommended", "insufficient_data"]
    currency: str = "BDT"
    purchase_amount: Decimal
    scheduled_expense_reserve: Decimal
    remaining_after_purchase_and_reserve: Decimal
    uncertain_scheduled_income: Decimal
    horizon_end: date
    assumptions: list[str]
    warnings: list[str]


class CategorizeBatchRequest(StrictModel):
    transaction_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=100)

    @field_validator("transaction_ids")
    @classmethod
    def no_duplicates(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("transaction_ids must be unique")
        return value


class CategorizeBatchItem(BaseModel):
    transaction_id: int
    category: str | None
    method: str | None
    confidence: Decimal | None
    reason: str | None
    preserved: bool


class CategorizeBatchResponse(BaseModel):
    items: list[CategorizeBatchItem]
