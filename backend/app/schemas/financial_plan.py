"""Composed AI-16A plans and evidence-linked AI-16B financial decisions."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.action_plan import CoachingActionPlan
from app.schemas.coaching import CoachingPriority
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


PriorityCategory = Literal[
    "cashflow_risk", "obligation_pressure", "liquidity_risk", "goal_commitment",
    "goal_review", "spending_review", "savings_opportunity", "capacity_review",
]
PriorityReason = Literal[
    "cashflow_constraint", "known_obligations", "liquidity_constraint",
    "accepted_commitment", "active_goal", "source_goal_risk", "spending_increase",
    "unassigned_savings", "commitments_exceed_capacity", "capacity_unavailable",
]
ConflictReason = Literal[
    "stabilize_cashflow", "protect_obligations", "review_reserves",
    "review_accepted_commitments", "resolve_capacity", "review_spending_before_savings",
]


class FinancialPriority(BaseModel):
    """An issue to review, never a new allocation or an executed financial action."""

    model_config = ConfigDict(extra="forbid")
    priority_id: str
    category: PriorityCategory
    level: CoachingPriority
    title: str
    reason: PriorityReason
    source_action_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    evidence_quality: Literal["recorded", "derived", "estimated", "limited"]
    blocking_priority_ids: list[str] = Field(default_factory=list)
    blocking_factors: list[Literal["goal_capacity_unknown", "goal_not_feasible"]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PriorityConflict(BaseModel):
    """Explicit precedence; review order alone does not prove a funding deficit."""

    model_config = ConfigDict(extra="forbid")
    preceding_priority_id: str
    deferred_priority_id: str
    kind: Literal["funding_constraint", "review_precedence"]
    reason: ConflictReason


class FinancialDecisionSet(BaseModel):
    """AI-16B ordered issues over an unmodified AI-16A plan."""

    model_config = ConfigDict(extra="forbid")
    policy_version: Literal["ai-16b-v1"] = "ai-16b-v1"
    source_planner_version: Literal["ai-16a-v1"] = "ai-16a-v1"
    as_of_date: date
    planning_horizon: IntelligencePeriod
    data_status: Literal["sufficient", "partial", "insufficient_data"]
    priorities: list[FinancialPriority] = Field(default_factory=list)
    conflicts: list[PriorityConflict] = Field(default_factory=list)
    evidence: list[CoachEvidence] = Field(default_factory=list)
    goal_planning: GoalPlanningOverview | None = None
    warnings: list[CoachWarning] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent_decisions(self):
        horizon = self.planning_horizon
        if horizon.start != self.as_of_date or not 0 <= (horizon.end - horizon.start).days <= 366:
            raise ValueError("Invalid decision horizon")
        if self.goal_planning and self.goal_planning.capacity.as_of_date != self.as_of_date:
            raise ValueError("Goal planning date must match decisions")
        ids = [p.priority_id for p in self.priorities]
        evidence_ids = [e.evidence_id for e in self.evidence]
        if len(ids) != len(set(ids)) or len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Duplicate priority or evidence IDs")
        if any(e.as_of_date is not None and e.as_of_date != self.as_of_date for e in self.evidence):
            raise ValueError("Decision evidence date must match decisions")
        positions = {key: position for position, key in enumerate(ids)}
        evidence = {e.evidence_id: e for e in self.evidence}
        for priority in self.priorities:
            if not set(priority.evidence_ids) <= evidence.keys():
                raise ValueError("Unknown priority evidence IDs")
            support = [evidence[key] for key in priority.evidence_ids]
            if not any(e.evidence_type != "interpretation" for e in support):
                raise ValueError("Source evidence is required, beyond policy interpretation")
            if any(e.as_of_date != self.as_of_date for e in support):
                raise ValueError("Supporting evidence date must match decisions")
            if len(priority.blocking_priority_ids) != len(set(priority.blocking_priority_ids)):
                raise ValueError("Duplicate dependency IDs")
            for blocker in priority.blocking_priority_ids:
                if blocker not in positions or positions[blocker] >= positions[priority.priority_id]:
                    raise ValueError("Dependencies must exist earlier in the priority order")
        pairs = [(c.preceding_priority_id, c.deferred_priority_id) for c in self.conflicts]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Duplicate conflicts")
        by_id = {p.priority_id: p for p in self.priorities}
        for conflict in self.conflicts:
            if (conflict.deferred_priority_id not in by_id or
                    conflict.preceding_priority_id not in by_id[conflict.deferred_priority_id].blocking_priority_ids):
                raise ValueError("Conflict must identify an existing dependency")
        return self
