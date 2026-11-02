"""AI-16A composes existing planning contracts; it owns no financial arithmetic."""
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.action_plan import CoachingActionPlan
from app.schemas.financial_coach import CoachAction, CoachEvidence, CoachWarning
from app.schemas.financial_health import FinancialHealthProfile
from app.schemas.goal_planning import GoalPlanningOverview
from app.schemas.intelligence import IntelligencePeriod


class FinancialPlan(CoachingActionPlan):
    """Read-only plan, with original action IDs, shared goal pool and provenance.

    Amounts in actions retain their source meaning (e.g. a one-time reserve),
    while monthly allocations and existing timelines live in goal_planning.
    Priorities are interpretations, not additional allocations or instructions
    to execute payments. No clock-generated ID or timestamp affects equality.
    """

    planner_version: Literal["ai-16a-v1"] = "ai-16a-v1"
    planning_horizon: IntelligencePeriod
    priorities: list[CoachAction] = Field(default_factory=list)
    goal_planning: GoalPlanningOverview | None = None
    financial_health: FinancialHealthProfile | None = None
    evidence: list[CoachEvidence] = Field(default_factory=list)
    warnings: list[CoachWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_plan(self):
        horizon = self.planning_horizon
        if horizon.start != self.as_of_date or not 0 <= (horizon.end - horizon.start).days <= 366:
            raise ValueError("Planning horizon must start as of the plan and span zero to 366 days")
        if self.goal_planning and self.goal_planning.capacity.as_of_date != self.as_of_date:
            raise ValueError("Goal capacity date must match the plan")
        if self.financial_health and self.financial_health.as_of_date != self.as_of_date:
            raise ValueError("Financial health date must match the plan")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate planning evidence IDs")
        decisions = [item.action_id for item in self.priorities]
        if len(decisions) != len(set(decisions)):
            raise ValueError("Duplicate planning decision IDs")
        for item in self.priorities:
            if not item.evidence_ids or not set(item.evidence_ids) <= set(ids):
                raise ValueError("Every planning decision requires existing evidence")
        return self
