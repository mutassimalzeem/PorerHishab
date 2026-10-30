"""Authenticated deterministic coaching presentation over shared facts."""
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.coach import Money
from app.schemas.coaching import CoachingPriority, FinancialCoaching
from app.services.finance.coaching import financial_coaching

router = APIRouter(prefix="/finance", tags=["coach"])


@router.get("/coaching", response_model=FinancialCoaching)
def get_coaching(priority: CoachingPriority | None = None,
                 safety_threshold: Annotated[Money, Query()] = Decimal("0.00"),
                 current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return financial_coaching(db, current.id, priority=priority, safety_threshold=safety_threshold)
