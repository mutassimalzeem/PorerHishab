"""Authenticated, explicitly evaluated financial health profiles."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.financial_health import FinancialHealthProfile, FinancialHealthTrend
from app.services.finance import financial_health as health

router = APIRouter(prefix="/finance/health", tags=["finance"])

@router.get("", response_model=FinancialHealthProfile)
def current(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return health.current_profile(db, current.id)

@router.post("/evaluate", response_model=FinancialHealthProfile)
def evaluate(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return health.evaluate(db, current.id)

@router.get("/history", response_model=list[FinancialHealthProfile])
def history(from_date: date | None = None, to_date: date | None = None,
            limit: int = Query(90, ge=1, le=1000), current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must not exceed to_date")
    return health.history_profiles(db, current.id, from_date=from_date, to_date=to_date, limit=limit)

@router.get("/trend", response_model=FinancialHealthTrend)
def trend(days: int = Query(90, ge=7, le=366), current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return health.get_trend(db, current.id, days)
