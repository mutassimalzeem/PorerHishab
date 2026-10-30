"""Authenticated financial event read model; no side effects."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.timeline import FinancialTimeline
from app.services.finance.timeline import financial_timeline

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/timeline", response_model=FinancialTimeline)
def get_timeline(start_date: date | None = None, end_date: date | None = None,
                 include_estimates: bool = True, current: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    try:
        return financial_timeline(db, current.id, start_date=start_date, end_date=end_date,
                                  include_estimates=include_estimates)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
