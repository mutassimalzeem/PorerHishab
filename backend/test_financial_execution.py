from datetime import date

import pytest

from app.schemas.coaching import CoachingPriority
from app.schemas.financial_coach import CoachEvidence, EvidenceType
from app.schemas.financial_execution import FinancialActionStep, FinancialExecutionPlan
from app.schemas.financial_plan import FinancialDecisionSet, FinancialPriority
from app.schemas.intelligence import IntelligencePeriod
from app.services.finance.financial_execution import build_financial_execution_plan


AS_OF = date(2026, 10, 31)
PERIOD = IntelligencePeriod(
    kind="month",
    start=AS_OF,
    end=date(2026, 11, 30),
    is_complete=False,
    label="October 2026",
)


def evidence(evidence_id: str = "ev_cash") -> CoachEvidence:
    return CoachEvidence(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.DERIVED_FACT,
        source="cashflow",
        label="Projected cashflow constraint",
        value="constraint",
        as_of_date=AS_OF,
    )


def decision_set(priorities: list[FinancialPriority]) -> FinancialDecisionSet:
    return FinancialDecisionSet(
        as_of_date=AS_OF,
        planning_horizon=PERIOD,
        data_status="sufficient",
        priorities=priorities,
        evidence=[evidence()],
    )


def priority(
    priority_id: str,
    category: str,
    level: CoachingPriority = "high",
    blocking: list[str] | None = None,
    factors: list[str] | None = None,
) -> FinancialPriority:
    return FinancialPriority(
        priority_id=priority_id,
        category=category,
        level=level,
        title=priority_id,
        reason="cashflow_constraint" if category == "cashflow_risk" else "spending_increase",
        evidence_ids=["ev_cash"],
        evidence_quality="derived",
        blocking_priority_ids=blocking or [],
        blocking_factors=factors or [],
    )


def test_maps_priority_categories_to_execution_steps():
    decisions = decision_set([
        priority("p_cash", "cashflow_risk"),
        priority("p_spend", "spending_review", blocking=["p_cash"]),
        priority("p_save", "savings_opportunity", level="medium", blocking=["p_spend"]),
    ])

    result = build_financial_execution_plan(decisions)

    assert isinstance(result, FinancialExecutionPlan)
    assert [step.kind for step in result.steps] == [
        "review_cashflow", "review_spending", "review_savings"
    ]
    assert [step.sequence for step in result.steps] == [1, 2, 3]
    assert result.steps[0].state == "ready"
    assert result.steps[1].state == "blocked"
    assert result.steps[2].state == "blocked"
    assert result.steps[2].blocking_priority_ids == ["p_spend"]


def test_execution_plan_preserves_source_provenance():
    decisions = decision_set([
        priority("p1", "cashflow_risk"),
    ])
    decisions.priorities[0].source_action_ids = ["action_123"]
    decisions.priorities[0].assumptions = ["Forecast uses recorded history"]
    decisions.priorities[0].limitations = ["Future income is uncertain"]

    result = build_financial_execution_plan(decisions)
    step = result.steps[0]

    assert step.source_action_ids == ["action_123"]
    assert step.evidence_ids == ["ev_cash"]
    assert step.assumptions == ["Forecast uses recorded history"]
    assert step.limitations == ["Future income is uncertain"]
    assert result.evidence[0].evidence_id == "ev_cash"


def test_unknown_capacity_is_blocked_without_becoming_zero():
    decisions = decision_set([
        priority(
            "p_goal",
            "goal_review",
            level="medium",
            factors=["goal_capacity_unknown"],
        ),
    ])

    result = build_financial_execution_plan(decisions)

    assert result.steps[0].state == "blocked"
    assert result.steps[0].blocking_factors == ["goal_capacity_unknown"]


def test_no_step_can_be_created_without_source_evidence():
    from app.schemas.financial_execution import FinancialActionStep

    interpretation_only = CoachEvidence(
        evidence_id="ev_interpretation",
        evidence_type=EvidenceType.INTERPRETATION,
        source="policy",
        label="Policy interpretation only",
        value="Review this issue",
        as_of_date=AS_OF,
    )

    with pytest.raises(ValueError, match="source evidence"):
        FinancialExecutionPlan(
            as_of_date=AS_OF,
            planning_horizon=PERIOD,
            data_status="sufficient",
            steps=[
                FinancialActionStep(
                    step_id="step_1_p1",
                    priority_id="p1",
                    sequence=1,
                    kind="review_cashflow",
                    level="high",
                    title="Cashflow",
                    description="Review cashflow",
                    evidence_ids=["ev_interpretation"],
                    state="ready",
                )
            ],
            evidence=[interpretation_only],
        )


def test_execution_is_non_mutating():
    decisions = decision_set([priority("p1", "cashflow_risk")])
    original = decisions.model_dump(mode="json")

    build_financial_execution_plan(decisions)

    assert decisions.model_dump(mode="json") == original


def test_dependency_order_is_enforced_by_contract():
    with pytest.raises(ValueError, match="dependencies"):
        FinancialExecutionPlan(
            as_of_date=AS_OF,
            planning_horizon=PERIOD,
            data_status="sufficient",
            steps=[
                {
                    "step_id": "step_1_p2",
                    "priority_id": "p2",
                    "sequence": 1,
                    "kind": "review_savings",
                    "level": "medium",
                    "title": "Savings",
                    "description": "Review savings",
                    "evidence_ids": ["ev_cash"],
                    "blocking_priority_ids": ["p1"],
                    "state": "blocked",
                },
            ],
            evidence=[evidence()],
        )


def test_money_values_are_not_created_by_execution_layer():
    decisions = decision_set(
        [priority("p1", "savings_opportunity", level="medium")]
    )
    result = build_financial_execution_plan(decisions)

    # Check the schema, not a fallback value that defaults to Decimal("0").
    assert "amount" not in FinancialActionStep.model_fields

    # Also ensure no amount is emitted in serialized output.
    for step in result.steps:
        assert "amount" not in step.model_dump()
