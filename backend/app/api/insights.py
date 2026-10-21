"""Transaction intelligence endpoints.

All metrics are computed by :mod:`app.services.analytics` over the
authenticated user's own transactions — a user can never see another user's
numbers because every query is user-scoped at the repository layer.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.insights import (
    BudgetBaselineInsight,
    CashflowPoint,
    CategoryBreakdown,
    InsightsOverview,
    MerchantInsight,
    MonthlyInsight,
    RecurringInsight,
    SummaryInsight,
)
from app.services.analytics import (
    get_user_budget_baseline,
    get_user_cashflow,
    get_user_categories,
    get_user_insights,
    get_user_monthly,
    get_user_recurring,
    get_user_summary,
    get_user_top_merchants,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/overview", response_model=InsightsOverview)
def insights_overview(
    start_date: date | None = None,
    end_date: date | None = None,
    top_merchants_limit: int = Query(5, ge=1, le=50),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every intelligence metric for the authenticated user in one payload."""
    return get_user_insights(
        db,
        current.id,
        start_date=start_date,
        end_date=end_date,
        top_merchants_limit=top_merchants_limit,
    )


@router.get("/summary", response_model=SummaryInsight)
def insights_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Income vs expenses, net position, and savings rate."""
    return get_user_summary(
        db, current.id, start_date=start_date, end_date=end_date
    )


@router.get("/monthly", response_model=list[MonthlyInsight])
def insights_monthly(
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Income / expenses / net grouped by month, oldest first."""
    return get_user_monthly(
        db, current.id, start_date=start_date, end_date=end_date
    )


@router.get("/categories", response_model=CategoryBreakdown)
def insights_categories(
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spending and income grouped by category."""
    return get_user_categories(
        db, current.id, start_date=start_date, end_date=end_date
    )


@router.get("/merchants", response_model=list[MerchantInsight])
def insights_top_merchants(
    limit: int = Query(5, ge=1, le=50),
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Merchants ranked by total spending."""
    return get_user_top_merchants(
        db,
        current.id,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/recurring", response_model=list[RecurringInsight])
def insights_recurring(
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detected recurring charges (subscriptions, bills, ...)."""
    return get_user_recurring(
        db, current.id, start_date=start_date, end_date=end_date
    )


@router.get("/cashflow", response_model=list[CashflowPoint])
def insights_cashflow(
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Day-by-day cash flow with a running balance, oldest day first."""
    return get_user_cashflow(
        db, current.id, start_date=start_date, end_date=end_date
    )


@router.get("/budget-baseline", response_model=BudgetBaselineInsight)
def insights_budget_baseline(
    start_date: date | None = None,
    end_date: date | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Average monthly spending, overall and per category."""
    return get_user_budget_baseline(
        db, current.id, start_date=start_date, end_date=end_date
    )
