"""Result structures, scoring rules, and aggregate metrics for evaluation.

Metrics operate on structured case scores. A score is 1.0 (pass), 0.0 (fail),
or None when the dimension does not apply to the case; aggregates exclude the
None entries so, for example, unsupported questions never dilute numeric
accuracy.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

SCORE_DIMENSIONS = ("intent", "date", "numeric", "status", "grounding", "safety")


def numeric_score(expected, actual, tolerance: Decimal = Decimal("0")) -> float:
    """Score one numeric expectation.

    Exact equality gives 1.0 by default; tolerance exists for forward-looking
    estimates (forecasting, recommendations) where close is correct.
    """
    if expected is None or actual is None:
        return 1.0 if expected is actual is None else 0.0
    expected, actual = Decimal(str(expected)), Decimal(str(actual))
    return 1.0 if abs(expected - actual) <= tolerance else 0.0


@dataclass
class CaseResult:
    case_id: str
    group: str
    expected_status: str
    observed_status: str
    scores: dict[str, float | None]
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _accuracy(values) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable) * 100, 1)


@dataclass
class EvaluationReport:
    as_of: date
    case_count: int
    results: list[CaseResult]
    metrics: dict[str, object] = field(default_factory=dict)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_count(self) -> int:
        return self.case_count - self.passed_count

    @property
    def passed(self) -> bool:
        return self.failed_count == 0 and self.case_count > 0


def summarize(results: list[CaseResult], as_of: date) -> dict:
    """Aggregate per-dimension accuracy plus pass/fail counts."""
    metrics: dict[str, object] = {
        "case_count": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
    }
    for dimension in SCORE_DIMENSIONS:
        metrics[f"{dimension}_accuracy"] = _accuracy(
            result.scores.get(dimension) for result in results)
    metrics["unsupported_question_accuracy"] = _accuracy(
        result.scores.get("status") for result in results if result.group == "unsupported")
    by_group: dict[str, dict] = {}
    for result in results:
        bucket = by_group.setdefault(result.group, {"cases": 0, "passed": 0})
        bucket["cases"] += 1
        bucket["passed"] += 1 if result.passed else 0
    metrics["by_group"] = by_group
    return metrics


def format_report(report: EvaluationReport) -> str:
    """Render the console summary used in CI logs."""
    def row(label, value):
        return f"{label:<24}{value}"

    lines = [
        "AI Finance Evaluation",
        "─" * 42,
        row(f"Cases: {report.case_count}", ""),
        row("Passed:", report.passed_count),
        row("Failed:", report.failed_count),
        "",
    ]
    for dimension in SCORE_DIMENSIONS:
        accuracy = report.metrics.get(f"{dimension}_accuracy")
        shown = "n/a" if accuracy is None else f"{accuracy:.1f}%"
        lines.append(row(f"{dimension.capitalize()} accuracy:", shown))
    unsupported = report.metrics.get("unsupported_question_accuracy")
    if unsupported is not None:
        lines.append(row("Unsupported accuracy:", f"{unsupported:.1f}%"))
    lines.append("─" * 42)
    lines.append("Status: " + ("ALL CASES PASSED" if report.passed else "REGRESSIONS DETECTED"))
    for result in report.results:
        if not result.passed:
            lines.append(f"  FAIL {result.case_id} ({result.observed_status}):")
            lines.extend(f"         - {failure}" for failure in result.failures)
    return "\n".join(lines)
