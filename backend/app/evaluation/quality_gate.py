"""AI-12E quality gate: orchestrate the existing offline AI evaluators.

This module adds no evaluation logic of its own. It runs the four existing
suites in one offline, deterministic pass and distinguishes three outcomes:

* ``PASS``  — every mandatory gate satisfies its configured threshold;
* ``FAIL``  — at least one mandatory gate is violated (measured and real);
* ``ERROR`` — an evaluator could not execute correctly (crashed, its dataset
  validator rejected the dataset, or it returned an internally inconsistent /
  empty result). ERROR is never collapsed into PASS or counted as zero cases.

Nothing here calls a provider, needs an API key, or touches the network. All
four suites run against in-memory SQLite with seeded, controlled scenarios.

Usage:

    cd backend
    python -m app.evaluation.quality_gate
    # or, from the repository root:
    python -m backend.app.evaluation.quality_gate

Exit codes: 0 = PASS, 1 = FAIL, 2 = ERROR.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from app.evaluation.metrics import EvaluationReport
except ModuleNotFoundError:  # invoked as ``backend.app.evaluation.quality_gate``
    # Make ``app`` importable when the module is executed from the repository
    # root via ``python -m backend.app.evaluation.quality_gate``.
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from app.evaluation.metrics import EvaluationReport

#: Section keys used in the aggregate result and the machine-readable JSON.
SECTION_FINANCE = "finance"
SECTION_CATEGORIZATION = "categorization"
SECTION_RECOMMENDATIONS = "recommendations"
SECTION_INSIGHTS = "insights"

SECTION_KEYS = (SECTION_FINANCE, SECTION_CATEGORIZATION,
                SECTION_RECOMMENDATIONS, SECTION_INSIGHTS)

PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"

# Percent-scale (0-100) accuracy metrics gate per section. These reuse the
# AI-12A accuracy convention; the isolated categorization fractions (0-1) are
# gated separately below. Values are the evaluator's *own* metric names.
_FINANCE_ACCURACY_METRICS = ("intent_accuracy", "date_accuracy", "numeric_accuracy",
                             "status_accuracy", "grounding_accuracy", "safety_accuracy")
_RECOMMENDATION_PERCENT_METRICS = ("grounding_accuracy", "arithmetic_accuracy",
                                   "estimate_labeling_rate", "no_double_counting_rate",
                                   "personalization_rate", "data_sufficiency_rate")
_INSIGHT_PERCENT_METRICS = ("presence_accuracy", "numbers_accuracy", "dates_accuracy",
                            "plan_labeling_accuracy")


@dataclass(frozen=True)
class QualityThresholds:
    """Configured quality-gate thresholds.

    Scale conventions follow the existing evaluators exactly: percent-scale
    metrics produced by ``_accuracy`` helpers (0-100), and fraction-scale
    categorization metrics (0-1). See ``docs/ai-quality-gate.md``.

    Exact safety/contract checks are pinned at the maximum/minimum possible
    value: user isolation, correction precedence, no-guess-on-ambiguous,
    insight detection/false alarms, and data-sufficiency behaviour are
    deterministic properties of the offline pipeline, so any regression must
    fail the gate. The categorization F1 scores are statistical aggregates
    over a controlled labeled corpus and are kept configurable so the corpus
    can evolve without weakening the structural safety gates.
    """

    # -- finance / grounded chat (percent scale, as reported by summarize) ----
    #: Every finance accuracy dimension (intent, date, numeric, status,
    #: grounding, safety). 100.0: the controlled world pins exact expectations,
    #: so a fully consistent deterministic pipeline can always achieve them.
    finance_min_accuracy: float = 100.0
    #: No case in the finance dataset may be missing (internal consistency).
    finance_min_cases: int = 1

    # -- categorization -------------------------------------------------------
    #: Mean F1 over categories with definable precision/recall. Configurable
    #: (statistical metric); today's deterministic rule engine reaches 100%.
    categorization_min_macro_f1: float = 100.0
    #: Micro F1 is reported on the 0-1 scale by categorization_metrics.
    categorization_min_micro_f1: float = 1.0
    #: Confirmed user corrections must always take precedence. Exact contract.
    categorization_min_correction_preservation: float = 1.0
    #: An ambiguous input must never receive a confident guess. Exact contract.
    categorization_max_guess_rate: float = 0.0

    # -- recommendations (percent scale) --------------------------------------
    #: Grounding, arithmetic, estimate labeling, no double counting,
    #: personalization and data sufficiency are all pinned-structure checks.
    recommendation_min_percent: float = 100.0
    #: Any canary leak is a hard defect.
    recommendation_max_isolation_violations: int = 0

    # -- proactive insights ----------------------------------------------------
    #: Presence, numbers, dates and plan-labeling accuracies (percent scale).
    insight_min_percent: float = 100.0
    #: Every "condition true" world must raise its insight. Exact contract.
    insight_min_detection_rate: float = 1.0
    #: A "condition false" world must stay silent. Exact contract.
    insight_max_false_alarm_rate: float = 0.0
    #: Any canary leak is a hard defect.
    insight_max_isolation_violations: int = 0

    min_cases: int = 1  # minimum case count enforced for every section


@dataclass
class SectionResult:
    """Outcome of one orchestrated evaluator section."""

    key: str
    status: str                       # PASS | FAIL | ERROR
    metrics: dict[str, Any]           # the evaluator's own aggregate metrics
    as_of: Any = None                 # the suite's fixed evaluation date (if exposed)
    gate_failures: list[str] = field(default_factory=list)
    failed_case_ids: list[str] = field(default_factory=list)
    error: str | None = None
    report_text: str | None = None    # evaluator's own formatted report (on failure/error)

    @property
    def passed(self) -> bool:
        return self.status == PASS

    @property
    def case_count(self) -> int:
        return int(self.metrics.get("case_count", 0))


@dataclass
class QualityGateResult:
    """Aggregate of the four offline AI evaluation sections."""

    sections: dict[str, SectionResult]
    thresholds: QualityThresholds

    @property
    def failures(self) -> list[str]:
        return [f"{key}: {message}"
                for key in SECTION_KEYS
                for message in self.sections[key].gate_failures]

    @property
    def errors(self) -> list[str]:
        return [f"{key}: {self.sections[key].error}"
                for key in SECTION_KEYS if self.sections[key].error]

    @property
    def overall_passed(self) -> bool:
        return all(self.sections[key].passed for key in SECTION_KEYS)

    @property
    def overall(self) -> str:
        if self.errors:
            return ERROR
        return PASS if self.overall_passed else FAIL

    # ------------------------------------------------------------- JSON view

    def to_json_dict(self) -> dict[str, Any]:
        """Machine-readable, CI-friendly aggregate.

        Deliberately deterministic (no wall-clock timestamps; each section
        carries its fixed evaluation ``as_of`` when the evaluator exposes one)
        and free of financial content: metrics, case ids of failing synthetic
        cases, and threshold verdicts only.
        """
        return {
            "overall": self.overall,
            "overall_passed": self.overall_passed,
            "failures": self.failures,
            "errors": self.errors,
            "evaluations": {
                key: {
                    "status": self.sections[key].status,
                    "passed": self.sections[key].passed,
                    "as_of": self.sections[key].as_of,
                    "metrics": self.sections[key].metrics,
                    "failed_case_ids": self.sections[key].failed_case_ids,
                    "gate_failures": self.sections[key].gate_failures,
                }
                for key in SECTION_KEYS
            },
        }

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_json_dict(), indent=indent, default=str, sort_keys=True)


# ------------------------------------------------------------------ execution


def _internal_consistency_problems(report: EvaluationReport) -> list[str]:
    """Cheap cross-checks that the evaluator's own bookkeeping adds up."""
    if not hasattr(report, "metrics"):
        return ["evaluator produced no metrics"]
    metrics = report.metrics
    problems = []
    case_count = metrics.get("case_count")
    if case_count != report.case_count or report.case_count != len(report.results):
        problems.append(
            f"case_count mismatch: metrics={case_count}, "
            f"report={report.case_count}, results={len(report.results)}")
    if metrics.get("passed", 0) + metrics.get("failed", 0) != case_count:
        problems.append(
            f"passed ({metrics.get('passed')}) + failed ({metrics.get('failed')}) "
            f"!= case_count ({case_count})")
    observed_failed = sum(1 for result in report.results if not result.passed)
    if metrics.get("failed") != observed_failed:
        problems.append(
            f"failed count mismatch: metrics={metrics.get('failed')}, "
            f"actual failing results={observed_failed}")
    return problems


