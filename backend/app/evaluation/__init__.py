"""AI finance evaluation layer (AI-12A foundation).

Evaluation is deliberately offline: every case runs the deterministic finance
coach against a seeded scenario and compares structured fields with ground
truth derived independently from the scenario specification.
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
]
