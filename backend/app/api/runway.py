"""Authenticated read-only financial runway."""
from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.coach import Money
from app.schemas.runway import FinancialRunway, RunwayMode
from app.services.finance.runway import financial_runway

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/runway", response_model=FinancialRunway)
def get_runway(horizon_days: int = Query(30, ge=1, le=366), as_of: date | None = None,
               safety_threshold: Annotated[Money, Query()] = Decimal("0.00"),
               mode: RunwayMode = "historical", current: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return financial_runway(db, current.id, as_of=as_of, horizon_days=horizon_days,
                            safety_threshold=safety_threshold, mode=mode)
