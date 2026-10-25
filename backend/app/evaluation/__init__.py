"""AI evaluation layer (AI-12A foundation, AI-12C categorization, AI-12D
recommendations and proactive insights, AI-12E quality gate).

Evaluation is deliberately offline: every case runs the deterministic
pipeline against seeded or labeled ground truth and compares structured
fields with expectations derived independently of the system under test.
"""
from app.evaluation.metrics import (
    SCORE_DIMENSIONS,
    CaseResult,
    EvaluationReport,
    numeric_score,
    summarize,
)
from app.evaluation.runner import (
    EVALUATION_CASES,
    EVALUATION_SCENARIO,
    EVALUATION_SCENARIO_AS_OF,
    format_report,
    ground_truth_consistency,
    run_case,
    run_dataset,
)
from app.evaluation.datasets.finance_scenario import AS_OF

from app.evaluation.datasets.categorization_cases import (
    CATEGORIZATION_EVALUATION_CASES,
)
from app.evaluation.categorization_metrics import (
    CategorizationOutcome,
    CategorizationReport,
    CategoryMetrics,
    ambiguity_handling,
    categorization_prf,
    correction_preservation,
    macro_micro,
    pathway_rates,
    summarize_categorization,
)
from app.evaluation.categorization_runner import (
    CATEGORIZATION_SCORE_DIMENSIONS,
    run_case as run_categorization_case,
    run_dataset as run_categorization_dataset,
    validate_dataset,
)
from app.evaluation.categorization_metrics import format_categorization_report

# -- AI-12D: proactive insights ------------------------------------------------
from app.evaluation.datasets.insight_scenarios import (
    INSIGHT_EVALUATION_CASES,
    INSIGHT_ISOLATION_MARKERS,
    KNOWN_INSIGHT_TYPES,
    INSIGHT_AS_OF,
    validate_insight_dataset,
)
from app.evaluation.insight_metrics import (
    InsightOutcome,
    InsightReport,
    detection_rates,
    format_insight_report,
    summarize_insights,
)
from app.evaluation.insight_runner import (
    INSIGHT_SCORE_DIMENSIONS,
    run_insight_case,
    run_insight_dataset,
)

# -- AI-12D: savings recommendations ------------------------------------------
from app.evaluation.datasets.recommendation_cases import (
    ARITHMETIC_TOLERANCE,
    COACH_CASES,
    PLAN_CASES,
    RECOMMENDATION_AS_OF,
    validate_recommendation_dataset,
)
from app.evaluation.recommendation_metrics import (
    RECOMMENDATION_SCORE_DIMENSIONS,
    RecommendationOutcome,
    RecommendationReport,
    format_recommendation_report,
    summarize_recommendations,
)
from app.evaluation.recommendation_runner import (
    run_coach_case,
    run_plan_case,
    run_recommendation_dataset,
)

# -- AI-12E: quality gate -------------------------------------------------------
# Imported lazily (PEP 562) so ``python -m app.evaluation.quality_gate`` does
# not emit the runpy re-import warning.
_GATE_EXPORTS = {
    "PASS": "PASS", "FAIL": "FAIL", "ERROR": "ERROR",
    "QualityThresholds": "QualityThresholds",
    "QualityGateResult": "QualityGateResult",
    "SectionResult": "SectionResult",
    "format_quality_report": "format_quality_report",
    "run_quality_gate": "run_quality_gate",
    "run_quality_gate_main": "main",
}


def __getattr__(name):  # noqa: D103 - PEP 562 lazy attribute
    export = _GATE_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module("app.evaluation.quality_gate")
    value = getattr(module, export)
    globals()[name] = value
    return value


__all__ = [
    "SCORE_DIMENSIONS",
    "CaseResult",
    "EvaluationReport",
    "numeric_score",
    "summarize",
    "EVALUATION_CASES",
    "EVALUATION_SCENARIO",
    "EVALUATION_SCENARIO_AS_OF",
    "format_report",
    "ground_truth_consistency",
    "run_case",
    "run_dataset",
    "AS_OF",
    "CATEGORIZATION_EVALUATION_CASES",
    "CATEGORIZATION_SCORE_DIMENSIONS",
    "CategorizationOutcome",
    "CategorizationReport",
    "CategoryMetrics",
    "ambiguity_handling",
    "categorization_prf",
    "correction_preservation",
    "macro_micro",
    "pathway_rates",
    "summarize_categorization",
    "format_categorization_report",
    "run_categorization_case",
    "run_categorization_dataset",
    "validate_dataset",
    # AI-12D insights
    "INSIGHT_EVALUATION_CASES",
    "INSIGHT_ISOLATION_MARKERS",
    "KNOWN_INSIGHT_TYPES",
    "INSIGHT_AS_OF",
    "INSIGHT_SCORE_DIMENSIONS",
    "InsightOutcome",
    "InsightReport",
    "detection_rates",
    "format_insight_report",
    "summarize_insights",
    "run_insight_case",
    "run_insight_dataset",
    "validate_insight_dataset",
    # AI-12D recommendations
    "ARITHMETIC_TOLERANCE",
    "PLAN_CASES",
    "COACH_CASES",
    "RECOMMENDATION_AS_OF",
    "RECOMMENDATION_SCORE_DIMENSIONS",
    "RecommendationOutcome",
    "RecommendationReport",
    "format_recommendation_report",
    "summarize_recommendations",
    "run_coach_case",
    "run_plan_case",
    "run_recommendation_dataset",
    "validate_recommendation_dataset",
    # AI-12E quality gate
    "PASS",
    "FAIL",
    "ERROR",
    "QualityThresholds",
    "QualityGateResult",
    "SectionResult",
    "format_quality_report",
    "run_quality_gate",
    "run_quality_gate_main",
]
