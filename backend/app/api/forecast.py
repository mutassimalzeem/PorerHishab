from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.forecast import BudgetForecast
from app.services.forecasting import get_user_budget_forecast


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