"""Authenticated deterministic coaching presentation over shared facts."""
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.action_plan import CoachingActionPlan
from app.services.finance.action_plan import action_plan
from app.schemas.coach import Money
from app.schemas.coaching import CoachingPriority, FinancialCoaching
from app.services.finance.coaching_feedback import visible_coaching, submit, restore
from app.schemas.coaching import CoachingFeedbackInput, CoachingFeedbackRecord

router = APIRouter(prefix="/finance", tags=["coach"])


@router.get("/coaching", response_model=FinancialCoaching)
def get_coaching(priority: CoachingPriority | None = None,
                 safety_threshold: Annotated[Money, Query()] = Decimal("0.00"),
                 current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return visible_coaching(db, current.id, priority=priority, safety_threshold=safety_threshold)


@router.get("/coaching/feedback", response_model=list[CoachingFeedbackRecord])
def get_feedback(safety_threshold: Annotated[Money, Query()] = Decimal("0.00"),
                 current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return visible_coaching(db, current.id, safety_threshold=safety_threshold).feedback


@router.put("/coaching/{recommendation_id}/feedback", response_model=CoachingFeedbackRecord)
def put_feedback(recommendation_id: str, payload: CoachingFeedbackInput,
                 safety_threshold: Annotated[Money, Query()] = Decimal("0.00"),
                 current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return submit(db, current.id, recommendation_id, payload, safety_threshold=safety_threshold)


@router.delete("/coaching/{recommendation_id}/feedback", status_code=204)
def delete_feedback(recommendation_id: str, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    restore(db, current.id, recommendation_id)
    return Response(status_code=204)


@router.get("/action-plan", response_model=CoachingActionPlan)
def get_action_plan(priority: CoachingPriority | None = None,
                    safety_threshold: Annotated[Money, Query()] = Decimal("0.00"),
                    current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return action_plan(db, current.id, priority=priority, safety_threshold=safety_threshold)
