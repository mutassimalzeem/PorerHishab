"""Financial Intelligence Engine (AI-13).

A reusable, deterministic layer that turns raw user financial records into
structured facts and signals for chat, recommendations, insights and a future
dashboard. No LLM, no network, no embeddings: arithmetic and facts stay in
plain Python/SQL.

Layers and what never mixes:

* :mod:`periods`     — central, timezone-safe period definitions;
* :mod:`coverage`    — first-class data-coverage statements;
* :mod:`facts`       — user-scoped SQL aggregates (single implementation);
* :mod:`snapshot`    — observed facts + plans + the baseline *estimate*;
* :mod:`cashflow`    — actual/scheduled/forecast separation via the engine;
* :mod:`categories`  — reusable category facts and comparisons;
* :mod:`goals`       — goal affordability assessment;
* :mod:`signals`     — deterministic signals with evidence and stable ids;
* :mod:`engine`      — one orchestration entry point.

The :class:`~app.services.finance.coach` presentation layer consumes these
primitives and owns wording/status codes only.
"""
from app.services.intelligence.periods import (
    Period,
    history_window_period,
    latest_complete_month_period,
    month_end,
    month_key,
    month_shift,
    month_start,
    previous_complete_month_period,
    today_dhaka,
)
from app.services.intelligence.coverage import (
    DataCoverage,
    assess_coverage,
)
from app.services.intelligence.facts import (
    LIMITATIONS,
    grouped_expenses,
    scheduled_cashflow_items,
    scheduled_totals,
    scoped,
    totals,
)
from app.services.intelligence.snapshot import (
    FinancialSnapshot,
    MonthlyHistory,
    ScheduledObligations,
    baseline_forecast,
    build_snapshot,
    monthly_history,
    scheduled_obligations,
)
from app.services.intelligence.categories import (
    CategorySpendingFact,
    category_spending_facts,
    percentage_change,
)
from app.services.intelligence.goals import (
    GoalAssessment,
    goal_assessment,
)
from app.services.intelligence.signals import (
    SIGNAL_GOAL_PROGRESS,
    SIGNAL_PROJECTED_SHORTFALL,
    SIGNAL_SAVINGS_OPPORTUNITY,
    SIGNAL_UNUSUAL_SPENDING,
    SIGNAL_UPCOMING_EXPENSE,
    FinancialSignal,
    build_signals,
)
from app.services.intelligence.engine import (
    CashflowIntelligence,
    FinancialIntelligence,
    build_cashflow_intelligence,
    build_financial_intelligence,
)

__all__ = [
    # periods
    "Period",
    "history_window_period",
    "latest_complete_month_period",
    "previous_complete_month_period",
    "month_end",
    "month_key",
    "month_shift",
    "month_start",
    "today_dhaka",
    # coverage
    "DataCoverage",
    "assess_coverage",
    # facts
    "LIMITATIONS",
    "grouped_expenses",
    "scheduled_cashflow_items",
    "scheduled_totals",
    "scoped",
    "totals",
    # snapshot
    "FinancialSnapshot",
    "MonthlyHistory",
    "ScheduledObligations",
    "baseline_forecast",
    "build_snapshot",
    "monthly_history",
    "scheduled_obligations",
    # categories
    "CategorySpendingFact",
    "category_spending_facts",
    "percentage_change",
    # goals
    "GoalAssessment",
    "goal_assessment",
    # signals
    "SIGNAL_GOAL_PROGRESS",
    "SIGNAL_PROJECTED_SHORTFALL",
    "SIGNAL_SAVINGS_OPPORTUNITY",
    "SIGNAL_UNUSUAL_SPENDING",
    "SIGNAL_UPCOMING_EXPENSE",
    "FinancialSignal",
    "build_signals",
    # engine
    "CashflowIntelligence",
    "FinancialIntelligence",
    "build_cashflow_intelligence",
    "build_financial_intelligence",
]
