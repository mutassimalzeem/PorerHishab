from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.forecast import BudgetForecast
from app.services.forecasting import get_user_budget_forecast


from decimal import Decimal

from fastapi import Query

from app.schemas.cashflow import CashflowForecast
from app.services.forecasting import get_user_cashflow_forecast



router = APIRouter(
    prefix="/forecast",
    tags=["forecast"],
)


@router.get(
    "/budget",
    response_model=BudgetForecast,
)
def budget_forecast(
    months_ahead: int = Query(
        1,
        ge=1,
        le=6,
    ),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_budget_forecast(
        db,
        current.id,
        months_ahead=months_ahead,
    )


@router.get("/cashflow", response_model=CashflowForecast)
def cashflow_forecast(
    starting_balance: Decimal = Query(
        ...,
        gt=0,
    ),
    months_ahead: int = Query(
        3,
        ge=1,
        le=12,
    ),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_cashflow_forecast(
        db=db,
        user_id=current.id,
        starting_balance=starting_balance,
        months_ahead=months_ahead,
    )