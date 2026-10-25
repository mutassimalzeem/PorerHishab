"""Categorization-specific metrics (AI-12C).

Works on :class:`CategorizationOutcome` records produced by the runner, so
pathway rates are computed from the *actual execution path* recorded on each
result (``method``), never inferred from the final category.

Ground truth and confidence
---------------------------
Only cases that carry ground truth about a *confident* outcome enter the
precision / recall / F1 machinery:

* ``rule_classify`` cases — the labeled category is the ground truth.
* Confident predictions (``method`` in ``rule``/``llm``/``user_preference``)
  on any ground-truth case are a hit (TP) or a miss (FP for the predicted
  category + FN for the expected one).
* A *confident* prediction on a case that has no ground-truth category
  (ambiguous / unknown / malformed-with-garbage) is always an FP — guessing
  on uncertain input must never buy a score.
* ``Uncategorized`` is a *state*, not a category: fallback predictions never
  enter the precision/recall matrices.

``user_correction`` / ``custom_category`` cases are scored on precedence
(correction preservation), not on the classifier's judgement — the corrected
label is right by construction, so its TP would only inflate metrics.

Categories with no positive predictions or no ground-truth support get
``precision``/``recall`` = ``None`` (explicitly handled, never 0.0), and they
are excluded from macro aggregates.
"""
from dataclasses import dataclass, field

from app.evaluation.metrics import CaseResult, EvaluationReport


#: Methods that carry a confident classification decision.
CONFIDENT_METHODS = frozenset({"rule", "llm", "user_preference"})

#: Execution-path names for the pathway-rate metrics.
RULE_PATH = "rule"
LLM_PATH = "llm"
FALLBACK_PATH = "fallback"


@dataclass(frozen=True)
class CategorizationOutcome:
    """Flattened trace of one evaluated case."""

    case_id: str
    group: str
    behavior: str
    is_ambiguous: bool
    is_mixed_language: bool
    eligible: bool
    expected_category: str | None
    observed_category: str | None
    observed_method: str
    corrected_category: str | None = None

    @property
    def confident(self) -> bool:
        return self.observed_method in CONFIDENT_METHODS


