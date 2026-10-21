from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.planner import (
    SavingsPlanRequest,
    SavingsPlanResponse,
)
from app.services.planning import get_user_savings_plan


router = APIRouter(prefix="/planner", tags=["planner"],
)


@router.post("/savings", response_model=SavingsPlanResponse)
def savings_plan(payload: SavingsPlanRequest, current: User = Depends(get_current_user),
    db: Session = Depends(get_db)):
    
    return get_user_savings_plan(
        db=db,
        user_id=current.id,
        goal_amount=payload.goal_amount,
        current_saved=payload.current_saved,
        target_date=payload.target_date,
    )