def evaluate_finance(db, thresholds: QualityThresholds) -> SectionResult:
    """Run the AI-12A/12B grounded finance evaluation as one gate section."""
    from app.evaluation.runner import format_report, ground_truth_consistency, run_dataset

    try:
        problems = ground_truth_consistency()
        if problems:
            return SectionResult(
                key=SECTION_FINANCE, status=ERROR, metrics={},
                error="finance dataset ground truth is inconsistent: "
                      + "; ".join(problems))
        report = run_dataset(db)
        consistency = _internal_consistency_problems(report)
        if report.case_count < thresholds.finance_min_cases or consistency:
            return SectionResult(
                key=SECTION_FINANCE, status=ERROR, metrics=report.metrics,
                as_of=report.as_of,
                error="; ".join(consistency) or
                      f"finance dataset produced {report.case_count} cases, "
                      f"minimum is {thresholds.finance_min_cases}",
                report_text=format_report(report))
    except Exception as exc:  # an evaluator that cannot execute is an ERROR
        return SectionResult(key=SECTION_FINANCE, status=ERROR, metrics={},
                             error=f"{type(exc).__name__}: {exc}")

    gate_failures = []
    for metric in _FINANCE_ACCURACY_METRICS:
        accuracy = report.metrics.get(metric)
        if accuracy is None or accuracy < thresholds.finance_min_accuracy:
            gate_failures.append(
                f"{metric}={accuracy} < required {thresholds.finance_min_accuracy}")
    return SectionResult(
        key=SECTION_FINANCE,
        status=FAIL if gate_failures else PASS,
        metrics=report.metrics,
        as_of=report.as_of,
        gate_failures=gate_failures,
        failed_case_ids=[result.case_id for result in report.results if not result.passed],
        report_text=format_report(report) if gate_failures else None)


