"""Personalized plans extend the existing authenticated goal routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.goal_planning import GoalPlanRecord, GoalMilestone
from app.schemas.goal_planning import (PlanRequest, ContributionRequest, MilestoneUpdate, PersonalizedGoalPlan,
    GoalMilestoneRead, GoalPlanningOverview, ContributionResult, GoalEventRead)
from app.services.finance import goal_planning as service

router=APIRouter(prefix="/finance/goals",tags=["goal planning"])

def mutate(db,action):
    try:return action()
    except Exception:
        db.rollback()
        raise

@router.get("/planning/overview",response_model=GoalPlanningOverview)
def overview(schedules_confirmed: bool=False,current: User=Depends(get_current_user),db: Session=Depends(get_db)):
    return service.planning_overview(db,current.id,schedules_confirmed=schedules_confirmed)

@router.post("/{goal_id}/plan",response_model=PersonalizedGoalPlan)
def create(goal_id:int,payload:PlanRequest,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.create_plan(db,current.id,goal_id,payload))

@router.post("/{goal_id}/replan",response_model=PersonalizedGoalPlan)
def replan(goal_id:int,payload:PlanRequest,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.create_plan(db,current.id,goal_id,payload,replan=True))

@router.get("/{goal_id}/plans/current",response_model=PersonalizedGoalPlan)
def current_plan(goal_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.current_plan(db,current.id,goal_id)

@router.get("/{goal_id}/plans",response_model=list[PersonalizedGoalPlan])
def history(goal_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    service.owned_goal(db,current.id,goal_id)
    rows=db.query(GoalPlanRecord).filter_by(user_id=current.id,goal_id=goal_id).order_by(GoalPlanRecord.version.desc()).limit(100).all()
    return [PersonalizedGoalPlan.model_validate(r.profile) for r in reversed(rows)]

@router.get("/{goal_id}/milestones",response_model=list[GoalMilestoneRead])
def milestones(goal_id:int,plan_id:int|None=None,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    service.owned_goal(db,current.id,goal_id)
    if plan_id is None:
        plan=service.current_plan(db,current.id,goal_id);plan_id=plan.id
    elif db.query(GoalPlanRecord).filter_by(user_id=current.id,goal_id=goal_id,id=plan_id).one_or_none() is None:
        raise HTTPException(404,"Goal plan not found")
    return [service.milestone_read(r) for r in db.query(GoalMilestone).filter_by(user_id=current.id,goal_id=goal_id,plan_id=plan_id).order_by(GoalMilestone.sequence).all()]

@router.post("/{goal_id}/contributions",response_model=ContributionResult)
def contribute(goal_id:int,payload:ContributionRequest,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.record_contribution(db,current.id,goal_id,payload))

@router.patch("/{goal_id}/milestones/{milestone_id}",response_model=GoalMilestoneRead)
def milestone(goal_id:int,milestone_id:int,payload:MilestoneUpdate,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return mutate(db,lambda:service.update_milestone(db,current.id,goal_id,milestone_id,payload))

@router.get("/{goal_id}/events",response_model=list[GoalEventRead])
def events(goal_id:int,current:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return service.progress_events(db,current.id,goal_id)
