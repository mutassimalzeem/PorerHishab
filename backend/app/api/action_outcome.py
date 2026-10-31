"""Authenticated, read-only action outcome observations (AI-15I)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.action_outcome import ActionOutcomeReport, OutcomeStatus
from app.services.finance.action_outcome import action_outcomes

router = APIRouter(prefix="/finance", tags=["coach"])


@router.get("/action-outcomes", response_model=ActionOutcomeReport)
def get_action_outcomes(
    recommendation_id: str | None = None,
    status: OutcomeStatus | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return action_outcomes(
        db, current.id, recommendation_id=recommendation_id, status=status)
