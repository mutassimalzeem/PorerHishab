"""Computed action plan; completion is an explicit user report only."""
from datetime import date
from typing import Literal
from decimal import Decimal
from pydantic import BaseModel
from app.schemas.coaching import CoachingType, CoachingPriority, CoachingFeedbackRecord


class CoachingAction(BaseModel):
    id: str
    recommendation_id: str
    type: CoachingType
    priority: CoachingPriority
    rank: int
    title: str
    description: str
    recommended_action: str
    amount: Decimal | None
    currency: Literal["BDT"]
    status: Literal["active"] = "active"
    source: Literal["financial_runway", "scheduled_cashflow", "category_spending", "goal_assessment"]
    evidence_quality: Literal["recorded", "estimated", "limited"]
    subject: str | None
    assumptions: list[str]
    limitations: list[str]


class CompletedActionFeedback(CoachingFeedbackRecord):
    action_status: Literal["reported_done"] = "reported_done"


class CoachingActionPlan(BaseModel):
    as_of_date: date
    data_status: Literal["sufficient", "partial", "insufficient_data"]
    actions: list[CoachingAction]
    completed_feedback: list[CompletedActionFeedback]
    active_count: int
    completed_count: int
    assumptions: list[str]
    limitations: list[str]