def evaluate_categorization(db, thresholds: QualityThresholds) -> SectionResult:
    """Run the AI-12C categorization evaluation as one gate section."""
    from app.evaluation.categorization_metrics import format_categorization_report
    from app.evaluation.categorization_runner import run_dataset as run_categorization

    try:
        report = run_categorization(db, allow_llm=False, mode="rules_only")
        consistency = _internal_consistency_problems(report)
        if report.case_count < thresholds.min_cases or consistency:
            return SectionResult(
                key=SECTION_CATEGORIZATION, status=ERROR, metrics=report.metrics,
                as_of=None,  # categorization as_of is intentionally unused (date.today)
                error="; ".join(consistency) or
                      f"categorization dataset produced {report.case_count} cases, "
                      f"minimum is {thresholds.min_cases}",
                report_text=format_categorization_report(report))
    except Exception as exc:
        return SectionResult(key=SECTION_CATEGORIZATION, status=ERROR, metrics={},
                             error=f"{type(exc).__name__}: {exc}")

    metrics = report.metrics
    macro = metrics["macro_micro"]["macro_f1"]
    micro = metrics["macro_micro"]["micro_f1"]
    correction = metrics["correction_preservation"]
    guess_rate = metrics["ambiguity_guess_rate"]

    def below(value, maximum: float) -> bool:
        return value is None or value < maximum

    gate_failures = []
    if below(macro, thresholds.categorization_min_macro_f1):
        gate_failures.append(
            f"macro_f1={macro} < required {thresholds.categorization_min_macro_f1}")
    if below(micro, thresholds.categorization_min_micro_f1):
        gate_failures.append(
            f"micro_f1={micro} < required {thresholds.categorization_min_micro_f1}")
    if below(correction, thresholds.categorization_min_correction_preservation):
        gate_failures.append(
            f"correction_preservation={correction} < required "
            f"{thresholds.categorization_min_correction_preservation}")
    if (guess_rate is None or guess_rate > thresholds.categorization_max_guess_rate):
        gate_failures.append(
            f"ambiguity_guess_rate={guess_rate} > allowed "
            f"{thresholds.categorization_max_guess_rate}")
    return SectionResult(
        key=SECTION_CATEGORIZATION,
        status=FAIL if gate_failures else PASS,
        metrics=metrics,
        as_of=None,  # categorization as_of is intentionally unused (date.today)
        gate_failures=gate_failures,
        failed_case_ids=[result.case_id for result in report.results if not result.passed],
        report_text=format_categorization_report(report) if gate_failures else None)


