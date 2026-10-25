"""Recommendation-specific metrics (AI-12D).

Operates on :class:`RecommendationOutcome` traces recorded by the runner.
Rates are computed per structured property, so wording quality is reported
separately from arithmetic: a recommendation that paraphrases beautifully but
quotes the wrong amount still fails the arithmetic dimension.
"""
from dataclasses import dataclass, field

from app.evaluation.metrics import EvaluationReport

RECOMMENDATION_SCORE_DIMENSIONS = (
    "grounding", "arithmetic", "estimate_labeling", "no_double_counting",
    "personalization", "data_sufficiency", "isolation")


@dataclass(frozen=True)
class RecommendationOutcome:
    """Flattened trace of one evaluated recommendation case."""

    case_id: str
    group: str
    source: str                       # "plan" | "coach"
    grounding_checks: int = 0
    grounding_passed: int = 0
    arithmetic_checks: int = 0
    arithmetic_passed: int = 0
    labeling_ok: bool = True
    double_counting_ok: bool = True
    personalization_ok: bool = True
    data_sufficiency_ok: bool = True
    isolation_ok: bool = True


def summarize_recommendations(outcomes, results, as_of) -> dict:
    """Aggregate the AI-12D recommendation report metrics."""
    metrics: dict[str, object] = {
        "case_count": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
        "grounding_checks": sum(o.grounding_checks for o in outcomes),
        "grounding_passed": sum(o.grounding_passed for o in outcomes),
        "arithmetic_checks": sum(o.arithmetic_checks for o in outcomes),
        "arithmetic_passed": sum(o.arithmetic_passed for o in outcomes),
        "grounding_accuracy": _accuracy(result.scores.get("grounding") for result in results),
        "arithmetic_accuracy": _ratio(
            sum(outcome.arithmetic_checks for outcome in outcomes),
            sum(outcome.arithmetic_passed for outcome in outcomes)),
        "estimate_labeling_rate": _rate(o.labeling_ok for o in outcomes),
        "no_double_counting_rate": _rate(o.double_counting_ok for o in outcomes),
        "personalization_rate": _rate(o.personalization_ok for o in outcomes),
        "data_sufficiency_rate": _rate(o.data_sufficiency_ok for o in outcomes),
        "isolation_violations": sum(1 for outcome in outcomes if not outcome.isolation_ok),
        "by_source": {},
    }
    by_source: dict[str, dict] = {}
    for outcome in outcomes:
        bucket = by_source.setdefault(outcome.source, {"cases": 0, "passed": 0})
        bucket["cases"] += 1
        bucket["passed"] += 1 if outcome.data_sufficiency_ok and outcome.labeling_ok else 0
    metrics["by_source"] = by_source
    return metrics


def _accuracy(values) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable) * 100, 1)


def _ratio(checks: int, passed: int) -> float | None:
    return round(passed / checks * 100, 1) if checks else None


def _rate(values) -> float | None:
    values = list(values)
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values) * 100, 1)


@dataclass
class RecommendationReport(EvaluationReport):
    """AI-12A report shape plus the recommendation outcome trace."""

    outcomes: list = field(default_factory=list)


def format_recommendation_report(report: RecommendationReport) -> str:
    """Render the console summary for CI logs."""
    def pct(value) -> str:
        return "n/a" if value is None else f"{value:.1f}%"

    metrics = report.metrics
    lines = [
        "Savings Recommendation Evaluation (AI-12D)",
        "─" * 62,
        f"Cases: {report.case_count}   Passed: {report.passed_count}   "
        f"Failed: {report.failed_count}",
        f"Grounding: {pct(metrics['grounding_accuracy'])}   "
        f"Arithmetic: {pct(metrics['arithmetic_accuracy'])}   "
        f"({metrics['arithmetic_passed']}/{metrics['arithmetic_checks']} amount checks)",
        f"Estimate labeling: {pct(metrics['estimate_labeling_rate'])}   "
        f"No double counting: {pct(metrics['no_double_counting_rate'])}",
        f"Personalization: {pct(metrics['personalization_rate'])}   "
        f"Data sufficiency: {pct(metrics['data_sufficiency_rate'])}   "
        f"Isolation violations: {metrics['isolation_violations']}",
        f"Sources: {metrics['by_source']}",
        "─" * 62,
        "Status: " + ("ALL CASES PASSED" if report.passed else "REGRESSIONS DETECTED"),
    ]
    for result in report.results:
        if not result.passed:
            lines.append(f"  FAIL {result.case_id} ({result.observed_status}):")
            lines.extend(f"         - {failure}" for failure in result.failures)
    return "\n".join(lines)
