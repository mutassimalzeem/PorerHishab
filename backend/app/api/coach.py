"""Authenticated deterministic coach and user-reported savings goals."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.savings_goal import SavingsGoal
from app.models.transactions import Transaction
from app.schemas.coach import (
    GoalCreate, GoalUpdate, GoalRead, GoalPage, GoalPlan, GoalStatus,
    RecommendationPage, NudgePage, CoachCashflowRequest, CoachCashflowResponse,
    CoachPurchaseRequest, CoachPurchaseResponse, CategorizeBatchRequest, CategorizeBatchResponse,
)
from app.services.finance.coach import today_dhaka, recommendations, nudges, goal_plan, coach_cashflow, coach_purchase
from app.services.categorization.service import categorize_transaction

router = APIRouter(tags=["coach"])


def owned_goal(db, user_id, goal_id, lock=False):
    query = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id)
    goal = (query.with_for_update() if lock else query).first()
    if goal is None:
        raise HTTPException(404, "Savings goal not found")
    return goal


@router.post("/finance/goals", response_model=GoalRead, status_code=201)
def create_goal(payload: GoalCreate, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.target_date < today_dhaka():
        raise HTTPException(422, "target_date cannot be in the past")
    goal = SavingsGoal(user_id=current.id, **payload.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.get("/finance/goals", response_model=GoalPage)
def list_goals(status: GoalStatus | None = None, limit: int = Query(50, ge=1, le=100),
               offset: int = Query(0, ge=0), current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(SavingsGoal).filter(SavingsGoal.user_id == current.id)
    if status is not None:
        query = query.filter(SavingsGoal.status == status)
    total = query.count()
    return {"items": query.order_by(SavingsGoal.target_date, SavingsGoal.id).offset(offset).limit(limit).all(),
            "total": total, "limit": limit, "offset": offset}


@router.get("/finance/goals/{goal_id}", response_model=GoalRead)
def read_goal(goal_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return owned_goal(db, current.id, goal_id)


@router.patch("/finance/goals/{goal_id}", response_model=GoalRead)
def patch_goal(goal_id: int, payload: GoalUpdate, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goal = owned_goal(db, current.id, goal_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    if goal.status != "active" and changes.get("status", goal.status) != goal.status:
        raise HTTPException(409, "Completed or cancelled goals cannot change status")
    if "target_date" in changes and changes["target_date"] < today_dhaka():
        raise HTTPException(422, "target_date cannot be in the past")
    saved = changes.get("current_saved", goal.current_saved)
    target = changes.get("target_amount", goal.target_amount)
    status = changes.get("status", goal.status)
    if status == "completed" and (saved is None or saved < target):
        raise HTTPException(409, "Completion requires reported savings at least equal to the target")
    for name, value in changes.items():
        setattr(goal, name, value)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/finance/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned_goal(db, current.id, goal_id))
    db.commit()
    return Response(status_code=204)


@router.get("/finance/goals/{goal_id}/plan", response_model=GoalPlan)
def plan_goal(goal_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return goal_plan(db, current.id, owned_goal(db, current.id, goal_id))


@router.get("/finance/savings/recommendations", response_model=RecommendationPage)
def savings_recommendations(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return recommendations(db, current.id)


@router.get("/insights/proactive", response_model=NudgePage)
def proactive_insights(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return nudges(db, current.id)


@router.post("/finance/coach/cashflow", response_model=CoachCashflowResponse)
def cashflow_scenario(payload: CoachCashflowRequest, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return coach_cashflow(db, current.id, payload)


@router.post("/finance/coach/spending-decision", response_model=CoachPurchaseResponse)
def obligation_decision(payload: CoachPurchaseRequest, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return coach_purchase(db, current.id, payload)


@router.post("/transactions/categorize", response_model=CategorizeBatchResponse)
def categorize_batch(payload: CategorizeBatchRequest, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # All IDs are checked before writing or calling a provider. Missing and foreign IDs look identical.
    rows = db.query(Transaction).filter(Transaction.user_id == current.id, Transaction.id.in_(payload.transaction_ids)).order_by(Transaction.id).with_for_update().all()
    if len(rows) != len(payload.transaction_ids):
        raise HTTPException(404, "One or more transactions were not found")
    items = []
    llm_budget = 5
    for row in rows:
        # A non-placeholder existing category may have been supplied by a user/importer.
        preserved = bool(row.category and row.category not in {"Other", "Uncategorized"}) or row.category_method in {"user", "manual", "user_preference"}
        if not preserved:
            result = categorize_transaction(row, db=db, user_id=current.id, allow_llm=llm_budget > 0)
            if result.method in {"llm", "fallback"}:
                llm_budget -= 1
            row.category = result.category
            row.category_confidence = result.confidence
            row.category_method = result.method
            row.category_reason = result.reason
        items.append({"transaction_id": row.id, "category": row.category, "method": row.category_method,
                      "confidence": row.category_confidence, "reason": row.category_reason, "preserved": preserved})
    db.commit()
    return {"items": items}