@dataclass
class CategoryMetrics:
    """Per-category confusion counts with optional precision/recall/F1."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    support: int = 0
    predicted: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None

    def compute_scores(self) -> "CategoryMetrics":
        """Fill precision/recall/F1 after counts are aggregated."""
        self.precision = (self.tp / (self.tp + self.fp)) if self.predicted else None
        self.recall = (self.tp / (self.tp + self.fn)) if self.support else None
        if self.precision is None or self.recall is None:
            self.f1 = None
        elif self.precision + self.recall == 0:
            self.f1 = 0.0
        else:
            self.f1 = 2 * self.precision * self.recall / (self.precision + self.recall)
        return self


def categorization_prf(outcomes) -> dict[str, CategoryMetrics]:
    """Per-category TP/FP/FN/support/predicted + precision/recall/F1.

    ``user_correction`` / ``custom_category`` outcomes are excluded: the
    corrected label is right by construction, so both its TP and its FP
    would be noise.  Those cases are measured by
    :func:`correction_preservation` instead.
    """
    metrics: dict[str, CategoryMetrics] = {}

    for outcome in outcomes:
        if outcome.behavior in ("user_correction", "custom_category"):
            continue
        expected = outcome.expected_category
        if expected is not None:
            bucket = _metric(metrics, expected)
            bucket.support += 1
            if outcome.confident and outcome.observed_category == expected:
                bucket.tp += 1
            else:
                bucket.fn += 1

        if outcome.confident and outcome.observed_category is not None:
            predicted = _metric(metrics, outcome.observed_category)
            if expected is not None and outcome.observed_category == expected:
                pass  # already counted as TP
            else:
                predicted.fp += 1
            predicted.predicted += 1

    return {category: metric.compute_scores() for category, metric in metrics.items()}


def _metric(metrics: dict, category: str) -> CategoryMetrics:
    if category not in metrics:
        metrics[category] = CategoryMetrics()
    return metrics[category]


def macro_micro(per_category: dict[str, CategoryMetrics]) -> dict:
    """Macro (mean over categories with definable scores) and micro F1."""
    defined = [
        metric for metric in per_category.values()
        if metric.precision is not None and metric.recall is not None
    ]
    total_tp = sum(metric.tp for metric in per_category.values())
    total_fp = sum(metric.fp for metric in per_category.values())
    total_fn = sum(metric.fn for metric in per_category.values())

    micro_precision = (total_tp / (total_tp + total_fp)) if (total_tp + total_fp) else None
    micro_recall = (total_tp / (total_tp + total_fn)) if (total_tp + total_fn) else None
    if micro_precision is None or micro_recall is None or micro_precision + micro_recall == 0:
        micro_f1 = 0.0 if (micro_precision is not None and micro_recall is not None) else None
    else:
        micro_f1 = 2 * micro_precision * micro_recall / (
            micro_precision + micro_recall)

    def macro(values) -> float | None:
        return round(sum(values) / len(values) * 100, 1) if values else None

    return {
        "macro_precision": macro([m.precision for m in defined]),
        "macro_recall": macro([m.recall for m in defined]),
        "macro_f1": macro([m.f1 for m in defined]),
        "macro_categories": len(defined),
        "micro_precision": micro_precision,
        "micro_recall": micro_recall,
        "micro_f1": micro_f1,
        "micro_tp": total_tp,
        "micro_fp": total_fp,
        "micro_fn": total_fn,
        "categories_scored": len(per_category),
    }


def pathway_rates(outcomes) -> dict:
    """Rule coverage and provider-fallback rates from real execution paths.

    ``eligible`` = the transaction had text the pipeline could act on;
    blank-input cases (``eligible=False``) cannot be classified by anything
    and are therefore excluded from both denominators.
    """
    eligible = [outcome for outcome in outcomes if outcome.eligible]
    if not eligible:
        return {
            "eligible": 0,
            "rule_coverage": None,
            "provider_fallback_rate": None,
            "llm_path_rate": None,
            "by_path": {},
        }

    def count(*methods: str) -> int:
        return sum(1 for outcome in eligible if outcome.observed_method in methods)

    rule_hits = count(RULE_PATH)
    llm_hits = count(LLM_PATH)
    fallback_hits = count(FALLBACK_PATH)
    by_path: dict[str, int] = {}
    for outcome in eligible:
        by_path[outcome.observed_method] = by_path.get(outcome.observed_method, 0) + 1
    return {
        "eligible": len(eligible),
        "rule_coverage": rule_hits / len(eligible),
        "provider_fallback_rate": (llm_hits + fallback_hits) / len(eligible),
        "llm_path_rate": llm_hits / len(eligible),
        "by_path": by_path,
    }


def correction_preservation(outcomes) -> float | None:
    """Confirmed corrections that took precedence over system predictions."""
    cases = [
        outcome for outcome in outcomes
        if outcome.behavior in ("user_correction", "custom_category")
    ]
    if not cases:
        return None
    preserved = sum(
        1 for outcome in cases
        if outcome.observed_method == "user_preference"
        and outcome.observed_category == outcome.corrected_category
    )
    return preserved / len(cases)


def ambiguity_handling(outcomes) -> dict:
    """Uncertain cases reported separately from confident classifications.

    ``guess_rate`` — ambiguous cases where the engine still assigned a
    confident category.  A lucky guess must not score; these rates expose it.
    """
    ambiguous = [outcome for outcome in outcomes if outcome.is_ambiguous]
    if not ambiguous:
        return {"ambiguous_cases": 0, "guess_rate": None, "safe_uncertainty_rate": None}
    guessed = sum(1 for outcome in ambiguous if outcome.confident)
    guess_rate = guessed / len(ambiguous)
    return {
        "ambiguous_cases": len(ambiguous),
        "guess_rate": guess_rate,
        "safe_uncertainty_rate": 1.0 - guess_rate,
    }


def summarize_categorization(
    outcomes,
    results: list[CaseResult],
    mode: str,
) -> dict:
    """Build the full metrics dict for one categorization report run."""
    per_category = categorization_prf(outcomes)
    pathways = pathway_rates(outcomes)
    ambiguity = ambiguity_handling(outcomes)
    metrics: dict[str, object] = {
        "mode": mode,
        "case_count": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
        "rule_coverage": pathways["rule_coverage"],
        "provider_fallback_rate": pathways["provider_fallback_rate"],
        "llm_path_rate": pathways["llm_path_rate"],
        "correction_preservation": correction_preservation(outcomes),
        "ambiguous_cases": ambiguity["ambiguous_cases"],
        "ambiguity_guess_rate": ambiguity["guess_rate"],
        "ambiguity_safe_rate": ambiguity["safe_uncertainty_rate"],
        "macro_micro": macro_micro(per_category),
    }
    metrics["per_category"] = {
        category: {
            "precision": metric.precision,
            "recall": metric.recall,
            "f1": metric.f1,
            "support": metric.support,
            "predicted": metric.predicted,
            "tp": metric.tp,
            "fp": metric.fp,
            "fn": metric.fn,
        }
        for category, metric in sorted(per_category.items())
    }
    metrics["pathways"] = pathways["by_path"]
    return metrics


@dataclass
class CategorizationReport(EvaluationReport):
    """AI-12A report shape plus the outcome trace and run mode."""

    mode: str = "rules_only"
    outcomes: list = field(default_factory=list)


def format_categorization_report(report: CategorizationReport) -> str:
    """Render the console summary for CI logs."""
    def cell(value) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"

    line_1 = f"Rule coverage: {cell(report.metrics['rule_coverage'])}"
    line_1 += f"   Fallback: {cell(report.metrics['provider_fallback_rate'])}"
    line_1 += f"   LLM path: {cell(report.metrics['llm_path_rate'])}"
    line_2 = (f"Corrections preserved: {cell(report.metrics['correction_preservation'])}"
              f"   Ambiguous guessed: {cell(report.metrics['ambiguity_guess_rate'])}")
    lines = [
        "Categorization Evaluation",
        "─" * 62,
        f"Mode: {report.mode}   Cases: {report.case_count}   "
        f"Passed: {report.passed_count}   Failed: {report.failed_count}",
        line_1,
        line_2,
        "─" * 62,
    ]
    aggregates = report.metrics["macro_micro"]
    macro_f1 = aggregates["macro_f1"]
    micro_f1 = aggregates["micro_f1"]
    lines.append(
        f"Macro F1: {'n/a' if macro_f1 is None else f'{macro_f1:.1f}%'}   "
        f"Micro F1: {'n/a' if micro_f1 is None else f'{micro_f1 * 100:.1f}%'}"
    )
    lines.append(f"{'category':<20}{'P':>8}{'R':>8}{'F1':>8}{'sup':>6}{'pred':>6}")
    for category, stats in report.metrics["per_category"].items():
        precision = stats["precision"]
        recall = stats["recall"]
        f1 = stats["f1"]
        lines.append(f"{category:<20}"
                     f"{'n/a' if precision is None else f'{precision:.3f}':>8}"
                     f"{'n/a' if recall is None else f'{recall:.3f}':>8}"
                     f"{'n/a' if f1 is None else f'{f1:.3f}':>8}"
                     f"{stats['support']:>6}{stats['predicted']:>6}")
    lines.append("─" * 62)
    lines.append("Status: " + ("ALL CASES PASSED" if report.passed else "REGRESSIONS DETECTED"))
    for result in report.results:
        if not result.passed:
            lines.append(f"  FAIL {result.case_id} ({result.observed_status}):")
            lines.extend(f"         - {failure}" for failure in result.failures)
    return "\n".join(lines)
