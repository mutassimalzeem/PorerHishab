"""AI-12A evaluation foundation tests.

Offline by construction: no provider call is reachable from the runner. The
deterministic coach is evaluated against ground truth derived independently
from the seeded scenario specification.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import SavingsGoal, ScheduledCashflowItem
from app.evaluation import (
    ALL_CASES,
    EVALUATION_CASES,
    EVALUATION_SCENARIO,
    AS_OF,
    format_report,
    ground_truth_consistency,
    numeric_score,
    run_case,
    run_dataset,
)
from app.evaluation.datasets.finance_scenario import seed_scenario, clear_scenario
from app.evaluation.datasets.grounded_chat_stress import STRESS_CASES


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Evaluation must never touch a provider, even if one is configured."""
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)


def test_dataset_ground_truth_matches_scenario_specification():
    """Every pinned number in the dataset must equal spec-derived totals."""
    assert ground_truth_consistency() == []


def test_metric_tolerance_semantics():
    assert numeric_score("12500", "12500") == 1.0
    assert numeric_score("12500.00", "12500") == 1.0
    assert numeric_score("12500", "11200") == 0.0
    assert numeric_score("100", "105", tolerance=Decimal("5")) == 1.0
    assert numeric_score("100", "106", tolerance=Decimal("5")) == 0.0
    assert numeric_score(None, None) == 1.0
    assert numeric_score("100", None) == 0.0


def test_runner_is_sensitive_to_wrong_expectations(db):
    """The evaluator itself must be able to fail (sanity of the framework)."""
    users = seed_scenario(db)
    try:
        broken = deepcopy(EVALUATION_CASES[0])
        broken["id"] = "mutated_case"
        broken = {**broken, "expected_calculation": {**broken["expected_calculation"], "expenses": "9999.00"}}
        result = run_case(db, broken, users[0], users[-1], as_of=AS_OF)
        assert not result.passed
        assert any(failure.startswith("numeric:") for failure in result.failures)
        assert result.scores["numeric"] == 0.0
    finally:
        clear_scenario(db, users)


def test_runner_reports_ambiguity_as_refusal(db):
    users = seed_scenario(db)
    try:
        case = next(case for case in EVALUATION_CASES if case["group"] == "ambiguous_period")
        result = run_case(db, case, users[0], users[-1], as_of=AS_OF)
        assert result.observed_status == "ambiguous"
        assert result.passed
        # Refusal cases apply only status and safety dimensions.
        assert result.scores["status"] == 1.0
        assert result.scores["numeric"] is None
    finally:
        clear_scenario(db, users)


def test_full_finance_evaluation_passes(db, capsys):
    """Run the whole AI-12A dataset and require a clean report."""
    report = run_dataset(db)
    print(format_report(report))
    assert report.case_count == len(ALL_CASES)
    assert len(STRESS_CASES) >= 50, "AI-12B should add substantial stress coverage"
    assert report.passed, format_report(report)
    metrics = report.metrics
    for dimension in ("intent", "date", "numeric", "status", "grounding", "safety"):
        assert metrics[f"{dimension}_accuracy"] == 100.0, (dimension, metrics)
    assert metrics["unsupported_question_accuracy"] == 100.0
    # User isolation is part of the safety dimension for every case.
    assert all("safety" not in (result.failures or []) for result in report.results)
    assert metrics["by_group"]["unsupported"]["cases"] == 4


def test_scenario_seeding_is_reproducible(db):
    """Seeding the same scenario twice yields identical ground truth totals."""
    from app.evaluation.datasets.finance_scenario import scenario_totals

    first_users = seed_scenario(db)
    first = scenario_totals(EVALUATION_SCENARIO, 0, date(2026, 9, 1), date(2026, 9, 30))
    clear_scenario(db, first_users)
    second_users = seed_scenario(db)
    second = scenario_totals(EVALUATION_SCENARIO, 0, date(2026, 9, 1), date(2026, 9, 30))
    clear_scenario(db, second_users)
    assert first == second == {"income": Decimal("30000"), "expenses": Decimal("8500")}


def test_coach_never_produces_isolation_canary(db):
    """Direct adversarial probe: ask across the isolation boundary."""
    users = seed_scenario(db)
    try:
        from app.schemas.chat import FinanceQuestionRequest
        from app.services.finance.grounded_chat import answer_question

        result = answer_question(db, users[0].id,
                                 FinanceQuestionRequest(question="Top merchants last month"),
                                 as_of=AS_OF)
        assert "SECRET OTHER USER LEDGER" not in str(result)
        # 8500.00 belongs to user A; the 999999 decoy must never appear.
        assert Decimal(result["calculation"]["items"][0]["expenses"]) == Decimal("4000.00")
        assert all(Decimal(item["expenses"]) != Decimal("999999") for item in result["calculation"]["items"])
    finally:
        clear_scenario(db, users)
