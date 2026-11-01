"""AI-15P: conservative, offline goal planning over existing authoritative facts."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from hashlib import sha256
import json
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import func, select
from app.models.savings_goal import SavingsGoal
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.financial_health import FinancialHealthSnapshot
from app.models.goal_planning import GoalPlanRecord, GoalMilestone, GoalProgressEvent
from app.models.user import User
from app.schemas.goal_planning import (PlanningCapacity, PersonalizedGoalPlan, PlanAlternative, GoalMilestoneRead,
    GoalPlanningOverview, GoalPlanningItem, ContributionResult)
from app.services.finance.account_position import get_account_overview
from app.services.finance.runway import financial_runway
from app.services.finance.obligations import obligation_amounts_for_items
from app.services.finance.financial_health import BALANCE_MAX_AGE_DAYS
from app.services.intelligence.snapshot import monthly_history
from app.services.intelligence.goals import required_monthly_contribution, goal_assessment
from app.services.intelligence.periods import today_dhaka, month_shift, month_end

D = Decimal
ZERO = D("0.00")
CENT = D("0.01")
INCOME_RELIABILITY_FACTOR = D("0.80")  # 20% haircut to the lowest observed month
MONTHLY_BUFFER_FACTOR = D("0.10")  # protect another 10% of conservative income
RESERVE_MONTHS = D("1")  # an additional full observed spending month
ADJUSTMENT_RATIO = D("1.10")  # <=10% contribution gap: modest adjustment
CHALLENGING_RATIO = D("1.50")  # <=50% gap: challenging, never a funded schedule
MAX_MONTHS = 120
MAX_WEEKLY_MILESTONES = 260
VERSION = "ai-15p-v1"
LIMITATIONS = [
    "Planning is an estimate from recorded BDT data, not a guarantee or a transfer.",
    "Reported savings and contributions are unverified; feasibility conservatively funds the full target.",
    "Reported goal savings are reserved against cash, never added as extra money.",
    "All recorded spending is protected; no essential spending is assumed discretionary.",
    "Income and expense changes are hypothetical; allocations cannot exceed recorded capacity.",
    "Debt goals track reported allocations, not lender-confirmed repayment or interest schedules.",
    "Expense-reduction goals track an earmarked savings target, not verified spending reductions.",
]
REASONS = {
    "history": "Three complete months with positive recorded income and expenses are required.",
    "cash": "Every BDT account needs a reconciled balance verified within thirty days.",
    "schedules": "Confirm that recorded expense schedules include known commitments before planning.",
    "earmarks": "Report existing goal savings explicitly, including zero when known, before allocating shared cash.",
    "reserve": "Emergency reserves, upcoming and overdue obligations, and existing goal earmarks protect cash before savings.",
}
EXPLANATIONS = {
    "feasible": "The required contribution fits the conservative capacity after existing commitments.",
    "feasible_with_adjustments": "A smaller contribution or later deadline is needed; review the recalculated alternatives.",
    "challenging": "The required contribution exceeds the allocated capacity materially; review the recalculated alternatives.",
    "not_currently_feasible": "The deadline or protected cash capacity does not support this goal currently.",
    "insufficient_data": "Required financial inputs or verified completion evidence are unavailable; no allocation is recommended.",
}


def floor(value): return value.quantize(CENT, rounding=ROUND_DOWN)

def owned_goal(db, user_id, goal_id):
    goal = db.query(SavingsGoal).filter_by(user_id=user_id, id=goal_id).one_or_none()
    if goal is None: raise HTTPException(404, "Savings goal not found")
    return goal

def lock_user(db, user_id):
    db.query(User).filter_by(id=user_id).with_for_update().one()

def latest_plans(db, user_id):
    ids=select(func.max(GoalPlanRecord.id)).where(GoalPlanRecord.user_id==user_id).group_by(GoalPlanRecord.goal_id)
    return {p.goal_id:p for p in db.query(GoalPlanRecord).filter(GoalPlanRecord.user_id==user_id,GoalPlanRecord.id.in_(ids)).all()}

@dataclass
class EvaluationContext:
    capacity: PlanningCapacity
    goals: list
    plans: dict


def build_context(db, user_id, *, schedules_confirmed=False, income_change_percent=ZERO, expense_change_percent=ZERO, as_of=None):
    as_of=as_of or today_dhaka()
    goals=db.query(SavingsGoal).filter(SavingsGoal.user_id==user_id).order_by(SavingsGoal.priority,SavingsGoal.created_at,SavingsGoal.id).all()
    plans=latest_plans(db,user_id)
    history=monthly_history(db,user_id,as_of,exclude_transfers=True)
    accounts=get_account_overview(db,user_id,as_of=as_of)
    runway=financial_runway(db,user_id,as_of=as_of,history=history,account_overview=accounts)
    overdue=db.query(ScheduledCashflowItem).filter(ScheduledCashflowItem.user_id==user_id,
        ScheduledCashflowItem.kind=="expense",ScheduledCashflowItem.status=="scheduled",ScheduledCashflowItem.due_date<as_of).all()
    amounts=obligation_amounts_for_items(db,user_id,overdue)
    overdue_total=sum((v.reserved_amount for v in amounts.values()),ZERO)
    health=db.query(FinancialHealthSnapshot).filter_by(user_id=user_id).order_by(FinancialHealthSnapshot.snapshot_date.desc(),FinancialHealthSnapshot.id.desc()).first()
    bdt=[a for a in accounts.items if a.currency=="BDT"]
    def recent(a):
        stamp=a.balance_as_of
        if stamp is None:return False
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        return 0 <= (as_of-stamp.astimezone(ZoneInfo("Asia/Dhaka")).date()).days <= BALANCE_MAX_AGE_DAYS
    trusted=accounts.trusted_bdt_position.total if bdt and all(a.position_status=="trusted" and recent(a) for a in bdt) else None
    relevant=[g for g in goals if g.status!="cancelled"]
    earmarks=sum((g.current_saved for g in relevant),ZERO) if all(g.current_saved is not None for g in relevant) else None
    adequate=history.adequate and all(r["income"] is not None and r["income"]>ZERO and r["expenses"] is not None and r["expenses"]>ZERO for r in history.monthly)
    missing=[]
    if not adequate:missing.append(REASONS["history"])
    if trusted is None:missing.append(REASONS["cash"])
    if not schedules_confirmed:missing.append(REASONS["schedules"])
    if earmarks is None:missing.append(REASONS["earmarks"])
    income=expense=reserve=capacity=scenario=None
    if not missing and runway.expected_expense_reserve is not None:
        income=floor(min(r["income"] for r in history.monthly)*INCOME_RELIABILITY_FACTOR)
        expense=max(r["expenses"] for r in history.monthly)
        def calculate(income_delta,expense_delta):
            observed_income=floor(income*(D("1")+income_delta/100))
            observed_expense=floor(expense*(D("1")+expense_delta/100))
            near_term=max(runway.scheduled_expense_reserve, floor(runway.expected_expense_reserve*(D("1")+expense_delta/100)))
            protected=near_term+observed_expense*RESERVE_MONTHS+overdue_total+earmarks
            free_cash=max(ZERO,trusted-protected)
            monthly=max(ZERO,observed_income-max(observed_expense,near_term)-observed_income*MONTHLY_BUFFER_FACTOR)
            return floor(min(free_cash,monthly)),floor(protected)
        capacity,reserve=calculate(ZERO,ZERO)
        scenario,_=calculate(income_change_percent,expense_change_percent)
        capacity=min(capacity,scenario)
    else:
        if not missing:missing.append(REASONS["history"])
    result=PlanningCapacity(as_of_date=as_of,observation_start=history.period.start,observation_end=history.period.end,
        status="insufficient_data" if missing else "sufficient",conservative_monthly_capacity=capacity,
        scenario_monthly_capacity=scenario,trusted_cash=trusted,protected_reserve=reserve,
        upcoming_obligations=runway.scheduled_expense_reserve,overdue_obligations=overdue_total,reported_earmarks=earmarks,
        conservative_income=income,protected_expenses=expense,
        health_coverage=health.coverage_percent if health else None,health_as_of_date=health.snapshot_date if health else None,
        explanations=missing or [REASONS["reserve"]],limitations=list(LIMITATIONS)+(["Financial-health context is unavailable; it does not determine goal feasibility."] if health is None else health.profile.get("limitations",[])))
    return EvaluationContext(result,goals,plans)


def classify(required,available,*,has_data=True,overdue=False):
    if not has_data:return "insufficient_data"
    if overdue or available<=ZERO:return "not_currently_feasible"
    if required is None:return "feasible_with_adjustments"
    if required<=available:return "feasible"
    if required<=available*ADJUSTMENT_RATIO:return "feasible_with_adjustments"
    if required<=available*CHALLENGING_RATIO:return "challenging"
    return "not_currently_feasible"


def allocations(context,focus_goal=None):
    pool=context.capacity.conservative_monthly_capacity or ZERO
    result={}
    # Accepted commitments stay reserved; evaluating another goal never diverts them.
    ordered=sorted((g for g in context.goals if g.status=="active"),key=lambda g:(g.id not in context.plans or g.id==focus_goal,g.priority,g.id))
    for goal in ordered:
        plan=context.plans.get(goal.id)
        demand=D(plan.profile["proposed_monthly"]) if plan and goal.id!=focus_goal else required_monthly_contribution(goal.target_amount,goal.target_date,context.capacity.as_of_date)
        value=min(pool,demand if demand is not None else pool)
        result[goal.id]=floor(value);pool-=value
    return result


def assess_goal(goal,context,*,inputs=None):
    inputs=inputs or {}
    as_of=context.capacity.as_of_date
    required=required_monthly_contribution(goal.target_amount,goal.target_date,as_of)
    available=allocations(context,goal.id).get(goal.id,ZERO)
    has_data=context.capacity.status=="sufficient" and goal.status=="active"
    status=classify(required,available,has_data=has_data,overdue=goal.target_date is not None and goal.target_date<as_of)
    proposal=min(available,required) if required is not None else available
    if not has_data:proposal=ZERO
    reported=goal_assessment(None,goal.user_id,goal,as_of,None).remaining
    result=PersonalizedGoalPlan(goal_id=goal.id,as_of_date=as_of,target_amount=goal.target_amount,target_date=goal.target_date,
        reported_progress=goal.current_saved,remaining_amount=goal.target_amount,reported_remaining_amount=reported,
        required_monthly=required,proposed_monthly=proposal,feasibility=status,explanation=EXPLANATIONS[status],
        capacity=context.capacity,inputs=inputs,limitations=list(LIMITATIONS))
    if proposal>ZERO and status!="feasible":
        # Every alternative goes back through the identical classifier and denominator.
        months=int((goal.target_amount/proposal).to_integral_value(rounding=ROUND_UP))
        if months<=MAX_MONTHS:
            end=month_end(month_shift(as_of,months-1))
            amount=required_monthly_contribution(goal.target_amount,end,as_of)
            result.alternatives.append(PlanAlternative(key="extend_deadline",target_amount=goal.target_amount,target_date=end,
                required_monthly=amount,proposed_monthly=min(proposal,amount),feasibility=classify(amount,proposal),explanation=EXPLANATIONS["feasible"]))
        if goal.target_date is not None and goal.target_date>=as_of:
            months=max(1,(goal.target_date.year-as_of.year)*12+goal.target_date.month-as_of.month+1)
            target=floor(proposal*months)
            if target>ZERO and target<goal.target_amount and (goal.current_saved is None or target>=goal.current_saved):
                amount=required_monthly_contribution(target,goal.target_date,as_of)
                result.alternatives.append(PlanAlternative(key="reduce_target",target_amount=target,target_date=goal.target_date,
                    required_monthly=amount,proposed_monthly=min(proposal,amount),feasibility=classify(amount,proposal),explanation=EXPLANATIONS["feasible"]))
    return result


def milestone_schedule(target,as_of,deadline,cadence):
    if deadline is None or deadline<as_of:return []
    months=max(1,(deadline.year-as_of.year)*12+deadline.month-as_of.month+1)
    if months>MAX_MONTHS:raise HTTPException(422,"Plans support at most 120 calendar months")
    dates=[min(deadline,month_end(month_shift(as_of,i))) for i in range(months)]
    def distribute(cents,points):
        count=min(len(points),cents)
        if count==0:return []
        q,r=divmod(cents,count)
        return [(points[((i+1)*len(points)+count-1)//count-1],q+(i<r)) for i in range(count)]
    monthly=distribute(int(target/CENT),dates)
    installments=[]
    for due,cents in monthly:
        if cadence=="monthly":installments.append((due,cents));continue
        start=max(as_of,due.replace(day=1));points=[]
        while start+timedelta(days=7)<due:
            start+=timedelta(days=7);points.append(start)
        points.append(due)
        installments.extend(distribute(cents,points))
    if cadence=="weekly" and len(installments)>MAX_WEEKLY_MILESTONES:
        raise HTTPException(422,"Weekly plans support at most 260 milestones")
    cumulative=ZERO;result=[]
    for due,cents in installments:
        amount=D(cents)*CENT;cumulative+=amount
        result.append(dict(sequence=len(result)+1,due_date=due,target_cumulative=cumulative,expected_contribution=amount))
    return result


def event(db,user_id,goal_id,kind,payload,*,key=None):
    row=GoalProgressEvent(user_id=user_id,goal_id=goal_id,kind=kind,payload=payload,idempotency_key=key or uuid4().hex)
    db.add(row);db.flush();return row


def replay(db,user_id,goal_id,key,kind,request):
    row=db.query(GoalProgressEvent).filter_by(user_id=user_id,idempotency_key="request-"+key).one_or_none()
    if row is None:return None
    if row.goal_id!=goal_id or row.kind!=kind or row.payload.get("request")!=request:
        raise HTTPException(409,"Idempotency key already belongs to a different request")
    return row.payload["response"]


def milestone_read(row,as_of=None):
    result=GoalMilestoneRead.model_validate(row)
    if result.status=="pending" and result.due_date<(as_of or today_dhaka()):result.status="missed"
    return result


def sync_milestones(db,user_id,goal,*,as_of=None):
    as_of=as_of or today_dhaka()
    rows=db.query(GoalMilestone).filter_by(user_id=user_id,goal_id=goal.id).all()
    for row in rows:
        # Existing completion reports are historical facts and never undone by target edits.
        if row.status=="reported_completed":continue
        if goal.current_saved is not None and goal.current_saved>=row.target_cumulative:
            row.status="reported_completed";row.completed_at=datetime.now(timezone.utc)
            event(db,user_id,goal.id,"milestone_achieved",{"milestone_id":row.id,"plan_id":row.plan_id,"source":"user_reported"},key=f"milestone-{row.id}-achieved")
        elif row.status=="pending" and row.due_date<as_of:
            row.status="missed"
            event(db,user_id,goal.id,"milestone_missed",{"milestone_id":row.id,"plan_id":row.plan_id},key=f"milestone-{row.id}-missed")


def current_plan(db,user_id,goal_id):
    owned_goal(db,user_id,goal_id)
    row=db.query(GoalPlanRecord).filter_by(user_id=user_id,goal_id=goal_id).order_by(GoalPlanRecord.version.desc()).first()
    if row is None:raise HTTPException(404,"No personalized plan yet")
    result=PersonalizedGoalPlan.model_validate(row.profile)
    result.milestones=[milestone_read(m) for m in db.query(GoalMilestone).filter_by(user_id=user_id,goal_id=goal_id,plan_id=row.id).order_by(GoalMilestone.sequence).all()]
    return result


def create_plan(db,user_id,goal_id,payload,*,replan=False,as_of=None):
    lock_user(db,user_id);goal=owned_goal(db,user_id,goal_id)
    request={**payload.model_dump(mode="json"), "target_date_supplied": replan and "target_date" in payload.model_fields_set};kind="plan_revised" if replan else "plan_created"
    previous=replay(db,user_id,goal_id,payload.idempotency_key,kind,request)
    if previous is not None:return PersonalizedGoalPlan.model_validate(previous)
    as_of=as_of or today_dhaka()
    if goal.status=="cancelled" or replan and goal.status=="completed":raise HTTPException(409,"Completed or cancelled goals cannot be replanned")
    changes={}
    if payload.target_amount is not None:changes["target_amount"]=payload.target_amount
    if "target_date" in payload.model_fields_set and (replan or payload.target_date is not None):changes["target_date"]=payload.target_date
    if changes and not replan:raise HTTPException(422,"Accept target changes through replan")
    if payload.target_date is not None and payload.target_date<as_of:raise HTTPException(422,"Target date cannot be in the past")
    if payload.target_amount is not None and goal.current_saved is not None and payload.target_amount<goal.current_saved:
        raise HTTPException(422,"Revised target cannot be less than reported progress")
    before={k:str(getattr(goal,k)) if getattr(goal,k) is not None else None for k in changes}
    for k,v in changes.items():setattr(goal,k,v)
    db.flush()
    context=build_context(db,user_id,schedules_confirmed=payload.schedules_confirmed,income_change_percent=payload.income_change_percent,expense_change_percent=payload.expense_change_percent,as_of=as_of)
    result=assess_goal(goal,context,inputs={k:v for k,v in request.items() if k!="idempotency_key"})
    signature=result.model_dump(mode="json",exclude={"id","version","milestones"})
    fingerprint=sha256(json.dumps(signature,sort_keys=True).encode()).hexdigest()
    latest=context.plans.get(goal_id)
    if latest and latest.fingerprint==fingerprint:
        result=current_plan(db,user_id,goal_id)
    else:
        row=GoalPlanRecord(user_id=user_id,goal_id=goal_id,version=latest.version+1 if latest else 1,fingerprint=fingerprint,profile={})
        db.add(row);db.flush();result.id=row.id;result.version=row.version
        if result.feasibility=="feasible":
            for item in milestone_schedule(goal.target_amount,as_of,goal.target_date,payload.cadence):
                db.add(GoalMilestone(user_id=user_id,goal_id=goal_id,plan_id=row.id,**item))
            db.flush();sync_milestones(db,user_id,goal,as_of=as_of)
            result.milestones=[milestone_read(m,as_of) for m in db.query(GoalMilestone).filter_by(user_id=user_id,goal_id=goal_id,plan_id=row.id).order_by(GoalMilestone.sequence).all()]
        row.profile=result.model_dump(mode="json")
    event(db,user_id,goal_id,kind,{"request":request,"response":result.model_dump(mode="json"),"previous_target":before},key="request-"+payload.idempotency_key)
    db.commit();return result


def record_contribution(db,user_id,goal_id,payload):
    lock_user(db,user_id);goal=owned_goal(db,user_id,goal_id)
    request=payload.model_dump(mode="json")
    previous=replay(db,user_id,goal_id,payload.idempotency_key,"contribution_recorded",request)
    if previous is not None:return ContributionResult.model_validate(previous)
    if goal.status!="active":raise HTTPException(409,"Contributions require an active goal")
    if goal.current_saved is None:raise HTTPException(409,"Report the starting savings amount explicitly before recording contributions")
    total=goal.current_saved+payload.amount
    if total>goal.target_amount:raise HTTPException(409,"Contribution would exceed the reported goal target")
    goal.current_saved=total
    if total==goal.target_amount:goal.status="completed"
    row=event(db,user_id,goal_id,"contribution_recorded",{})
    result=ContributionResult(event_id=row.id,goal_id=goal_id,reported_total=total,goal_status=goal.status)
    row.idempotency_key="request-"+payload.idempotency_key;row.payload={"request":request,"response":result.model_dump(mode="json"),"amount":str(payload.amount),"source":"user_reported"}
    sync_milestones(db,user_id,goal)
    if goal.status=="completed":event(db,user_id,goal_id,"goal_completed",{"source":"user_reported","reported_total":str(total)})
    db.commit();return result


def update_milestone(db,user_id,goal_id,milestone_id,payload):
    lock_user(db,user_id);goal=owned_goal(db,user_id,goal_id)
    request={**payload.model_dump(mode="json"),"milestone_id":milestone_id}
    previous=replay(db,user_id,goal_id,payload.idempotency_key,"milestone_updated",request)
    if previous is not None:return GoalMilestoneRead.model_validate(previous)
    row=db.query(GoalMilestone).filter_by(user_id=user_id,goal_id=goal_id,id=milestone_id).one_or_none()
    if row is None:raise HTTPException(404,"Goal milestone not found")
    if payload.status=="reported_completed" and (goal.current_saved is None or goal.current_saved<row.target_cumulative):raise HTTPException(409,"Record sufficient reported contributions before completing a milestone")
    if payload.status=="missed" and (row.due_date>=today_dhaka() or row.status=="reported_completed"):raise HTTPException(409,"Only past uncompleted milestones may be marked missed")
    sync_milestones(db,user_id,goal)
    result=milestone_read(row)
    event(db,user_id,goal_id,"milestone_updated",{"request":request,"response":result.model_dump(mode="json")},key="request-"+payload.idempotency_key)
    db.commit();return result


def progress_events(db,user_id,goal_id):
    owned_goal(db,user_id,goal_id)
    rows=db.query(GoalProgressEvent).filter_by(user_id=user_id,goal_id=goal_id).order_by(GoalProgressEvent.id.desc()).limit(200).all()
    return [dict(id=r.id,goal_id=r.goal_id,kind=r.kind,created_at=r.created_at,details={k:v for k,v in r.payload.items() if k not in {"request","response"}}) for r in rows]


def planning_overview(db,user_id,*,schedules_confirmed=False,as_of=None):
    context=build_context(db,user_id,schedules_confirmed=schedules_confirmed,as_of=as_of)
    shares=allocations(context);items=[];accepted=ZERO
    for goal in context.goals:
        if goal.status!="active":continue
        proposal=shares.get(goal.id,ZERO)
        required=required_monthly_contribution(goal.target_amount,goal.target_date,context.capacity.as_of_date)
        state=classify(required,proposal,has_data=context.capacity.status=="sufficient",overdue=goal.target_date is not None and goal.target_date<context.capacity.as_of_date)
        stored=context.plans.get(goal.id);commitment=D(stored.profile["proposed_monthly"]) if stored else ZERO;accepted+=commitment
        items.append(GoalPlanningItem(goal_id=goal.id,name=goal.name,priority=goal.priority,goal_status=goal.status,target_amount=goal.target_amount,remaining_amount=goal.target_amount,proposed_monthly=proposal,accepted_monthly=commitment,feasibility=state,explanation=EXPLANATIONS[state]))
    plan_ids=[context.plans[g.goal_id].id for g in items if g.goal_id in context.plans]
    milestones=[milestone_read(m,context.capacity.as_of_date) for m in db.query(GoalMilestone).filter(GoalMilestone.user_id==user_id,GoalMilestone.plan_id.in_(plan_ids)).order_by(GoalMilestone.due_date,GoalMilestone.id).all()] if plan_ids else []
    capacity=context.capacity.conservative_monthly_capacity
    return GoalPlanningOverview(capacity=context.capacity,goals=items,total_target_amount=sum((g.target_amount for g in items),ZERO),total_remaining_amount=sum((g.remaining_amount for g in items),ZERO),
        total_planned_monthly=accepted,total_proposed_monthly=sum((g.proposed_monthly for g in items),ZERO),capacity_utilization=floor(accepted/capacity*100) if capacity is not None and capacity>ZERO else None,
        over_capacity=capacity is not None and accepted>capacity,upcoming_milestones=[m for m in milestones if m.status=="pending"][:20],missed_milestones=[m for m in milestones if m.status=="missed"][:20])
