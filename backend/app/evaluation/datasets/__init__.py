"""Deterministic evaluation datasets.

The scenario is the synthetic financial world seeded before evaluation; the
question dataset describes the cases asked against it and the expected
structured results. Numbers in the dataset are cross-checked against totals
computed directly from the scenario specification, so dataset values are
never hand-copied guesses.
"""
from app.evaluation.datasets.finance_scenario import (
    AS_OF,
    EVALUATION_SCENARIO,
    ISOLATION_CANARY,
    FinanceScenario,
    ScheduledEntry,
    ScenarioTransaction,
    scenario_scheduled_expenses,
    scenario_totals,
    seed_scenario,
)
from app.evaluation.datasets.finance_questions import EVALUATION_CASES
from app.evaluation.datasets.categorization_cases import (
    CATEGORIZATION_EVALUATION_CASES,
)

__all__ = [
    "AS_OF",
    "EVALUATION_SCENARIO",
    "ISOLATION_CANARY",
    "FinanceScenario",
    "ScheduledEntry",
    "ScenarioTransaction",
    "scenario_scheduled_expenses",
    "scenario_totals",
    "seed_scenario",
    "EVALUATION_CASES",
    "CATEGORIZATION_EVALUATION_CASES",
]
