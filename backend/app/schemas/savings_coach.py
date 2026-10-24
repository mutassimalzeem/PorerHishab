
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.planner import SavingsPlanResponse


ActionPriority = Literal["high", "medium", "low"]


class SavingsAction(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    action: str = Field(min_length=10, max_length=400)
    reason: str = Field(min_length=10, max_length=400)
    priority: ActionPriority


class SavingsActionDrafts(BaseModel):
    """LLM-generated action text; financial amounts come from Python."""

    actions: list[SavingsAction] = Field(default_factory=list, max_length=5)


class SavingsCoachResponse(BaseModel):
    plan: SavingsPlanResponse
    actions: list[SavingsAction] = Field(default_factory=list, max_length=5)
