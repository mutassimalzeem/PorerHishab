"""Authenticated financial review; no execution or persistence endpoint."""
from datetime import date
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.financial_review import FinancialReview
from app.services.finance.financial_review import financial_review

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/review", response_model=FinancialReview,
            responses={401: {"description": "Bearer authentication required"},
                       500: {"description": "Financial review unavailable"}})
def get_financial_review(
    as_of: date | None = Query(None, ge=date(1900, 1, 1), le=date(9998, 12, 31)),
    schedules_confirmed: bool = Query(False, description="User confirms recorded schedules are complete; does not authorize execution."),
    current: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Review the existing fixed 30-day coaching horizon. Never executes actions."""
    try:
        return financial_review(db, current.id, as_of=as_of,
                                schedules_confirmed=schedules_confirmed)
    except Exception:
        logger.exception("Financial review composition failed")
        raise HTTPException(500, "Financial review is temporarily unavailable") from None
