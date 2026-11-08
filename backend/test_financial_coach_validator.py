"""Unit tests for evidence-grounded response validation (AI-15S-E / AI-15S-K)."""

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
    contains_unverified_spelled_money,
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
        CoachEvidence(
            evidence_id="ev_projected_savings",
            evidence_type=EvidenceType.ESTIMATE,
            source="forecast_engine",
            label="Projected monthly savings",
            value=D("3000.00"),
            unit="BDT",
            as_of_date=DAY,
            observed_at=NOW,
            confidence=D("0.80"),
        ),
    ]
    return EvidencePackage(
        intent=CoachIntent.SPENDING_ANALYSIS,
        as_of_date=DAY,
        evidence=evidence,
        limitations=["Recorded data only."],
        missing_data=["recurring_income"],
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
    assert validated.actions[0].action_type == "personalized"


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
    # The claim cited 15,000 BDT which is not in evidence; validator safely falls back
    assert report.repaired
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


def test_guarantee_language_gets_caveat_and_repair(evidence_package):
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
    assert report.repaired
    assert "guaranteed" not in validated.answer
    assert "projected" in validated.answer
    assert any(w.code == "UNSUPPORTED_GUARANTEE_CAVEAT" for w in validated.warnings)


def test_unsupported_amount_in_answer_while_claims_valid(evidence_package):
    """When claims are grounded but answer introduces an unsupported amount (e.g. 99,000 BDT),
    it must be rejected and safely fall back to the deterministic answer."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="Your spending was 12,000 BDT and your secret balance is 99,000 BDT.",
        summary="Recorded spending was 12,000 BDT.",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert not report.is_valid
    assert report.repaired
    assert "99,000" not in validated.answer
    assert "99000" not in validated.answer
    # Safe fallback with verified spending numbers is returned
    assert "12000" in validated.answer


def test_unsupported_amount_in_summary(evidence_package):
    """When the summary contains a hallucinated figure (e.g. 75,000 BDT), it must be repaired."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total.",
        summary="Overall expenses reached 75,000 BDT this month.",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.repaired
    assert validated.summary is None or "75,000" not in validated.summary
    # The valid answer remains intact
    assert "12,000 BDT" in validated.answer


def test_unsupported_amount_in_action_description(evidence_package):
    """Action description asserting an unsupported figure (e.g. 40,000 BDT) must be dropped."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total.",
        summary="Total: 12,000 BDT",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[
            CoachAction(
                action_id="act_bad_amount",
                title="Transfer surplus",
                description="Immediately transfer 40,000 BDT to your savings deposit.",
                priority=1,
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.repaired
    assert report.dropped_actions_count == 1
    assert len(validated.actions) == 0


def test_valid_amount_supported_by_correct_evidence(evidence_package):
    """An action citing 5,000 BDT supported by the top category evidence is accepted."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total, with 5,000 BDT on Food.",
        summary="Total: 12,000 BDT",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[
            CoachAction(
                action_id="act_food",
                title="Review Food expenses",
                description="Your food spending was 5,000 BDT; try meal planning.",
                priority=2,
                evidence_ids=["ev_spending_top_category"],
            )
        ],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.is_valid
    assert len(validated.actions) == 1
    assert validated.actions[0].action_type == "personalized"


def test_valid_amount_supported_only_by_unrelated_evidence(evidence_package):
    """A claim citing 12,000 BDT for savings, but referencing only the savings evidence (3,000 BDT),
    must be rejected because 12,000 BDT belongs only to the unrelated total expenses evidence."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="Your savings were 12,000 BDT.",
        claims=[
            CoachClaim(
                claim_id="cl_mismatched",
                text="You saved 12,000 BDT this month.",
                evidence_ids=["ev_projected_savings"],  # Only supports 3000, not 12000!
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.repaired
    assert report.dropped_claims_count == 1
    # Fallback response is returned because the only claim failed relevant grounding
    assert "12000" in validated.answer


def test_estimate_presented_as_guaranteed_fact(evidence_package):
    """When a claim cites an estimate but uses guarantee phrasing, it must be rejected."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="Your spending was 12,000 BDT.",
        claims=[
            CoachClaim(
                claim_id="cl_valid",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
            CoachClaim(
                claim_id="cl_guaranteed_estimate",
                text="You are 100% guaranteed to save 3,000 BDT next month.",
                evidence_ids=["ev_projected_savings"],
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


def test_missing_evidence_and_unavailable_values_not_zero(evidence_package):
    """Missing recurring income must not be claimed as 0 BDT."""
    evidence_package.evidence.append(
        CoachEvidence(
            evidence_id="ev_missing_income",
            evidence_type=EvidenceType.RAW_DATA,
            source="income_tracker",
            label="Recurring income",
            value=None,  # Missing / unavailable
            unit="BDT",
        )
    )

    validator = FinancialCoachValidator(evidence_package)
    # Missing value must NOT have produced Decimal(0) in supported numbers
    ev_nums = validator.evidence_numbers_by_id["ev_missing_income"]
    assert D("0") not in ev_nums

    # A claim asserting recurring income is 0 BDT must fail grounding
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total.",
        claims=[
            CoachClaim(
                claim_id="cl_zero_income",
                text="Your recurring income was 0 BDT.",
                evidence_ids=["ev_missing_income"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validator.validate(response)
    assert report.dropped_claims_count == 1


def test_multiple_supported_and_unsupported_figures(evidence_package):
    """In a mixed response, supported items are retained and unsupported items are dropped."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total.",
        summary="Total: 12,000 BDT",
        claims=[
            CoachClaim(
                claim_id="cl_supported",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
            CoachClaim(
                claim_id="cl_unsupported",
                text="You spent 44,000 BDT on dining.",
                evidence_ids=["ev_spending_top_category"],
            ),
        ],
        evidence=evidence_package.evidence,
        actions=[
            CoachAction(
                action_id="act_supported",
                title="Review Food budget",
                description="Food expenses are 5,000 BDT.",
                priority=1,
                evidence_ids=["ev_spending_top_category"],
            ),
            CoachAction(
                action_id="act_unsupported",
                title="Invest surplus",
                description="Invest 80,000 BDT into mutual funds.",
                priority=2,
                evidence_ids=["ev_spending_total_expenses"],
            ),
        ],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.repaired
    assert report.dropped_claims_count == 1
    assert report.dropped_actions_count == 1
    assert len(validated.claims) == 1
    assert validated.claims[0].claim_id == "cl_supported"
    assert len(validated.actions) == 1
    assert validated.actions[0].action_id == "act_supported"


def test_action_validation_empty_invalid_mixed_valid_evidence(evidence_package):
    """Test action classification: valid, empty evidence, invalid evidence, and mixed validity."""
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total.",
        summary="Total: 12,000 BDT",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            )
        ],
        evidence=evidence_package.evidence,
        actions=[
            # Valid personalized
            CoachAction(
                action_id="act_valid",
                title="Review Food",
                description="Consider reducing dining expenses.",
                priority=2,
                evidence_ids=["ev_spending_top_category"],
            ),
            # Empty evidence IDs without amounts -> general guidance
            CoachAction(
                action_id="act_general",
                title="Track your receipts",
                description="Record daily expenses to keep cashflow visibility accurate.",
                priority=3,
                evidence_ids=[],
            ),
            # Empty evidence IDs with explicit amounts -> unsupported, dropped
            CoachAction(
                action_id="act_empty_with_amt",
                title="Save cash",
                description="Set aside 25,000 BDT today.",
                priority=1,
                evidence_ids=[],
            ),
            # Invalid unknown evidence ID -> dropped
            CoachAction(
                action_id="act_unknown_id",
                title="Check investments",
                description="Review portfolio allocation.",
                priority=2,
                evidence_ids=["ev_nonexistent_fund_id"],
            ),
            # Mixed validity -> contains unknown ID -> dropped
            CoachAction(
                action_id="act_mixed",
                title="Mixed advice",
                description="Review food and mystery funds.",
                priority=2,
                evidence_ids=["ev_spending_top_category", "ev_unknown_id_xyz"],
            ),
        ],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.dropped_actions_count == 3
    assert len(validated.actions) == 2

    # Verify classifications
    actions_by_id = {a.action_id: a for a in validated.actions}
    assert actions_by_id["act_valid"].action_type == "personalized"
    assert actions_by_id["act_general"].action_type == "general_guidance"


def test_validation_does_not_mutate_input_objects(evidence_package):
    """Validation must never mutate the original caller response, claim, or action objects."""
    orig_action = CoachAction(
        action_id="act_general",
        title="General advice",
        description="Save regularly for emergencies.",
        priority=1,
        evidence_ids=[],
        action_type="personalized",
    )
    orig_claim = CoachClaim(
        claim_id="cl_1",
        text="Total: 12,000 BDT.",
        evidence_ids=["ev_spending_total_expenses"],
    )
    orig_response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT.",
        summary="Summary 12,000 BDT",
        claims=[orig_claim],
        evidence=evidence_package.evidence,
        actions=[orig_action],
    )

    validated, _ = validate_coach_response(orig_response, evidence_package)

    # Original action remains untouched
    assert orig_action.action_type == "personalized"
    # Validated copy has been classified
    assert validated.actions[0].action_type == "general_guidance"
    assert validated.actions[0] is not orig_action


def test_spelled_out_taka_amount_is_rejected():
    assert contains_unverified_spelled_money(
        "You could save one thousand taka."
    )


def test_numeric_taka_amount_uses_existing_numeric_validator():
    assert not contains_unverified_spelled_money(
        "You could save 1000 taka."
    )


def test_spelled_out_money_in_answer_triggers_fallback(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You could save one thousand taka by cutting dining out.",
        summary="Summary text.",
        claims=[],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert not report.is_valid
    assert report.repaired
    assert (
        "Answer contains a spelled-out monetary amount that cannot be independently verified."
        in report.issues
    )


def test_spelled_out_money_in_summary_removes_summary(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total, with 5,000 BDT on Food.",
        summary="You could save fifty taka tomorrow.",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Your total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert validated.summary is None
    assert report.repaired
    assert any("Summary contains a spelled-out monetary amount" in issue for issue in report.issues)


def test_spelled_out_money_in_claim_drops_claim(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total, with 5,000 BDT on Food.",
        claims=[
            CoachClaim(
                claim_id="cl_valid",
                text="Your total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
            CoachClaim(
                claim_id="cl_spelled",
                text="You could save one thousand taka.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
        ],
        evidence=evidence_package.evidence,
        actions=[],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.dropped_claims_count == 1
    assert len(validated.claims) == 1
    assert validated.claims[0].claim_id == "cl_valid"


def test_spelled_out_money_in_action_drops_action(evidence_package):
    response = CoachResponse(
        intent=CoachIntent.SPENDING_ANALYSIS,
        answer="You spent 12,000 BDT in total, with 5,000 BDT on Food.",
        claims=[
            CoachClaim(
                claim_id="cl_valid",
                text="Your total spending was 12,000 BDT.",
                evidence_ids=["ev_spending_total_expenses"],
            ),
        ],
        evidence=evidence_package.evidence,
        actions=[
            CoachAction(
                action_id="act_spelled",
                title="Save money",
                description="Try to save five hundred taka this week.",
                priority=1,
                evidence_ids=["ev_spending_top_category"],
            ),
        ],
    )

    validated, report = validate_coach_response(response, evidence_package)
    assert report.dropped_actions_count == 1
    assert len(validated.actions) == 0


@pytest.mark.parametrize("answer", [
    "Your available cash is BDT zero.",
    "Your available cash is zero.",
    "Your bank balance is nil.",
    "Your available cash is approximately zero.",
    "Your account balance is currently five thousand.",
    "আপনার নগদ শূন্য টাকা।",
])
def test_word_amount_variants_fail_closed(evidence_package, answer):
    response = CoachResponse(intent=CoachIntent.SPENDING_ANALYSIS, answer=answer, claims=[], actions=[], evidence=evidence_package.evidence)
    validated, report = validate_coach_response(response, evidence_package)
    assert not report.is_valid
    assert validated.answer != answer
