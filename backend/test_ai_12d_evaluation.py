"""AI-12D offline evaluation tests: savings recommendations + proactive insights.

Both evaluations run the deterministic pipeline against seeded controlled
worlds and compare *structured financial properties* with expectations
derived independently of the system under test. No provider call is
reachable and no wording is ever compared.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.evaluation.datasets.insight_scenarios import (
    GOAL_PROGRESS,
    INSIGHT_EVALUATION_CASES,
    KNOWN_INSIGHT_TYPES,
    PROJECTED_SHORTFALL,
    SAVINGS_OPPORTUNITY,
    UNUSUAL_SPENDING,
    UNUSUAL_TRIGGERED,
    UPCOMING_EXPENSE,
    validate_insight_dataset,
)
from app.evaluation.datasets.recommendation_cases import (
    COACH_CASES,
    COACH_INCREASED_CASE,
    COACH_TWO_MONTHS_CASE,
    PLAN_AT_RISK_CASE,
    PLAN_CASES,
    PLAN_INSUFFICIENT_CASE,
    validate_recommendation_dataset,
)
from app.evaluation.insight_runner import (
    run_insight_case_with_outcome,
    run_insight_dataset,
)
from app.evaluation.recommendation_runner import (
    run_coach_case_with_outcome,
    run_plan_case,
    run_plan_case_with_outcome,
    run_recommendation_dataset,
)
from app.services.planning.savings import calculate_savings_plan


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    from app.core.database import Base
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Evaluation must never reach a provider, even if one is configured."""
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)


# ----------------------------------------------------------------- datasets


def test_recommendation_dataset_is_self_consistent():
    problems = validate_recommendation_dataset()
    assert problems == [], problems
    ids = [case.case_id for case in PLAN_CASES + COACH_CASES]
    assert len(ids) == len(set(ids))


def test_insight_dataset_is_self_consistent_and_covers_all_types():
    problems = validate_insight_dataset()
    assert problems == [], problems
    ids = [case.case_id for case in INSIGHT_EVALUATION_CASES]
    assert len(ids) == len(set(ids))
    for insight_type in KNOWN_INSIGHT_TYPES:
        assert any(spec.type == insight_type and spec.count > 0
                   for case in INSIGHT_EVALUATION_CASES for spec in case.expected)


def test_both_datasets_are_sensitive_to_wrong_pins(db):
    mutated_fields = tuple(
        ("required_monthly_saving", "11000") if key == "required_monthly_saving"
        else (key, pinned)
        for key, pinned in PLAN_AT_RISK_CASE.expected_fields)
    mutated = replace(PLAN_AT_RISK_CASE, expected_fields=mutated_fields)
    report = run_recommendation_dataset(db, plan_cases=(mutated,))
    assert not report.passed
    failed = report.results[0]
    assert any(failure.startswith("grounding:") for failure in failed.failures)

    arithmetic_mutated = replace(
        PLAN_AT_RISK_CASE,
        scenario=replace(PLAN_AT_RISK_CASE.scenario, transactions=(
            tx for tx in PLAN_AT_RISK_CASE.scenario.transactions
            if tx.date != date(2026, 9, 14))))
    report = run_recommendation_dataset(db, plan_cases=(arithmetic_mutated,))
    assert not report.passed
    failed = next(result for result in report.results
                  if result.case_id == arithmetic_mutated.case_id)
    assert any(failure.startswith("arithmetic:") for failure in failed.failures), failed.failures

    broken_expectation = tuple(
        replace(spec, count=0) if spec.type == UNUSUAL_SPENDING else spec
        for spec in UNUSUAL_TRIGGERED)
    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_unusual_spending_triggered")
    result, _outcome = run_insight_case_with_outcome(
        db, replace(case, expected=broken_expectation))
    assert not result.passed
    assert any("presence:" in failure for failure in result.failures)
    # The insight still appears, so a zero-count expectation classifies it as
    # a false positive; a missing one would have been a false negative.
    assert _outcome.type_results[UNUSUAL_SPENDING] in ("fn", "fp")


def test_dataset_rebuilding_detects_internal_number_drift():
    """Pins whose literals drift from the scenario spec must fail hygiene."""
    from app.evaluation.datasets.insight_scenarios import insight_ground_truth_consistency

    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_unusual_spending_triggered")
    broken_expectation = tuple(
        replace(spec,
                evidence_sets=((("current_expenses", "9999.00"),
                                ("largest_prior_month", "4000.00")),))
        if spec.type == UNUSUAL_SPENDING else spec
        for spec in case.expected)
    broken_case = replace(case, expected=broken_expectation)
    seeded_cases = tuple(
        broken_case if original.case_id == case.case_id else original
        for original in INSIGHT_EVALUATION_CASES)
    problems = insight_ground_truth_consistency(seeded_cases)
    assert any("current_expenses" in problem for problem in problems)


# ------------------------------------------------- savings recommendations


