from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CoachIntent(str, Enum):
    """High-level financial questions the coach can route."""

    SPENDING_ANALYSIS = "spending_analysis"
    CASHFLOW = "cashflow"
    AFFORDABILITY = "affordability"
    SAVINGS = "savings"
    GOAL_PLANNING = "goal_planning"
    SCENARIO_COMPARISON = "scenario_comparison"
    ALERT_EXPLANATION = "alert_explanation"
    FINANCIAL_HEALTH = "financial_health"
    GENERAL_FINANCE = "general_finance"
    UNKNOWN = "unknown"


class CoachRequest(BaseModel):
    """Input received from the frontend."""

    message: str = Field(
        min_length=1,
        max_length=4000,
        description="The user's natural-language financial question.",
    )

    conversation_id: str | None = Field(
        default=None,
        description="Existing conversation identifier, if available.",
    )


class EvidenceType(str, Enum):
    """Types of deterministic evidence that may support a coach answer."""

    RAW_DATA = "raw_data"
    DERIVED_FACT = "derived_fact"
    ESTIMATE = "estimate"
    INTERPRETATION = "interpretation"


class CoachEvidence(BaseModel):
    """
    A traceable piece of information used to support a coach answer.

    Financial numbers should come from deterministic services, not from
    the language model.
    """

    evidence_id: str = Field(description="Stable identifier for this evidence item.")

    evidence_type: EvidenceType

    source: str = Field(description="The deterministic service or subsystem that produced it.")

    label: str = Field(description="Human-readable description of the evidence.")

    value: Any = Field(description="The underlying value.")

    unit: str | None = Field(
        default=None,
        description="Unit such as BDT, percent, days, or count.",
    )

    as_of_date: date | None = None

    observed_at: datetime | None = None

    confidence: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("1"),
    )


class CoachClaim(BaseModel):
    """A financial claim made in the final answer."""

    claim_id: str

    text: str

    evidence_ids: list[str] = Field(default_factory=list)


class CoachAction(BaseModel):
    """An actionable recommendation presented to the user."""

    action_id: str

    title: str

    description: str

    priority: int = Field(
        default=1,
        ge=1,
        le=5,
    )

    evidence_ids: list[str] = Field(default_factory=list)


class CoachWarning(BaseModel):
    """Important caveat or safety warning."""

    code: str

    message: str


class CoachResponse(BaseModel):
    """
    Canonical response returned by the financial coach.

    This is intentionally structured instead of returning arbitrary LLM text.
    """

    conversation_id: str | None = None

    intent: CoachIntent

    answer: str

    summary: str | None = None

    claims: list[CoachClaim] = Field(default_factory=list)

    evidence: list[CoachEvidence] = Field(default_factory=list)

    actions: list[CoachAction] = Field(default_factory=list)

    warnings: list[CoachWarning] = Field(default_factory=list)

    limitations: list[str] = Field(default_factory=list)