def evaluate_recommendations(db, thresholds: QualityThresholds) -> SectionResult:
    """Run the AI-12D savings-recommendation evaluation as one gate section."""
    from app.evaluation.recommendation_metrics import format_recommendation_report
    from app.evaluation.recommendation_runner import run_recommendation_dataset

    try:
        report = run_recommendation_dataset(db)
        consistency = _internal_consistency_problems(report)
        if report.case_count < thresholds.min_cases or consistency:
            return SectionResult(
                key=SECTION_RECOMMENDATIONS, status=ERROR, metrics=report.metrics,
                as_of=report.as_of,
                error="; ".join(consistency) or
                      f"recommendation dataset produced {report.case_count} cases, "
                      f"minimum is {thresholds.min_cases}",
                report_text=format_recommendation_report(report))
    except Exception as exc:
        return SectionResult(key=SECTION_RECOMMENDATIONS, status=ERROR, metrics={},
                             error=f"{type(exc).__name__}: {exc}")

    metrics = report.metrics
    gate_failures = []
    for metric in _RECOMMENDATION_PERCENT_METRICS:
        value = metrics.get(metric)
        if value is None or value < thresholds.recommendation_min_percent:
            gate_failures.append(
                f"{metric}={value} < required {thresholds.recommendation_min_percent}")
    violations = metrics.get("isolation_violations")
    if violations is None or violations > thresholds.recommendation_max_isolation_violations:
        gate_failures.append(
            f"isolation_violations={violations} > allowed "
            f"{thresholds.recommendation_max_isolation_violations}")
    return SectionResult(
        key=SECTION_RECOMMENDATIONS,
        status=FAIL if gate_failures else PASS,
        metrics=metrics,
        as_of=report.as_of,
        gate_failures=gate_failures,
        failed_case_ids=[result.case_id for result in report.results if not result.passed],
        report_text=format_recommendation_report(report) if gate_failures else None)