def test_full_recommendation_report_passes(db, capsys):
    from app.evaluation.recommendation_metrics import format_recommendation_report

    report = run_recommendation_dataset(db)
    print(format_recommendation_report(report))
    assert report.passed, format_recommendation_report(report)
    metrics = report.metrics
    assert metrics["grounding_accuracy"] == 100.0
    assert metrics["arithmetic_accuracy"] == 100.0
    assert metrics["arithmetic_passed"] > 0
    assert metrics["estimate_labeling_rate"] == 100.0
    assert metrics["no_double_counting_rate"] == 100.0
    assert metrics["personalization_rate"] == 100.0
    assert metrics["data_sufficiency_rate"] == 100.0
    assert metrics["isolation_violations"] == 0
    assert set(metrics["by_source"]) == {"plan", "coach"}


def test_plan_recommendations_obey_observed_times_fraction(db):
    """observed spending x reduction fraction ~= suggested cut in tolerance."""
    report = run_recommendation_dataset(db)
    outcome = next(outcome for outcome in report.outcomes if outcome.source == "plan")
    assert outcome.arithmetic_checks >= 4      # cut vs chain, cap, sum, aggregate
    assert outcome.arithmetic_passed == outcome.arithmetic_checks


def test_plan_does_not_double_count_overlapping_categories(db):
    """The cuts across categories must not exceed the monthly gap."""
    report = run_recommendation_dataset(db)
    at_risk = next(result for result in report.results
                   if result.case_id == "plan_recommendations_at_risk")
    assert at_risk.scores["no_double_counting"] == 1.0


def test_double_counting_guard_trips_on_inflated_cuts(db, monkeypatch):
    """The evaluator itself must fail when cuts exceed the monthly gap."""
    from app.services.planning import savings as savings_module

    original = savings_module.calculate_savings_plan

    def inflated(**kwargs):
        plan = deepcopy(original(**kwargs))
        for item in plan["recommendations"]:
            item["suggested_cut"] = item["suggested_cut"] * 3
        return plan

    monkeypatch.setattr(savings_module, "calculate_savings_plan", inflated)
    result, outcome = run_plan_case_with_outcome(db, PLAN_AT_RISK_CASE)
    assert not result.passed
    assert result.scores["no_double_counting"] == 0.0
    assert result.scores["arithmetic"] == 0.0
    assert not outcome.double_counting_ok


def test_plan_avoids_strong_claims_without_history(db):
    """Insufficient history: no estimates, no cuts, explicit limitation."""
    plan = calculate_savings_plan(
        transactions=[],
        goal_amount=Decimal("60000"),
        current_saved=Decimal("30000"),
        target_date=date(2026, 12, 31),
        today=date(2026, 10, 25),
    )
    assert plan["status"] == "insufficient_data"
    for field in ("estimated_monthly_income", "estimated_monthly_spending",
                  "estimated_monthly_surplus", "projected_monthly_saving"):
        assert plan[field] is None, (field, plan[field])
    assert plan["recommendations"] == []
    assert plan["historical_transaction_count"] == 0
    assert any("No usable actual history" in line for line in plan["limitations"])

    result = run_plan_case(db, PLAN_INSUFFICIENT_CASE)
    assert result.passed


def test_plan_recommendations_are_personal(db):
    """The suggested cut derives from this user's own category spending."""
    report = run_recommendation_dataset(db)
    result = next(result for result in report.results
                  if result.case_id == "plan_recommendations_at_risk")
    # Food 12000 -> 20% cut = 2400; Entertainment 1000 -> gap-bounded 200.
    assert result.scores["personalization"] == 1.0
    assert result.scores["grounding"] == 1.0
    assert result.scores["estimate_labeling"] == 1.0


def test_coach_recommendations_grounding_and_arithmetic(db):
    """Food: min(9000 x 10%, 9000-5000) = 900; Shopping: 300."""
    result, outcome = run_coach_case_with_outcome(db, COACH_INCREASED_CASE)
    assert result.passed, result.failures
    assert outcome.source == "coach"
    assert outcome.arithmetic_passed == outcome.arithmetic_checks >= 6
    assert outcome.grounding_passed == outcome.grounding_checks
    assert outcome.labeling_ok and outcome.double_counting_ok
    assert outcome.personalization_ok


def test_coach_recommendations_absent_when_condition_false(db):
    """Stable spending across both categories: no opportunity at all."""
    from app.evaluation.datasets.recommendation_cases import COACH_STABLE_CASE

    result, _outcome = run_coach_case_with_outcome(db, COACH_STABLE_CASE)
    assert result.passed
    assert result.observed_status == "empty"


def test_coach_silent_on_non_reducible_spending_spike(db):
    """Bills spike is not treated as an optional spending reduction."""
    from app.evaluation.datasets.recommendation_cases import COACH_NON_REDUCIBLE_CASE

    result, _outcome = run_coach_case_with_outcome(db, COACH_NON_REDUCIBLE_CASE)
    assert result.passed
    assert result.observed_status == "empty"


def test_coach_requires_three_complete_history_months(db):
    """Two months of history: no recommendations and an explicit limitation."""
    result, _outcome = run_coach_case_with_outcome(db, COACH_TWO_MONTHS_CASE)
    assert result.passed
    assert result.observed_status == "empty"
    assert result.scores["data_sufficiency"] == 1.0


