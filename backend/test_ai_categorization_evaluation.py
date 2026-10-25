"""AI-12C offline evaluation tests for transaction categorization.

No provider call is reachable: the default run executes the deterministic
pipeline with ``allow_llm=False`` and an autouse fixture that keeps
``AI_EXTERNAL_ENABLED`` off.  Provider behaviour is examined with injected
offline stubs that either fail or return fixed, validated shapes.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.evaluation.categorization_metrics import (
    CategorizationOutcome,
    ambiguity_handling,
    categorization_prf,
    correction_preservation,
    macro_micro,
    pathway_rates,
)
from app.evaluation.datasets.categorization_cases import CATEGORIZATION_EVALUATION_CASES
from app.evaluation.categorization_runner import (
    CATEGORIZATION_SCORE_DIMENSIONS,
    run_case,
    run_dataset,
    validate_dataset,
)
from app.services.categorization import service as categorization_service
from app.services.categorization.categories import ALLOWED_CATEGORIES, UNCATEGORIZED
from app.services.categorization.llm import CategorizationLLMError
from app.schemas.categorization import LLMCategorization


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


def _outcome(case_id="case", behavior="rule_classify", *, group="g",
             ambiguous=False, mixed=False, eligible=True, expected=None,
             observed_category=None, method="rule", corrected=None,
             observed_method=None):
    return CategorizationOutcome(
        case_id=case_id, group=group, behavior=behavior,
        is_ambiguous=ambiguous, is_mixed_language=mixed, eligible=eligible,
        expected_category=expected, observed_category=observed_category,
        observed_method=observed_method or method,
        corrected_category=corrected,
    )


# --------------------------------------------------------------------- dataset


def test_dataset_hygiene_and_unique_ids():
    problems = validate_dataset()
    assert problems == [], problems
    ids = [case["id"] for case in CATEGORIZATION_EVALUATION_CASES]
    assert len(ids) == len(set(ids))
    assert 100 <= len(ids) <= 150


def test_dataset_covers_all_required_evidence_types():
    groups = {case["group"] for case in CATEGORIZATION_EVALUATION_CASES}
    for required in ("clear_merchant", "similar_outcome", "language_bangla",
                     "language_mixed", "unknown_merchant", "ambiguous_context",
                     "misleading_keywords", "malformed_input", "long_input",
                     "corrected_categories", "custom_categories"):
        assert required in groups, (required, sorted(groups))
    cases = CATEGORIZATION_EVALUATION_CASES
    assert any(case.get("is_mixed_language") for case in cases)
    assert any(case.get("is_ambiguous") for case in cases)
    behaviors = {case["expected_behavior"] for case in cases}
    assert behaviors == {"rule_classify", "provider_required", "never_classify",
                         "user_correction", "custom_category"}


def test_dataset_labels_match_the_taxonomy():
    for case in CATEGORIZATION_EVALUATION_CASES:
        expected = case.get("expected_category")
        if expected:
            assert expected in ALLOWED_CATEGORIES, (case["id"], expected)


# ----------------------------------------------------------- rules-only report


def test_offline_rules_only_report_passes(db):
    report = run_dataset(db)
    assert report.mode == "rules_only"
    assert report.passed, _printable(report)
    assert report.case_count == len(CATEGORIZATION_EVALUATION_CASES)
    metrics = report.metrics
    assert metrics["correction_preservation"] == 1.0
    assert metrics["ambiguity_guess_rate"] == 0.0
    assert metrics["ambiguous_cases"] > 0
    assert 0.0 < metrics["rule_coverage"] < 1.0
    assert metrics["llm_path_rate"] == 0.0
    assert metrics["provider_fallback_rate"] > 0.0


def test_pathway_rates_reflect_real_execution_paths(db):
    report = run_dataset(db)
    eligible = [outcome for outcome in report.outcomes if outcome.eligible]
    by_path = pathway_rates(report.outcomes)["by_path"]
    # Recomputed straight from the outcome trace, no inference from labels:
    assert by_path["rule"] == sum(
        1 for outcome in eligible if outcome.observed_method == "rule")
    assert by_path["fallback"] == sum(
        1 for outcome in eligible if outcome.observed_method == "fallback")
    assert by_path["user_preference"] == len([
        case for case in CATEGORIZATION_EVALUATION_CASES
        if case["expected_behavior"] in ("user_correction", "custom_category")])
    coverage = report.metrics["rule_coverage"]
    fallback = report.metrics["provider_fallback_rate"]
    assert coverage == by_path["rule"] / len(eligible)
    assert fallback == (by_path["fallback"] + by_path.get("llm", 0)) / len(eligible)
    # Not classified by rules, but resolved by the user in the same run:
    assert coverage + fallback < 1.0


def test_per_case_scores_have_applicable_dimensions_only(db):
    report = run_dataset(db)
    ambiguous = [result for result in report.results
                 if result.expected_status == "provider_required"]
    corrected = [result for result in report.results
                 if result.expected_status in ("user_correction", "custom_category")]
    never = [result for result in report.results
             if result.expected_status == "never_classify"]
    for result in ambiguous:
        assert result.scores["ambiguity"] == 1.0
    for result in corrected:
        assert result.scores["method"] == 1.0
        assert result.scores["ambiguity"] is None
    for result in never:
        assert result.scores["method"] == 1.0
        assert result.scores["ambiguity"] is None


# ----------------------------------------------------------------- PRF metrics


def test_per_category_prf_on_known_outcomes():
    outcomes = [
        # Food: 3 supports; two hits + one confident miss.
        _outcome("f1", expected="Food", observed_category="Food", method="rule"),
        _outcome("f2", expected="Food", observed_category="Food", method="llm"),
        _outcome("f3", expected="Food", observed_category="Transport", method="rule"),
        # Transport: 1 support, hit.
        _outcome("t1", expected="Transport", observed_category="Transport"),
        # Groceries: 2 supports, 2 hits.
        _outcome("g1", expected="Groceries", observed_category="Groceries"),
        _outcome("g2", expected="Groceries", observed_category="Groceries"),
        # Guesses on uncertain (no ground truth) input are always FPs.
        _outcome("a1", behavior="provider_required", ambiguous=True,
                 observed_category="Food", method="rule"),
        _outcome("n1", behavior="never_classify", eligible=False,
                 observed_category=UNCATEGORIZED, method="fallback"),
        # A category predicted with no support: recall is None, precision 0.
        _outcome("z1", behavior="provider_required", ambiguous=True,
                 observed_category="Decor", method="llm"),
        # A supported category with no prediction at all.
        _outcome("i1", expected="Investment", observed_category=UNCATEGORIZED,
                 method="fallback"),
    ]
    per_category = categorization_prf(outcomes)

    food = per_category["Food"]
    assert (food.tp, food.fp, food.fn, food.support, food.predicted) == (2, 1, 1, 3, 3)
    assert food.precision == pytest.approx(2 / 3)
    assert food.recall == pytest.approx(2 / 3)
    assert food.f1 == pytest.approx(2 / 3)

    transport = per_category["Transport"]
    # The Transport prediction on the Food miss is a TP for Transport itself;
    # it is simultaneously an FP for Transport's precision denominator.
    assert (transport.tp, transport.fp, transport.fn, transport.support,
            transport.predicted) == (1, 1, 0, 1, 2)
    assert transport.precision == pytest.approx(0.5)
    assert transport.recall == 1.0
    assert transport.f1 == pytest.approx(2 / 3)

    groceries = per_category["Groceries"]
    assert groceries.precision == groceries.recall == groceries.f1 == 1.0

    # Predicted but never supported: precision None after compute? predicted=1,
    # support=0 -> precision 0.0, recall None, f1 None.
    decor = per_category["Decor"]
    assert decor.precision == 0.0
    assert decor.recall is None
    assert decor.f1 is None

    # Supported but never predicted: precision None, recall 0.0, f1 None.
    investment = per_category["Investment"]
    assert investment.predicted == 0
    assert investment.precision is None
    assert investment.recall == 0.0
    assert investment.f1 is None

    # Fallback results never enter any category matrix.
    assert "Uncategorized" not in per_category


def test_macro_micro_consistency():
    outcomes = [
        _outcome(expected="Food", observed_category="Food"),
        _outcome(expected="Food", observed_category="Food"),
        _outcome(expected="Food", observed_category="Food", method="llm"),
        _outcome(expected="Food", observed_category="Transport"),
        _outcome(expected="Transport", observed_category="Transport"),
        _outcome(expected="Groceries", observed_category="Groceries"),
        _outcome(expected="Groceries", observed_category="Groceries"),
        _outcome(behavior="provider_required", ambiguous=True,
                 observed_category="Food", method="rule"),
        _outcome(expected="Investment", observed_category=UNCATEGORIZED,
                 method="fallback"),
    ]
    per_category = categorization_prf(outcomes)
    aggregates = macro_micro(per_category)

    # Only categories with both precision and recall defined enter the macro.
    defined = [per_category["Food"], per_category["Transport"], per_category["Groceries"]]
    assert aggregates["macro_categories"] == len(defined)
    expected_macro_f1 = (
        (defined[0].f1 + defined[1].f1 + defined[2].f1) / 3)
    assert aggregates["macro_f1"] == pytest.approx(round(expected_macro_f1 * 100, 1))

    assert aggregates["micro_tp"] == 6
    assert aggregates["micro_fp"] == 2  # wrong-transport guess + ambiguous Food guess
    assert aggregates["micro_fn"] == 2  # Food miss + Investment miss
    assert aggregates["micro_precision"] == pytest.approx(6 / 8)
    assert aggregates["micro_recall"] == pytest.approx(6 / 8)
    assert aggregates["micro_f1"] == pytest.approx(6 / 8)
    # Micro F1 must be the harmonic mean of the micro P/R pair.
    p, r = aggregates["micro_precision"], aggregates["micro_recall"]
    assert aggregates["micro_f1"] == pytest.approx(2 * p * r / (p + r))


def test_ambiguity_handling_scored_separately():
    outcomes = [
        _outcome(ambiguous=True, behavior="provider_required",
                 observed_category="Food", method="rule"),
        _outcome(ambiguous=True, behavior="provider_required",
                 observed_category=UNCATEGORIZED, method="fallback"),
        _outcome(ambiguous=True, behavior="provider_required",
                 observed_category="Transport", method="llm"),
        _outcome(expected="Food", observed_category="Food"),
    ]
    handling = ambiguity_handling(outcomes)
    assert handling["ambiguous_cases"] == 3
    # The llm-path case IS a confident answer on uncertain ground: a guess.
    assert handling["guess_rate"] == pytest.approx(2 / 3)
    assert handling["safe_uncertainty_rate"] == pytest.approx(1 / 3)


def test_correction_preservation_metric():
    outcomes = [
        _outcome(behavior="user_correction", corrected="Groceries",
                 observed_category="Groceries", method="user_preference"),
        _outcome(behavior="custom_category", corrected="Family support",
                 observed_category="Family support", method="user_preference"),
        _outcome(behavior="custom_category", corrected="Donation",
                 observed_category="Other", method="user_preference"),
        _outcome(expected="Food", observed_category="Food"),
    ]
    assert correction_preservation(outcomes) == pytest.approx(2 / 3)
    assert correction_preservation(
        [_outcome(behavior="rule_classify", observed_category="Food")]) is None


def test_run_dataset_fails_when_expectations_are_wrong(db):
    cases = deepcopy(CATEGORIZATION_EVALUATION_CASES)
    target = next(case for case in cases
                  if case["expected_behavior"] == "rule_classify")
    target["expected_category"] = "Investment"
    report = run_dataset(db, cases=cases)
    assert not report.passed
    failed = next(result for result in report.results if result.case_id == target["id"])
    assert any(failure.startswith("category:") for failure in failed.failures)
    assert failed.scores["category"] == 0.0


# ------------------------------------------------ corrections & custom labels


def test_confirmed_correction_beats_rules_offline(db):
    from app.models import User
    from app.models.merchant_preference import MerchantCategoryPreference

    user = User(email="corr@porer-hishab.local", hashed_password="x",
                full_name="Correction Eval")
    db.add(user)
    db.commit()
    db.add(MerchantCategoryPreference(
        user_id=user.id, normalized_merchant="foodpanda mart", category="Groceries"))
    db.commit()

    case = next(case for case in CATEGORIZATION_EVALUATION_CASES
                if case["id"] == "cat_correction_foodpanda_mart")
    result, outcome = run_case(db, case, user.id)
    assert result.passed
    assert outcome.observed_method == "user_preference"
    assert outcome.observed_category == "Groceries"  # not the Food rule's answer


def test_custom_category_labels_are_not_in_the_taxonomy():
    for case in CATEGORIZATION_EVALUATION_CASES:
        if case["expected_behavior"] == "custom_category":
            label = case["user_context"]["confirmed_correction"]["category"]
            assert label not in ALLOWED_CATEGORIES
            assert label == label.strip()
            assert 0 < len(label) <= 100


def test_rerunning_the_dataset_is_stable(db):
    first = run_dataset(db)
    second = run_dataset(db)
    assert [outcome.observed_category for outcome in first.outcomes] == \
           [outcome.observed_category for outcome in second.outcomes]
    assert first.passed and second.passed


# --------------------------------------------------------- provider stubs


def _valid_stub(calls):
    def stub(**kwargs):
        calls.append(kwargs)
        return LLMCategorization(category="Other", confidence=0.7, reason="offline stub")
    return stub


def test_provider_stub_resolves_fallback_path_but_not_rules(db, monkeypatch):
    calls: list = []
    monkeypatch.setattr(categorization_service, "categorize_with_llm", _valid_stub(calls))
    provider_pass = run_dataset(db, allow_llm=True, mode="provider_stub")
    assert provider_pass.passed, _printable(provider_pass)
    assert calls, "the stub provider must be reached for unruled cases"

    monkeypatch.setattr(categorization_service, "categorize_with_llm", _valid_stub([]))
    rules_pass = run_dataset(db)

    # Rules short-circuit in both passes: identical coverage.
    assert provider_pass.metrics["rule_coverage"] == rules_pass.metrics["rule_coverage"]
    assert provider_pass.metrics["llm_path_rate"] > 0.0
    assert rules_pass.metrics["llm_path_rate"] == 0.0
    # The provider consumed the offline fallback share.
    assert provider_pass.metrics["provider_fallback_rate"] == \
           rules_pass.metrics["provider_fallback_rate"]


def test_provider_failure_degrades_safely_offline(db, monkeypatch):
    def failing_stub(**kwargs):
        raise CategorizationLLMError("provider unreachable")

    monkeypatch.setattr(categorization_service, "categorize_with_llm", failing_stub)
    report = run_dataset(db, allow_llm=True, mode="provider_stub")
    assert report.passed, _printable(report)
    assert report.metrics["llm_path_rate"] == 0.0
    unresolved = [outcome for outcome in report.outcomes
                  if outcome.behavior == "provider_required"]
    assert all(outcome.observed_category == UNCATEGORIZED for outcome in unresolved)
    assert all(outcome.observed_method == "fallback" for outcome in unresolved)


def test_provider_invalid_category_output_degrades_safely_offline(db, monkeypatch):
    def invalid_stub(**kwargs):
        return SimpleNamespace(category="Fooding", confidence=0.9, reason="x")

    monkeypatch.setattr(categorization_service, "categorize_with_llm", invalid_stub)
    report = run_dataset(db, allow_llm=True, mode="provider_stub")
    assert report.passed, _printable(report)
    assert report.metrics["llm_path_rate"] == 0.0
    assert report.metrics["provider_fallback_rate"] > 0.0


def test_provider_out_of_range_confidence_degrades_safely_offline(db, monkeypatch):
    def out_of_range_stub(**kwargs):
        return SimpleNamespace(category="Food", confidence=1.5, reason="x")

    monkeypatch.setattr(categorization_service, "categorize_with_llm", out_of_range_stub)
    report = run_dataset(db, allow_llm=True, mode="provider_stub")
    assert report.passed, _printable(report)
    assert all(outcome.observed_category == UNCATEGORIZED
               for outcome in report.outcomes
               if outcome.behavior == "provider_required")


def test_provider_stub_never_invoked_in_rules_pass(db, monkeypatch):
    def _boom(**kwargs):
        raise AssertionError("no provider call may happen in the rules-only pass")

    monkeypatch.setattr(categorization_service, "categorize_with_llm", _boom)
    report = run_dataset(db)
    assert report.passed


# ------------------------------------------------------------- format + legacy


def test_report_formatting_contains_quality_and_pathway_lines(db, capsys):
    from app.evaluation.categorization_metrics import format_categorization_report
    report = run_dataset(db)
    text = format_categorization_report(report)
    print(text)
    for needle in ("Categorization Evaluation", "Rule coverage:",
                   "Corrections preserved:", "Status: ALL CASES PASSED"):
        assert needle in text
    assert "Food" in text  # per-category table renders


def test_ai_12a_finance_evaluation_contract_intact():
    from app.evaluation import (
        EVALUATION_CASES, EVALUATION_SCENARIO, EVALUATION_SCENARIO_AS_OF,
        format_report, ground_truth_consistency, run_case as finance_run_case,
        run_dataset as finance_run_dataset,
    )
    assert EVALUATION_CASES and EVALUATION_SCENARIO
    assert callable(format_report) and callable(ground_truth_consistency)
    assert callable(finance_run_case) and callable(finance_run_dataset)


def _printable(report) -> str:
    from app.evaluation.categorization_metrics import format_categorization_report
    return format_categorization_report(report)
