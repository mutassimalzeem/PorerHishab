"""Insight-specific metrics (AI-12D).

Metrics operate on :class:`InsightOutcome` records computed from the *actual*
nudges payloads, so detection rates never depend on natural-language wording.
Each expected insight type in each case is classified as:

* ``tp`` — condition true in the scenario and the insight appeared;
* ``fn`` — condition true and the insight is missing;
* ``fp`` — condition false and the insight appeared anyway;
* ``tn`` — condition false and the insight correctly stayed silent.

Presence is scored per *type* per case, while number/date accuracy is scored
per pinned check, so a missing insight does not silently excuse wrong
numbers elsewhere in the same payload.
"""
from dataclasses import dataclass, field

from app.evaluation.metrics import EvaluationReport


@dataclass(frozen=True)
class InsightOutcome:
    """Flattened trace of one evaluated insight case."""

    case_id: str
    behavior: str                       # "triggered" | "silent"
    expected_status: str
    observed_status: str
    type_results: dict[str, str]        # type -> "tp" | "fn" | "fp" | "tn"
    numeric_checks: int = 0
    numeric_passed: int = 0
    date_checks: int = 0
    date_passed: int = 0
    plan_checks: int = 0
    plan_passed: int = 0
    isolation_ok: bool = True
    unexpected_types: int = 0


def detection_rates(outcomes) -> dict[str, dict]:
    """Per-type TP/FN/FP/TN with detection and false-alarm rates."""
    per_type: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        for insight_type, verdict in outcome.type_results.items():
            bucket = per_type.setdefault(
                insight_type, {"tp": 0, "fn": 0, "fp": 0, "tn": 0})
            bucket[verdict] = bucket.get(verdict, 0) + 1

    report: dict[str, dict] = {}
    for insight_type, counts in per_type.items():
        detected = counts["tp"] + counts["fn"]
        conditions = counts["tn"] + counts["fp"]
        report[insight_type] = {
            **counts,
            "detection_rate": (counts["tp"] / detected) if detected else None,
            "false_alarm_rate": (counts["fp"] / conditions) if conditions else None,
        }
    return report


def summarize_insights(outcomes, results, as_of) -> dict:
    """Aggregate the AI-12D insight report metrics."""
    metrics: dict[str, object] = {
        "case_count": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
        "triggered_cases": sum(1 for outcome in outcomes if outcome.behavior == "triggered"),
        "silent_cases": sum(1 for outcome in outcomes if outcome.behavior == "silent"),
        "presence_accuracy": _accuracy(result.scores.get("presence") for result in results),
        "numbers_accuracy": _accuracy(result.scores.get("numbers") for result in results),
        "dates_accuracy": _accuracy(result.scores.get("dates") for result in results),
        "plan_labeling_accuracy": _accuracy(
            result.scores.get("plan_labeling") for result in results),
        "isolation_violations": sum(
            1 for result in results if result.scores.get("isolation") == 0.0),
        "numeric_checks": sum(outcome.numeric_checks for outcome in outcomes),
        "numeric_passed": sum(outcome.numeric_passed for outcome in outcomes),
        "date_checks": sum(outcome.date_checks for outcome in outcomes),
        "date_passed": sum(outcome.date_passed for outcome in outcomes),
        "detection": detection_rates(outcomes),
    }
    flat = detection_rates(outcomes)
    tp = sum(counts["tp"] for counts in flat.values())
    fn = sum(counts["fn"] for counts in flat.values())
    fp = sum(counts["fp"] for counts in flat.values())
    tn = sum(counts["tn"] for counts in flat.values())
    metrics["detection_rate"] = (tp / (tp + fn)) if (tp + fn) else None
    metrics["false_alarm_rate"] = (fp / (fp + tn)) if (fp + tn) else None
    return metrics


def _accuracy(values) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable) * 100, 1)


@dataclass
class InsightReport(EvaluationReport):
    """AI-12A report shape plus the insight outcome trace."""

    outcomes: list = field(default_factory=list)


def format_insight_report(report: InsightReport) -> str:
    """Render the console summary for CI logs."""
    def cell(value) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"

    def pct(value) -> str:
        return "n/a" if value is None else f"{value:.1f}%"

    lines = [
        "Proactive Insight Evaluation (AI-12D)",
        "─" * 62,
        f"Cases: {report.case_count}   Triggered: {report.metrics['triggered_cases']}   "
        f"Silent: {report.metrics['silent_cases']}   "
        f"Passed: {report.passed_count}   Failed: {report.failed_count}",
        f"Presence: {pct(report.metrics['presence_accuracy'])}   "
        f"Numbers: {pct(report.metrics['numbers_accuracy'])}   "
        f"Dates: {pct(report.metrics['dates_accuracy'])}",
        f"Plan-marking: {pct(report.metrics['plan_labeling_accuracy'])}   "
        f"Isolation violations: {report.metrics['isolation_violations']}",
        f"Overall detection: {cell(report.metrics['detection_rate'])}   "
        f"False alarms: {cell(report.metrics['false_alarm_rate'])}",
        "─" * 62,
        f"{'insight type':<24}{'TP':>6}{'FN':>6}{'FP':>6}{'TN':>6}{'det.':>9}{'alarm':>9}",
    ]
    for insight_type, counts in sorted(report.metrics["detection"].items()):
        lines.append(
            f"{insight_type:<24}{counts['tp']:>6}{counts['fn']:>6}{counts['fp']:>6}"
            f"{counts['tn']:>6}{cell(counts['detection_rate']):>9}{cell(counts['false_alarm_rate']):>9}")
    lines.append("─" * 62)
    lines.append("Status: " + ("ALL CASES PASSED" if report.passed else "REGRESSIONS DETECTED"))
    for result in report.results:
        if not result.passed:
            lines.append(f"  FAIL {result.case_id} ({result.observed_status}):")
            lines.extend(f"         - {failure}" for failure in result.failures)
    return "\n".join(lines)
