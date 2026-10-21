"""Transaction intelligence service.

Public API lives in :mod:`app.services.analytics.insights`; this package
re-exports the entry points so callers can write
``from app.services.analytics import get_user_insights``.
"""

from app.services.analytics.insights import (
    compute_budget_baseline,
    compute_cashflow_timeline,
    compute_category_breakdown,
    compute_insights,
    compute_monthly_breakdown,
    compute_savings_rate,
    compute_summary,
    compute_top_merchants,
    detect_recurring_transactions,
    get_user_budget_baseline,
    get_user_cashflow,
    get_user_categories,
    get_user_insights,
    get_user_monthly,
    get_user_recurring,
    get_user_summary,
    get_user_top_merchants,
)

__all__ = [
    "compute_budget_baseline",
    "compute_cashflow_timeline",
    "compute_category_breakdown",
    "compute_insights",
    "compute_monthly_breakdown",
    "compute_savings_rate",
    "compute_summary",
    "compute_top_merchants",
    "detect_recurring_transactions",
    "get_user_budget_baseline",
    "get_user_cashflow",
    "get_user_categories",
    "get_user_insights",
    "get_user_monthly",
    "get_user_recurring",
    "get_user_summary",
    "get_user_top_merchants",
]