# -------------------------------------------------------- proactive insights


def test_full_insight_report_passes(db, capsys):
    from app.evaluation.insight_metrics import format_insight_report

    report = run_insight_dataset(db)
    print(format_insight_report(report))
    assert report.passed, format_insight_report(report)
    metrics = report.metrics
    assert metrics["presence_accuracy"] == 100.0
    assert metrics["numbers_accuracy"] == 100.0
    assert metrics["dates_accuracy"] == 100.0
    assert metrics["plan_labeling_accuracy"] == 100.0
    assert metrics["isolation_violations"] == 0
    assert metrics["detection_rate"] == 1.0
    assert metrics["false_alarm_rate"] == 0.0
    assert metrics["numeric_passed"] == metrics["numeric_checks"] > 0
    assert metrics["date_passed"] == metrics["date_checks"] > 0


def test_every_insight_type_is_detected_on_true_and_silent_on_false(db):
    report = run_insight_dataset(db)
    detection = report.metrics["detection"]
    for insight_type in KNOWN_INSIGHT_TYPES:
        counts = detection[insight_type]
        assert counts["tp"] >= 1, insight_type
        assert counts["fn"] == 0, insight_type
        assert counts["fp"] == 0, insight_type
        assert counts["tn"] >= 1, insight_type
        assert counts["detection_rate"] == 1.0
        assert counts["false_alarm_rate"] == 0.0


def test_insight_numbers_and_dates_match_scenario_ground_truth(db):
    """Triggered cases: every pinned number and date must hold."""
    for case in INSIGHT_EVALUATION_CASES:
        if case.behavior != "triggered":
            continue
        result, outcome = run_insight_case_with_outcome(db, case)
        assert result.passed, (case.case_id, result.failures)
        assert outcome.numeric_passed == outcome.numeric_checks
        assert outcome.date_passed == outcome.date_checks
        assert outcome.unexpected_types == 0


def test_scheduled_is_never_presented_as_actual(db):
    """Upcoming obligations are plan-marked; paid items never appear."""
    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_upcoming_scheduled_triggered")
    result, outcome = run_insight_case_with_outcome(db, case)
    assert result.passed, result.failures
    assert result.scores["plan_labeling"] == 1.0
    assert outcome.type_results[UPCOMING_EXPENSE] == "tp"
    # The silent variant proves a paid/beyond-horizon entry can never appear.
    silent_case = next(case for case in INSIGHT_EVALUATION_CASES
                       if case.case_id == "insight_upcoming_scheduled_silent")
    silent_result, silent_outcome = run_insight_case_with_outcome(db, silent_case)
    assert silent_result.passed
    assert silent_outcome.type_results[UPCOMING_EXPENSE] == "tn"


def test_insufficient_history_never_produces_spending_insights(db):
    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_insufficient_history_silent")
    result, outcome = run_insight_case_with_outcome(db, case)
    assert result.passed
    assert all(verdict == "tn" for verdict in outcome.type_results.values())


def test_insights_never_leak_other_users_records(db):
    report = run_insight_dataset(db)
    for result in report.results:
        assert result.scores["isolation"] == 1.0, result.case_id


def test_goal_progress_reports_user_reported_savings(db):
    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_goal_progress_triggered")
    result, outcome = run_insight_case_with_outcome(db, case)
    assert result.passed
    assert outcome.type_results[GOAL_PROGRESS] == "tp"


def test_projected_shortfall_numbers_match_ground_truth(db):
    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_projected_shortfall_triggered")
    result, outcome = run_insight_case_with_outcome(db, case)
    assert result.passed
    assert outcome.type_results[PROJECTED_SHORTFALL] == "tp"
    assert outcome.numeric_passed == outcome.numeric_checks


def test_savings_opportunity_estimate_matches_formula(db):
    case = next(case for case in INSIGHT_EVALUATION_CASES
                if case.case_id == "insight_savings_opportunity_triggered")
    result, outcome = run_insight_case_with_outcome(db, case)
    assert result.passed
    assert outcome.type_results[SAVINGS_OPPORTUNITY] == "tp"


# --------------------------------------------------------------- contract


def test_ai_12a_evaluation_contract_still_intact():
    from app.evaluation import (
        EVALUATION_CASES, EVALUATION_SCENARIO,
        format_report, ground_truth_consistency, run_case as finance_run_case,
        run_dataset as finance_run_dataset,
    )
    assert EVALUATION_CASES and EVALUATION_SCENARIO
    assert callable(format_report) and callable(ground_truth_consistency)
    assert callable(finance_run_case) and callable(finance_run_dataset)


def test_ai_12d_exports_are_importable():
    from app import evaluation
    for name in (
        "INSIGHT_EVALUATION_CASES", "run_insight_dataset",
        "format_insight_report", "INSIGHT_SCORE_DIMENSIONS",
        "PLAN_CASES", "COACH_CASES", "run_recommendation_dataset",
        "format_recommendation_report", "RECOMMENDATION_SCORE_DIMENSIONS",
        "validate_insight_dataset", "validate_recommendation_dataset",
    ):
        assert hasattr(evaluation, name), name