def evaluate_insights(db, thresholds: QualityThresholds) -> SectionResult:
    """Run the AI-12D proactive-insight evaluation as one gate section."""
    from app.evaluation.insight_metrics import format_insight_report
    from app.evaluation.insight_runner import run_insight_dataset

    try:
        report = run_insight_dataset(db)
        consistency = _internal_consistency_problems(report)
        if report.case_count < thresholds.min_cases or consistency:
            return SectionResult(
                key=SECTION_INSIGHTS, status=ERROR, metrics=report.metrics,
                as_of=report.as_of,
                error="; ".join(consistency) or
                      f"insight dataset produced {report.case_count} cases, "
                      f"minimum is {thresholds.min_cases}",
                report_text=format_insight_report(report))
    except Exception as exc:
        return SectionResult(key=SECTION_INSIGHTS, status=ERROR, metrics={},
                             error=f"{type(exc).__name__}: {exc}")

    metrics = report.metrics
    gate_failures = []
    for metric in _INSIGHT_PERCENT_METRICS:
        value = metrics.get(metric)
        if value is None or value < thresholds.insight_min_percent:
            gate_failures.append(
                f"{metric}={value} < required {thresholds.insight_min_percent}")
    detection = metrics.get("detection_rate")
    if detection is None or detection < thresholds.insight_min_detection_rate:
        gate_failures.append(
            f"detection_rate={detection} < required {thresholds.insight_min_detection_rate}")
    false_alarms = metrics.get("false_alarm_rate")
    if false_alarms is None or false_alarms > thresholds.insight_max_false_alarm_rate:
        gate_failures.append(
            f"false_alarm_rate={false_alarms} > allowed "
            f"{thresholds.insight_max_false_alarm_rate}")
    violations = metrics.get("isolation_violations")
    if violations is None or violations > thresholds.insight_max_isolation_violations:
        gate_failures.append(
            f"isolation_violations={violations} > allowed "
            f"{thresholds.insight_max_isolation_violations}")
    return SectionResult(
        key=SECTION_INSIGHTS,
        status=FAIL if gate_failures else PASS,
        metrics=metrics,
        as_of=report.as_of,
        gate_failures=gate_failures,
        failed_case_ids=[result.case_id for result in report.results if not result.passed],
        report_text=format_insight_report(report) if gate_failures else None)


EVALUATORS = {
    SECTION_FINANCE: evaluate_finance,
    SECTION_CATEGORIZATION: evaluate_categorization,
    SECTION_RECOMMENDATIONS: evaluate_recommendations,
    SECTION_INSIGHTS: evaluate_insights,
}


def run_quality_gate(db=None, thresholds: QualityThresholds | None = None) -> QualityGateResult:
    """Run every offline AI evaluation suite and aggregate the results.

    ``db`` defaults to a fresh in-memory SQLite session so the gate never
    touches real user data or a provider.
    """
    import app.models  # noqa: F401  (register ORM models before create_all)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base

    owned = db is None
    if owned:
        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()

    thresholds = thresholds or QualityThresholds()
    try:
        sections = {key: evaluator(db, thresholds) for key, evaluator in EVALUATORS.items()}
        return QualityGateResult(sections=sections, thresholds=thresholds)
    finally:
        if owned:
            db.close()
            engine.dispose()


# -------------------------------------------------------------------- reports


def _cell(value) -> str:
    """Render a fraction-scale metric (0-1)."""
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _pct(value) -> str:
    """Render a percent-scale metric (0-100)."""
    return "n/a" if value is None else f"{value:.1f}%"


