from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.planner import (
    SavingsPlanRequest,
    SavingsPlanResponse,
)
from app.services.planning import get_user_savings_plan
from app.schemas.savings_coach import SavingsCoachResponse
from app.services.ai.savings_coach import generate_savings_actions


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



@router.post("/savings/coach", response_model=SavingsCoachResponse)
def savings_coach(
    payload: SavingsPlanRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db)):
    """Return a deterministic savings plan plus grounded AI action guidance."""

    plan_data = get_user_savings_plan(
        db=db,
        user_id=current.id,
        goal_amount=payload.goal_amount,
        current_saved=payload.current_saved,
        target_date=payload.target_date,
    )

    plan = SavingsPlanResponse.model_validate(plan_data)

    try:
        actions = generate_savings_actions(plan)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="The optional savings coach is unavailable.") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="The savings coach is temporarily unavailable.",
        ) from exc

    return SavingsCoachResponse(plan=plan, actions=actions)
