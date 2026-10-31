from decimal import Decimal
from typing import Literal

from app.schemas.coaching import CoachingType

from pydantic import BaseModel, Field


class CoachingEffectivenessCounts(BaseModel):
    total_recommendations: int = Field(ge=0)
    acted_on: int = Field(ge=0)
    dismissed: int = Field(ge=0)
    not_relevant: int = Field(ge=0)
    snoozed: int = Field(ge=0)

    measurable_outcomes: int = Field(ge=0)
    improved: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    worsened: int = Field(ge=0)
    insufficient_data: int = Field(ge=0)


class CoachingEffectivenessRates(BaseModel):
    observable_outcome_rate: Decimal | None = None
    improvement_rate_among_observed: Decimal | None = None
    worsening_rate_among_observed: Decimal | None = None


class CoachingEffectivenessTypeBreakdown(BaseModel):
    recommendation_type: CoachingType

    total_recommendations: int = Field(ge=0)
    acted_on: int = Field(ge=0)
    measurable_outcomes: int = Field(ge=0)

    improved: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    worsened: int = Field(ge=0)
    insufficient_data: int = Field(ge=0)

    observable_outcome_rate: Decimal | None = None
    improvement_rate_among_observed: Decimal | None = None
    worsening_rate_among_observed: Decimal | None = None

class CoachingEffectivenessResponse(BaseModel):
    counts: CoachingEffectivenessCounts
    rates: CoachingEffectivenessRates
    by_type: list[CoachingEffectivenessTypeBreakdown]

    causal_claim: Literal[False] = False

    limitations: list[str]