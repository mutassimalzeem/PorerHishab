"""Unit tests for evidence-grounded response validation (AI-15S-E)."""

from datetime import date, datetime, timezone
from decimal import Decimal as D
import pytest

from app.schemas.financial_coach import (
    CoachAction,
    CoachClaim,
    CoachEvidence,
    CoachIntent,
    CoachResponse,
    CoachWarning,
    EvidenceType,
)
from app.services.finance.financial_coach_evidence import EvidencePackage
from app.services.finance.financial_coach_validator import (
    FinancialCoachValidator,
    validate_coach_response,
)

DAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def evidence_package():
    evidence = [
        CoachEvidence(
            evidence_id="ev_spending_total_expenses",
            evidence_type=EvidenceType.DERIVED_FACT,
            source="intelligence_facts.totals",
            label="Total expenses",
            value=D("12000.00"),
            unit="BDT",
            as_of_date=DAY,
            observed_at=NOW,
            confidence=D("1.0"),
        ),
        CoachEvidence(
            evidence_id="ev_spending_top_category",
            evidence_type=EvidenceType.INTERPRETATION,
            source="intelligence_facts.grouped_expenses",
            label="Top category",
            value={"category": "Food", "amount": D("5000.00")},
            unit="BDT",
            as_of_date=DAY,
            observed_at=NOW,
            confidence=D("0.95"),
        ),
    ]
    return EvidencePackage(
        intent=CoachIntent.SPENDING_ANALYSIS,
        as_of_date=DAY,
        evidence=evidence,
        limitations=["Recorded data only."],
    )


def test_valid_response_passes(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total, with 5,000 BDT on Food.",
        summary="Total: 12,000 BDT",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Your total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
            CoachClaim(
                claim_id="cl_2",
                text="Food spending was 5,000 BDT.",
                evidence_ids=["ev_spending_top_category"],
            ),
        ],
        evidence=evidence_package.evidence,
        actions=[
            CoachAction(
                action_id="act_1",
                title="Review dining",
                description="Check food items.",
                priority=2,
                evidence_ids=["ev_spending_top_category"],
            )
        ],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.is_valid
    assert not report.repaired
    assert len(validated.claims) == 2
    assert len(validated.actions) == 1


def test_unknown_evidence_id_dropped(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT.",
        claims=[
            CoachClaim(
                claim_id="cl_valid",
                text="Total was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
            CoachClaim(
                claim_id="cl_hallucinated",
                text="You have a secret balance.",
                evidence_ids=["ev_hallucinated_balance_id"],
            ),
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.repaired
    assert report.dropped_claims_count == 1
    assert len(validated.claims) == 1
    assert validated.claims[0].claim_id == "cl_valid"


def test_numerical_contradiction_rejected(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 15,000 BDT on Food.",
        claims=[
            CoachClaim(
                claim_id="cl_contradiction",
                text="Total spending was 15,000 BDT.",  # Contradicts evidence value 12000
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    # The claim cited 15,000 BDT which is not in evidence; since it was the only claim,
    # validator safely falls back to deterministic generator
    assert report.repaired
    assert report.dropped_claims_count == 1
    assert "12000" in validated.answer


def test_executed_action_phrasing_fallback(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="I have paid your electricity bill and transferred 12,000 BDT.",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total: 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert not report.is_valid
    assert report.repaired
    # Execution language must be completely replaced
    assert "I have paid" not in validated.answer
    assert any(w.code == "VALIDATION_REPAIRED_LANGUAGE" for w in validated.warnings)


def test_guarantee_language_gets_caveat(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="Your balance is guaranteed to increase next month.",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert any(w.code == "UNSUPPORTED_GUARANTEE_CAVEAT" for w in validated.warnings)
