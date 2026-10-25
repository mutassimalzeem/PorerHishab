"""AI-12E quality-gate regression tests.

The gate itself must be proven to discriminate: PASS when every suite passes,
FAIL when any mandatory gate is violated, ERROR when an evaluator cannot
execute correctly. Everything runs offline on in-memory SQLite; no provider
is reachable and no real user data is involved.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (register ORM models)
from app.core.config import settings
from app.core.database import Base
from app.evaluation.quality_gate import (
    ERROR,
    FAIL,
    PASS,
    SECTION_CATEGORIZATION,
    SECTION_FINANCE,
    SECTION_INSIGHTS,
    SECTION_RECOMMENDATIONS,
    QualityGateResult,
    QualityThresholds,
    SectionResult,
    format_quality_report,
    main as quality_gate_main,
    run_quality_gate,
)
from app.evaluation.datasets.finance_scenario import ISOLATION_CANARY
from app.evaluation.datasets.insight_scenarios import INSIGHT_ISOLATION_MARKERS
from app.evaluation.datasets.recommendation_cases import RECOMMENDATION_ISOLATION_MARKERS


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """The gate must never touch a provider, even if one is configured."""
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ------------------------------------------------------------------- happy path


def test_all_suites_pass_gives_overall_pass():
    result = run_quality_gate()
    assert result.overall == PASS
    assert result.overall_passed
    assert result.failures == [] and result.errors == []
    for key in (SECTION_FINANCE, SECTION_CATEGORIZATION,
                SECTION_RECOMMENDATIONS, SECTION_INSIGHTS):
        assert result.sections[key].status == PASS, key
        assert result.sections[key].case_count > 0, key


def test_gate_is_deterministic_apart_from_nothing():
    """Two full runs must produce identical aggregate JSON (no wall clock)."""
    first = run_quality_gate().to_json_dict()
    second = run_quality_gate().to_json_dict()
    assert first == second
    # The snapshot metadata is the suites' fixed evaluation dates, not now().
    assert first["evaluations"]["finance"]["as_of"]
    # The JSON text form (dates serialized) must itself be reproducible.
    assert run_quality_gate().to_json() == run_quality_gate().to_json()


def test_failing_sections_carry_only_case_ids_and_metrics():
    result = run_quality_gate()
    dumped = result.to_json()
    for marker in ({ISOLATION_CANARY, *INSIGHT_ISOLATION_MARKERS,
                    *RECOMMENDATION_ISOLATION_MARKERS}):
        assert marker not in dumped
    # And the payloads are metrics/ids only — validation is structural here.
    for key in (SECTION_FINANCE, SECTION_CATEGORIZATION,
                SECTION_RECOMMENDATIONS, SECTION_INSIGHTS):
        section = result.to_json_dict()["evaluations"][key]
        assert set(section) == {"status", "passed", "as_of", "metrics",
                                "failed_case_ids", "gate_failures"}


# -------------------------------------------------------------- verdict matrix


@pytest.fixture
def gate_result(monkeypatch):
    """Build a gate result from canned section outcomes."""
    def factory(**sections):
        defaults = {
            key: SectionResult(key=key, status=PASS, metrics={"case_count": 3})
            for key in (SECTION_FINANCE, SECTION_CATEGORIZATION,
                        SECTION_RECOMMENDATIONS, SECTION_INSIGHTS)}
        defaults.update(sections)
        result = QualityGateResult(sections=defaults, thresholds=QualityThresholds())
        monkeypatch.setattr(
            "app.evaluation.quality_gate.run_quality_gate",
            lambda *args, **kwargs: result)
        return result
    return factory


def test_finance_gate_failure_overall_fail(gate_result):
    result = gate_result(**{
        SECTION_FINANCE: SectionResult(
            key=SECTION_FINANCE, status=FAIL,
            metrics={"case_count": 26}, gate_failures=["safety_accuracy=0.0"])})
    assert result.overall == FAIL
    assert not result.overall_passed
    assert result.failures == [f"{SECTION_FINANCE}: safety_accuracy=0.0"]


def test_categorization_gate_failure_overall_fail(gate_result):
    result = gate_result(**{
        SECTION_CATEGORIZATION: SectionResult(
            key=SECTION_CATEGORIZATION, status=FAIL,
            metrics={"case_count": 123}, gate_failures=["macro_f1=80.0"])})
    assert result.overall == FAIL


def test_recommendation_gate_failure_overall_fail(gate_result):
    result = gate_result(**{
        SECTION_RECOMMENDATIONS: SectionResult(
            key=SECTION_RECOMMENDATIONS, status=FAIL,
            metrics={"case_count": 8},
            gate_failures=["arithmetic_accuracy=90.0"])})
    assert result.overall == FAIL


def test_insight_gate_failure_overall_fail(gate_result):
    result = gate_result(**{
        SECTION_INSIGHTS: SectionResult(
            key=SECTION_INSIGHTS, status=FAIL,
            metrics={"case_count": 11}, gate_failures=["detection_rate=0.5"])})
    assert result.overall == FAIL


def test_evaluator_crash_is_error_not_pass_or_zero_cases(db, monkeypatch):
    """A non-executable evaluator must surface as ERROR, never as PASS."""
    from app.evaluation import quality_gate
    monkeypatch.setattr(
        "app.evaluation.recommendation_runner.run_recommendation_dataset",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    result = quality_gate.evaluate_recommendations(db, QualityThresholds())
    assert result.status == ERROR
    assert "RuntimeError" in (result.error or "")


def test_empty_dataset_is_error(db, monkeypatch):
    """Zero cases is an execution problem, not an automatic pass."""
    from datetime import date
    from app.evaluation import metrics as metrics_module
    from app.evaluation import runner as runner_module

    empty = metrics_module.EvaluationReport(as_of=date(2026, 10, 25),
                                            case_count=0, results=[])
    empty.metrics.update(case_count=0, passed=0, failed=0)
    monkeypatch.setattr(runner_module, "run_dataset", lambda *a, **kw: empty)
    section = quality_gate_module().evaluate_finance(db, QualityThresholds())
    assert section.status == ERROR


def quality_gate_module():
    from app.evaluation import quality_gate
    return quality_gate


def test_threshold_violation_is_fail_not_error():
    """A tightened threshold is a measured FAIL with the metric named."""
    thresholds = QualityThresholds(categorization_min_macro_f1=101.0)
    result = run_quality_gate(thresholds=thresholds)
    assert result.overall == FAIL
    categorization = result.sections[SECTION_CATEGORIZATION]
    assert categorization.status == FAIL
    assert any("macro_f1" in message for message in categorization.gate_failures)


def test_error_dominates_fail(gate_result):
    result = gate_result(**{
        SECTION_FINANCE: SectionResult(
            key=SECTION_FINANCE, status=FAIL,
            metrics={"case_count": 26}, gate_failures=["x"]),
        SECTION_INSIGHTS: SectionResult(
            key=SECTION_INSIGHTS, status=ERROR, metrics={},
            error="ValueError: dataset inconsistent")})
    assert result.overall == ERROR


# ------------------------------------------------------------------- reporting


def test_json_and_human_report_agree():
    result = run_quality_gate()
    payload = result.to_json_dict()
    text = format_quality_report(result)
    assert f"OVERALL: {payload['overall']}" in text
    for key, section in payload["evaluations"].items():
        assert section["passed"] == (section["status"] == PASS)
    finance = payload["evaluations"][SECTION_FINANCE]["metrics"]
    assert f"Cases: {finance['case_count']}" in text
    assert "OVERALL: " + payload["overall"] == "OVERALL: PASS"


def test_human_report_contains_no_financial_payload():
    result = run_quality_gate()
    text = format_quality_report(result)
    for marker in ({ISOLATION_CANARY, *INSIGHT_ISOLATION_MARKERS,
                    *RECOMMENDATION_ISOLATION_MARKERS}):
        assert marker not in text


# ------------------------------------------------------------------- CLI codes


def test_main_exit_codes(monkeypatch, capsys):
    from app.evaluation import quality_gate

    def fake_gate(*args, **kwargs):
        if fake_gate.mode == PASS:
            sections = {key: SectionResult(key=key, status=PASS, metrics={"case_count": 1})
                        for key in (SECTION_FINANCE, SECTION_CATEGORIZATION,
                                    SECTION_RECOMMENDATIONS, SECTION_INSIGHTS)}
        else:
            sections = {key: SectionResult(key=key, status=PASS, metrics={"case_count": 1})
                        for key in (SECTION_FINANCE, SECTION_CATEGORIZATION,
                                    SECTION_RECOMMENDATIONS, SECTION_INSIGHTS)}
            sections[SECTION_FINANCE] = SectionResult(
                key=SECTION_FINANCE, status=fake_gate.mode, metrics={"case_count": 1},
                gate_failures=["x"] if fake_gate.mode == FAIL else None,
                error="boom" if fake_gate.mode == ERROR else None)
        return QualityGateResult(sections=sections, thresholds=QualityThresholds())

    fake_gate.mode = PASS
    monkeypatch.setattr(quality_gate, "run_quality_gate", fake_gate)
    assert quality_gate.main([]) == 0
    capsys.readouterr()
    assert quality_gate.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)  # --json is valid JSON

    fake_gate.mode = FAIL
    assert quality_gate.main([]) == 1

    fake_gate.mode = ERROR
    assert quality_gate.main([]) == 2
