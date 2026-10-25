"""AI evaluation layer (AI-12A foundation, AI-12C categorization).

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
]
