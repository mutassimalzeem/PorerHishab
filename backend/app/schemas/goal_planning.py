"""Deterministic personalized planning and explicit user-reported progress."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.coach import Money, PositiveMoney

Feasibility = Literal["feasible", "feasible_with_adjustments", "challenging", "not_currently_feasible", "insufficient_data"]
Key = Annotated[str, Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]

class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: Key
    schedules_confirmed: bool = False
    cadence: Literal["monthly", "weekly"] = "monthly"
    target_amount: PositiveMoney | None = None
    target_date: date | None = None
    income_change_percent: Decimal = Field(Decimal("0"), ge=-80, le=50, decimal_places=2)
    expense_change_percent: Decimal = Field(Decimal("0"), ge=-50, le=100, decimal_places=2)

class ContributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: Key
    amount: PositiveMoney

class MilestoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: Key
    status: Literal["missed", "reported_completed"]

class GoalMilestoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_id: int
    goal_id: int
    sequence: int
    due_date: date
    target_cumulative: Decimal
    expected_contribution: Decimal
    status: Literal["pending", "missed", "reported_completed"]
    completed_at: datetime | None
    progress_source: Literal["user_reported"] = "user_reported"

class GoalEventRead(BaseModel):
    id: int
    goal_id: int
    kind: str
    created_at: datetime
    details: dict

class PlanningCapacity(BaseModel):
    as_of_date: date
    observation_start: date
    observation_end: date
    status: Literal["sufficient", "insufficient_data"]
    conservative_monthly_capacity: Decimal | None
    scenario_monthly_capacity: Decimal | None
    trusted_cash: Decimal | None
    protected_reserve: Decimal | None
    upcoming_obligations: Decimal
    overdue_obligations: Decimal
    reported_earmarks: Decimal | None
    conservative_income: Decimal | None
    protected_expenses: Decimal | None
    health_coverage: Decimal | None
    health_as_of_date: date | None
    explanations: list[str]
    limitations: list[str]

class PlanAlternative(BaseModel):
    key: Literal["extend_deadline", "reduce_target"]
    target_amount: Decimal
    target_date: date
    required_monthly: Decimal
    proposed_monthly: Decimal
    feasibility: Feasibility
    explanation: str

class PersonalizedGoalPlan(BaseModel):
    id: int | None = None
    goal_id: int
    version: int = 0
    calculation_version: str = "ai-15p-v1"
    as_of_date: date
    target_amount: Decimal
    target_date: date | None
    reported_progress: Decimal | None
    verified_goal_progress: Decimal | None = None
    remaining_amount: Decimal
    reported_remaining_amount: Decimal | None
    required_monthly: Decimal | None
    proposed_monthly: Decimal
    feasibility: Feasibility
    explanation: str
    capacity: PlanningCapacity
    alternatives: list[PlanAlternative] = Field(default_factory=list)
    milestones: list[GoalMilestoneRead] = Field(default_factory=list)
    inputs: dict
    limitations: list[str]

class GoalPlanningItem(BaseModel):
    goal_id: int
    name: str
    priority: int
    goal_status: str
    target_amount: Decimal
    remaining_amount: Decimal
    proposed_monthly: Decimal
    accepted_monthly: Decimal
    feasibility: Feasibility
    explanation: str

class GoalPlanningOverview(BaseModel):
    capacity: PlanningCapacity
    goals: list[GoalPlanningItem]
    total_target_amount: Decimal
    total_remaining_amount: Decimal
    total_planned_monthly: Decimal
    total_proposed_monthly: Decimal
    capacity_utilization: Decimal | None
    over_capacity: bool
    upcoming_milestones: list[GoalMilestoneRead]
    missed_milestones: list[GoalMilestoneRead]

class ContributionResult(BaseModel):
    event_id: int
    goal_id: int
    reported_total: Decimal
    goal_status: str
    progress_source: Literal["user_reported"] = "user_reported"
