from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.financial_coach import (
    CoachAction,
    CoachClaim,
    CoachEvidence,
    CoachIntent,
    CoachRequest,
    CoachResponse,
    CoachWarning,
    EvidenceType,
)


def test_coach_request_accepts_valid_message():
    request = CoachRequest(
        message="Can I afford a laptop for 80000?",
    )

    assert request.message == "Can I afford a laptop for 80000?"
    assert request.conversation_id is None


def test_coach_request_rejects_empty_message():
    with pytest.raises(ValidationError):
        CoachRequest(message="")


def test_coach_request_rejects_overly_long_message():
    with pytest.raises(ValidationError):
        CoachRequest(message="x" * 4001)


def test_coach_intents_are_stable():
    assert CoachIntent.AFFORDABILITY.value == "affordability"
    assert CoachIntent.SPENDING_ANALYSIS.value == "spending_analysis"
    assert CoachIntent.SCENARIO_COMPARISON.value == "scenario_comparison"


def test_evidence_accepts_deterministic_financial_fact():
    evidence = CoachEvidence(
        evidence_id="cash_position_001",
        evidence_type=EvidenceType.DERIVED_FACT,
        source="account_position_engine",
        label="Current cash position",
        value=Decimal("145000"),
        unit="BDT",
        as_of_date=date(2026, 10, 25),
        observed_at=datetime(2026, 10, 25, 12, 0),
        confidence=Decimal("1"),
    )

    assert evidence.value == Decimal("145000")
    assert evidence.unit == "BDT"
    assert evidence.confidence == Decimal("1")


def test_evidence_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        CoachEvidence(
            evidence_id="invalid",
            evidence_type=EvidenceType.DERIVED_FACT,
            source="test",
            label="Invalid confidence",
            value=100,
            confidence=Decimal("1.1"),
        )


def test_claim_can_reference_evidence():
    claim = CoachClaim(
        claim_id="claim_001",
        text="Your projected cash is ৳83,000.",
        evidence_ids=["cash_projection_001"],
    )

    assert claim.evidence_ids == ["cash_projection_001"]


def test_action_priority_is_bounded():
    action = CoachAction(
        action_id="action_001",
        title="Review discretionary spending",
        description="Review non-essential expenses before making the purchase.",
        priority=2,
    )

    assert action.priority == 2


def test_action_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        CoachAction(
            action_id="action_001",
            title="Test",
            description="Test",
            priority=6,
        )


def test_complete_coach_response():
    response = CoachResponse(
        conversation_id="conversation_001",
        intent=CoachIntent.AFFORDABILITY,
        answer="You can probably afford this purchase, but it would reduce your cash buffer.",
        summary="The purchase is possible but should be considered carefully.",
        claims=[
            CoachClaim(
                claim_id="claim_001",
                text="Projected cash after purchase is ৳83,000.",
                evidence_ids=["projection_001"],
            )
        ],
        evidence=[
            CoachEvidence(
                evidence_id="projection_001",
                evidence_type=EvidenceType.DERIVED_FACT,
                source="affordability_engine",
                label="Projected cash after purchase",
                value=Decimal("83000"),
                unit="BDT",
                as_of_date=date(2026, 10, 25),
            )
        ],
        actions=[
            CoachAction(
                action_id="action_001",
                title="Preserve your cash buffer",
                description="Consider delaying the purchase if you expect additional obligations.",
                priority=2,
                evidence_ids=["projection_001"],
            )
        ],
        warnings=[],
        limitations=[],
    )

    assert response.intent == CoachIntent.AFFORDABILITY
    assert len(response.claims) == 1
    assert len(response.evidence) == 1
    assert len(response.actions) == 1


def test_warning_is_structured():
    warning = CoachWarning(
        code="INSUFFICIENT_DATA",
        message="There is not enough recurring income history.",
    )

    assert warning.code == "INSUFFICIENT_DATA"