def format_quality_report(result: QualityGateResult) -> str:
    """Render the developer-facing AI quality report."""
    width = 62
    finance = result.sections[SECTION_FINANCE].metrics
    categorization = result.sections[SECTION_CATEGORIZATION].metrics
    recommendations = result.sections[SECTION_RECOMMENDATIONS].metrics
    insights = result.sections[SECTION_INSIGHTS].metrics

    lines = [
        "AI QUALITY REPORT",
        "─" * width,
        "PorerHishab",
        "Evaluation snapshot: "
        + ", ".join(
            f"{key}: as_of={result.sections[key].as_of if result.sections[key].as_of else 'n/a'}"
            for key in SECTION_KEYS),
        "",
    ]

    lines += [
        "Finance / Grounded Chat",
        f"Cases: {finance.get('case_count', 'n/a')}   "
        f"Passed: {finance.get('passed', 'n/a')}   "
        f"Failed: {finance.get('failed', 'n/a')}",
        f"Intent: {_pct(finance.get('intent_accuracy'))}   "
        f"Date: {_pct(finance.get('date_accuracy'))}   "
        f"Numeric: {_pct(finance.get('numeric_accuracy'))}",
        f"Status: {_pct(finance.get('status_accuracy'))}   "
        f"Grounding: {_pct(finance.get('grounding_accuracy'))}   "
        f"Safety: {_pct(finance.get('safety_accuracy'))}",
        "",
    ]

    macro = categorization.get("macro_micro") or {}
    lines += [
        "Categorization",
        f"Cases: {categorization.get('case_count', 'n/a')}   "
        f"Passed: {categorization.get('passed', 'n/a')}   "
        f"Failed: {categorization.get('failed', 'n/a')}",
        f"Rule coverage: {_cell(categorization.get('rule_coverage'))}   "
        f"Fallback: {_cell(categorization.get('provider_fallback_rate'))}",
        f"Corrections preserved: {_cell(categorization.get('correction_preservation'))}   "
        f"Ambiguous guessed: {_cell(categorization.get('ambiguity_guess_rate'))}",
        f"Macro F1: {_pct(macro.get('macro_f1'))}   "
        f"Micro F1: {_cell(macro.get('micro_f1'))}",
        "",
    ]

    lines += [
        "Recommendations",
        f"Cases: {recommendations.get('case_count', 'n/a')}   "
        f"Passed: {recommendations.get('passed', 'n/a')}   "
        f"Failed: {recommendations.get('failed', 'n/a')}",
        f"Grounding: {_pct(recommendations.get('grounding_accuracy'))}   "
        f"Arithmetic: {_pct(recommendations.get('arithmetic_accuracy'))}",
        f"Estimate labeling: {_pct(recommendations.get('estimate_labeling_rate'))}   "
        f"No double counting: {_pct(recommendations.get('no_double_counting_rate'))}",
        f"Personalization: {_pct(recommendations.get('personalization_rate'))}   "
        f"Data sufficiency: {_pct(recommendations.get('data_sufficiency_rate'))}   "
        f"Isolation violations: {recommendations.get('isolation_violations', 'n/a')}",
        "",
    ]

    lines += [
        "Insights",
        f"Cases: {insights.get('case_count', 'n/a')}   "
        f"Passed: {insights.get('passed', 'n/a')}   "
        f"Failed: {insights.get('failed', 'n/a')}",
        f"Triggered: {insights.get('triggered_cases', 'n/a')}   "
        f"Silent: {insights.get('silent_cases', 'n/a')}",
        f"Presence: {_pct(insights.get('presence_accuracy'))}   "
        f"Numbers: {_pct(insights.get('numbers_accuracy'))}   "
        f"Dates: {_pct(insights.get('dates_accuracy'))}",
        f"Plan-labeling: {_pct(insights.get('plan_labeling_accuracy'))}   "
        f"Isolation violations: {insights.get('isolation_violations', 'n/a')}",
        f"Detection rate: {_cell(insights.get('detection_rate'))}   "
        f"False-alarm rate: {_cell(insights.get('false_alarm_rate'))}",
        "",
    ]

    for key in SECTION_KEYS:
        section = result.sections[key]
        if section.status == FAIL:
            lines.append(f"{key.title()} gate failures:")
            lines.extend(f"  - {message}" for message in section.gate_failures)
            if section.report_text:
                lines.append(section.report_text)
        elif section.status == ERROR:
            lines.append(f"{key.title()} ERROR: {section.error}")
            if section.report_text:
                lines.append(section.report_text)

    lines += ["─" * width, f"OVERALL: {result.overall}", "─" * width]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. 0 = PASS, 1 = FAIL, 2 = ERROR.

    ``--json`` emits the machine-readable aggregate instead of the
    human-readable report; both describe the same run.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    result = run_quality_gate()
    if "--json" in argv:
        print(result.to_json(indent=2))
    else:
        print(format_quality_report(result))
    return {PASS: 0, FAIL: 1, ERROR: 2}[result.overall]


if __name__ == "__main__":
    raise SystemExit(main())

