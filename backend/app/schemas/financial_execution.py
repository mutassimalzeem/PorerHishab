"""AI-16C execution planning contracts; this layer never executes financial actions."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.coaching import CoachingPriority
from app.schemas.financial_coach import CoachEvidence, CoachWarning
from app.schemas.financial_plan import FinancialDecisionSet
from app.schemas.intelligence import IntelligencePeriod


ExecutionKind = Literal[
    "review_cashflow",
    "review_obligations",
    "review_liquidity",
    "review_capacity",
    "review_goal_commitment",
    "review_goal",
    "review_spending",
    "review_savings",
]

ExecutionState = Literal["ready", "blocked"]


class FinancialActionStep(BaseModel):
    """A user-review step derived from one AI-16B priority."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    priority_id: str
    sequence: int = Field(ge=1)
    kind: ExecutionKind
    level: CoachingPriority
    title: str
    description: str
    source_action_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    blocking_priority_ids: list[str] = Field(default_factory=list)
    blocking_factors: list[Literal["goal_capacity_unknown", "goal_not_feasible"]] = Field(default_factory=list)
    state: ExecutionState
    requires_user_confirmation: bool = True
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class FinancialExecutionPlan(BaseModel):
    """Deterministic next-step workflow over an AI-16B decision set."""

    model_config = ConfigDict(extra="forbid")

    policy_version: Literal["ai-16c-v1"] = "ai-16c-v1"
    source_decision_version: Literal["ai-16b-v1"] = "ai-16b-v1"
    as_of_date: date
    planning_horizon: IntelligencePeriod
    data_status: Literal["sufficient", "partial", "insufficient_data"]
    steps: list[FinancialActionStep] = Field(default_factory=list)
    evidence: list[CoachEvidence] = Field(default_factory=list)
    warnings: list[CoachWarning] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_execution(self):
        horizon = self.planning_horizon
        if horizon.start != self.as_of_date or not 0 <= (horizon.end - horizon.start).days <= 366:
            raise ValueError("Invalid execution horizon")

        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Duplicate execution step IDs")
        if [step.sequence for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("Execution steps must have contiguous sequence numbers")

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Duplicate execution evidence IDs")
        evidence = {item.evidence_id: item for item in self.evidence}
        positions = {step.priority_id: index for index, step in enumerate(self.steps)}

        for step in self.steps:
            if not set(step.evidence_ids) <= evidence.keys():
                raise ValueError("Unknown execution evidence IDs")
            support = [evidence[key] for key in step.evidence_ids]
            if not any(item.evidence_type != "interpretation" for item in support):
                raise ValueError("Execution step requires source evidence")
            if any(item.as_of_date != self.as_of_date for item in support):
                raise ValueError("Execution evidence date must match execution date")
            for blocker in step.blocking_priority_ids:
                if blocker not in positions or positions[blocker] >= positions[step.priority_id]:
                    raise ValueError("Execution dependencies must precede their step")
        return self



def execution_plan_from_decisions(decisions: FinancialDecisionSet) -> FinancialExecutionPlan:
    """Type-check the AI-16B input without executing or changing it."""
    return FinancialExecutionPlan(
        as_of_date=decisions.as_of_date,
        planning_horizon=decisions.planning_horizon,
        data_status=decisions.data_status,
        evidence=[item.model_copy(deep=True) for item in decisions.evidence],
        warnings=[item.model_copy(deep=True) for item in decisions.warnings],
        limitations=list(decisions.limitations),
        steps=[],
    )
