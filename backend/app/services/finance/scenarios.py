"""AI-15Q orchestration. Real ORM financial entities are never assigned to or flushed.

Frozen run evidence records authoritative inputs; comparisons are typed SQL rows.
No provider is involved in interpreting or calculating scenario results.
"""
from calendar import monthrange
from copy import deepcopy
from datetime import timedelta, datetime, timezone
from decimal import Decimal as D, ROUND_HALF_UP
from hashlib import sha256
import json
from types import SimpleNamespace
from fastapi import HTTPException
from app.models.scenarios import Scenario, ScenarioChangeRecord, ScenarioRun, ScenarioComparison
from app.schemas.scenarios import ScenarioRead, ScenarioChange, ScenarioResult, MetricComparison
from app.services.finance import goal_planning as planning
from app.services.finance.account_position import get_account_overview
from app.services.finance.runway import financial_runway
from app.services.intelligence.snapshot import monthly_history
from app.services.intelligence.periods import today_dhaka
from app.repositories import scenarios as repository

VERSION="ai-15q-v1"
ZERO=D("0.00")
LIMITATIONS=[
    "Under the assumptions used in this scenario, values are hypothetical BDT estimates, not guaranteed outcomes or financial advice.",
    "Monthly income and expenses use AI-13 observed averages; goal capacity uses the stricter AI-15P policy.",
    "Monthly comparisons describe the horizon-end run rate. Recurring adjustments are prorated by active calendar days in runway segments.",
    "Runway uses AI-15D monthly segments and expenses-before-income minima; an exact depletion date or runway month count is unavailable.",
    "Scheduled obligations retain the authoritative overlap rule: reserve the greater of historical expenses and scheduled expense reserves.",
    "Future windfalls affect projected cash only; they never fund current goal capacity. One-time expenses protect cash before allocations.",
    "Savings adjustments are signed monthly allocation changes. Increases earmark additional capacity; decreases release accepted commitments, lowest priority first. Reductions beyond accepted commitments are rejected.",
    "Goal changes take effect from their selected date; horizon-end goal comparisons do not model phased contribution schedules.",
    "Financial health cannot safely evaluate hypothetical inputs and is not available for scenarios.",
]

def owned(db,uid,sid):
    row=repository.owned(db,uid,sid)
    if row is None: raise HTTPException(404,"Scenario not found")
    return row

def changes_for(db,row):
    return [ScenarioChange.model_validate(c) for c in repository.changes(db,row.user_id,[row.id])]

_UNSET=object()
def read(db,row,*,latest=_UNSET,changes=None):
    if latest is _UNSET:latest=repository.latest_runs(db,row.user_id,[row.id]).get(row.id)
    extra={"latest_run_id":latest.id if latest else None,"latest_run_at":latest.created_at if latest else None,
        "result_revision":latest.request.get("revision") if latest else None,
        "result_calculation_version":latest.calculation_version if latest else None,
        "result_state":"missing" if latest is None else "current" if latest.request.get("revision")==row.revision and latest.calculation_version==row.calculation_version else "stale"}
    fields={k:getattr(row,k) for k in ScenarioRead.model_fields if k not in {"changes",*extra}}
    return ScenarioRead.model_validate({**fields,**extra,"changes":changes if changes is not None else changes_for(db,row)})


def editable(row):
    if row.status=="archived": raise HTTPException(409,"Archived scenarios are read-only")

def create(db,uid,payload):
    planning.lock_user(db,uid)
    row=Scenario(user_id=uid,**payload.model_dump());db.add(row);db.commit();return read(db,row)

def replace_changes(db,uid,sid,payload):
    planning.lock_user(db,uid);row=owned(db,uid,sid);editable(row)
    if any(c.change_type=="savings_contribution_adjustment" and c.amount<ZERO for c in payload.changes) and any(c.change_type=="goal_commitment_adjustment" for c in payload.changes):
        raise HTTPException(422,"Choose either a total savings reduction or individual commitment replacements")
    seen=set()
    for change in payload.changes:
        if change.target_id is not None:
            goal=planning.owned_goal(db,uid,change.target_id)
            if goal.status!="active": raise HTTPException(422,"Goal changes require an active goal")
            key=(change.change_type,change.target_id)
            if key in seen: raise HTTPException(422,"Conflicting goal replacements; keep one change per field and goal")
            seen.add(key)
        if change.target_date and change.target_date<change.effective_date: raise HTTPException(422,"Goal deadline precedes its effective date")
    db.query(ScenarioChangeRecord).filter_by(scenario_id=row.id).delete()
    for change in payload.changes: db.add(ScenarioChangeRecord(scenario_id=row.id,**change.model_dump()))
    row.revision+=1;row.status="draft";row.updated_at=datetime.now(timezone.utc);db.commit();return read(db,row)

def set_status(db,uid,sid,status):
    planning.lock_user(db,uid);row=owned(db,uid,sid)
    if row.status==status:return read(db,row)
    editable(row)
    now=datetime.now(timezone.utc);row.status=status;row.updated_at=now
    if status=="saved":row.saved_at=now
    if status=="archived":row.archived_at=now
    db.commit();return read(db,row)


def compare(metric,before,after,reason=None,*,unavailable=False,percentage=True):
    status="not_available_for_scenario" if unavailable else "insufficient_data" if before is None or after is None else "available"
    delta=planning.floor(after-before) if status=="available" else None
    pct=(delta/before*100).quantize(D("0.01"),rounding=ROUND_HALF_UP) if delta is not None and before>ZERO and percentage else None
    pct_status="available" if pct is not None else "insufficient_data" if delta is None else "zero_baseline" if before==ZERO else "not_meaningful"
    return MetricComparison(metric=metric,baseline_value=before,scenario_value=after,absolute_delta=delta,percentage_delta=pct,percentage_status=pct_status,
        direction="unknown" if delta is None else "increased" if delta>0 else "decreased" if delta<0 else "unchanged",status=status,reason=reason if status!="available" else None)

def active(change,day):
    return change.effective_date<=day and (change.end_date is None or day<=change.end_date)

def adjustments(changes,start,stop):
    income=expense=once_income=once_expense=ZERO
    for c in changes:
        if c.frequency=="monthly":
            days=max(0,(min(stop,c.end_date or stop)-max(start,c.effective_date)).days+1)
            value=c.amount*D(days)/D(monthrange(start.year,start.month)[1])
            if c.change_type=="income_adjustment":income+=value
            if c.change_type=="recurring_expense_adjustment":expense+=value
        elif start<=c.effective_date<=stop:
            if c.change_type=="one_time_income":once_income+=c.amount
            if c.change_type=="one_time_expense":once_expense+=c.amount
    return income,expense,once_income,once_expense

def goal_facts(context):
    result=[]
    for goal in context.goals:
        if goal.status!="active":continue
        plan=planning.assess_goal(goal,context)
        accepted=context.plans.get(goal.id)
        result.append(dict(goal_id=goal.id,name=goal.name,target_amount=str(goal.target_amount),target_date=goal.target_date.isoformat() if goal.target_date else None,
            required_contribution=str(plan.required_monthly) if plan.required_monthly is not None else None,
            projected_contribution_capacity=str(plan.proposed_monthly) if context.capacity.status=="sufficient" else None,
            accepted_commitment=str(accepted.profile["proposed_monthly"]) if accepted else "0.00",
            feasibility=plan.feasibility,goal_risk=plan.feasibility,reason=plan.explanation))
    return result

def calculate(db,uid,sid,changes,request,*,as_of=None):
    as_of=as_of or today_dhaka();end=as_of+timedelta(days=request.horizon_days)
    for c in changes:
        if not as_of<=c.effective_date<=end: raise HTTPException(422,"Change effective date must be within this run's horizon")
        if c.target_id is not None: planning.owned_goal(db,uid,c.target_id)
    history=monthly_history(db,uid,as_of,exclude_transfers=True)
    accounts=get_account_overview(db,uid,as_of=as_of)
    context=planning.build_context(db,uid,schedules_confirmed=request.schedules_confirmed,as_of=as_of)
    assumptions=changes
    # Percent intent remains explicit; Python alone resolves the monetary delta.
    changes=[c.model_copy(update={"amount":planning.floor(history.baseline["average_monthly_income"]*c.percentage/100) if history.adequate and history.baseline.get("average_monthly_income") is not None else ZERO}) if c.percentage is not None else c for c in changes]
    # Copy plain input values, never mapped SQLAlchemy objects or their identity state.
    goals=[SimpleNamespace(**{k:getattr(g,k) for k in ("id","user_id","name","target_amount","target_date","current_saved","priority","status")}) for g in context.goals]
    hypothetical=planning.EvaluationContext(context.capacity.model_copy(deep=True),goals,
        {gid:SimpleNamespace(profile=deepcopy(p.profile)) for gid,p in context.plans.items()})
    base_runway=financial_runway(db,uid,as_of=as_of,horizon_days=request.horizon_days,history=history,account_overview=accounts)
    scenario_runway=financial_runway(db,uid,as_of=as_of,horizon_days=request.horizon_days,history=history,account_overview=accounts,
        scenario_adjustments=lambda a,b:adjustments(changes,a,b))
    complete=history.adequate and history.baseline["status"]!="insufficient_data" and all(r["income"] is not None and r["income"]>ZERO and r["expenses"] is not None and r["expenses"]>ZERO for r in history.monthly)
    income=history.baseline.get("average_monthly_income") if complete else None
    expense=history.baseline.get("average_monthly_expenses") if complete else None
    income_delta=sum((c.amount for c in changes if c.change_type=="income_adjustment" and active(c,end)),ZERO)
    expense_delta=sum((c.amount for c in changes if c.change_type=="recurring_expense_adjustment" and active(c,end)),ZERO)
    savings_delta=sum((c.amount for c in changes if c.change_type=="savings_contribution_adjustment" and active(c,end)),ZERO)
    if savings_delta<ZERO:
        remaining=-savings_delta
        for goal in sorted((g for g in goals if g.status=="active"),key=lambda g:(g.priority,g.id),reverse=True):
            plan=hypothetical.plans.get(goal.id)
            if plan is None:continue
            previous=D(plan.profile["proposed_monthly"]);reduction=min(previous,remaining)
            plan.profile["proposed_monthly"]=str(previous-reduction);remaining-=reduction
        if remaining>ZERO:raise HTTPException(422,"Savings reduction exceeds accepted monthly goal commitments")
    # Reject underflow instead of silently clamping reductions into invented values.
    for segment in scenario_runway.checkpoints:
        di,de,_,_=adjustments(changes,segment.period_start,segment.date)
        if complete:
            fraction=D((segment.date-segment.period_start).days+1)/D(monthrange(segment.date.year,segment.date.month)[1])
            if income*fraction+di<ZERO or expense*fraction+de<ZERO: raise HTTPException(422,"Adjustment would make observed income or expenses negative")
    for c in changes:
        if c.target_id is None or not active(c,end):continue
        goal=next(g for g in goals if g.id==c.target_id)
        if goal.status!="active":raise HTTPException(422,"Goal changes require an active goal")
        if c.change_type=="goal_target_date_adjustment":goal.target_date=c.target_date
        if c.change_type=="goal_target_amount_adjustment":
            if goal.current_saved is not None and c.amount<goal.current_saved: raise HTTPException(422,"Target cannot be less than reported progress")
            goal.target_amount=c.amount
        if c.change_type=="goal_commitment_adjustment":
            if c.target_id not in hypothetical.plans:raise HTTPException(422,"Goal has no accepted commitment to adjust")
            hypothetical.plans[c.target_id].profile["proposed_monthly"]=str(c.amount)
    capacity=context.capacity;sc=hypothetical.capacity
    once_expenses=sum((c.amount for c in changes if c.change_type=="one_time_expense"),ZERO)
    current_windfalls=sum((c.amount for c in changes if c.change_type=="one_time_income" and c.effective_date==as_of),ZERO)
    if capacity.status=="sufficient":
        adjusted_income=capacity.conservative_income+income_delta*planning.INCOME_RELIABILITY_FACTOR
        adjusted_expense=capacity.protected_expenses+expense_delta
        if min(adjusted_income,adjusted_expense)<ZERO:raise HTTPException(422,"Adjustment would make protected planning inputs negative")
        # Planning uses its established 30-day reserve, not the potentially longer display horizon.
        planning_runway=financial_runway(db,uid,as_of=as_of,history=history,account_overview=accounts)
        near_term=max(capacity.upcoming_obligations,planning_runway.expected_expense_reserve or ZERO)
        near_term=max(capacity.upcoming_obligations,near_term+expense_delta)
        value,reserve=planning.capacity_from_facts(adjusted_income,adjusted_expense,near_term,
            capacity.trusted_cash+current_windfalls-once_expenses,capacity.overdue_obligations,capacity.reported_earmarks)
        sc.conservative_monthly_capacity=max(ZERO,value-max(ZERO,savings_delta));sc.protected_reserve=reserve
        sc.conservative_income=adjusted_income;sc.protected_expenses=adjusted_expense
    accepted=lambda ctx:sum((D(plan.profile["proposed_monthly"]) for gid,plan in ctx.plans.items() if any(g.id==gid and g.status=="active" for g in ctx.goals)),ZERO)
    base_commitment=accepted(context);scenario_commitment=accepted(hypothetical)
    available=lambda cap,commitment:planning.floor(max(ZERO,cap-commitment)) if cap is not None else None
    trusted=capacity.trusted_cash
    reasons="Required financial inputs are unavailable. "+" ".join(capacity.explanations)
    pairs=[("monthly_income",income,income+income_delta if income is not None else None),
        ("monthly_expenses",expense,expense+expense_delta if expense is not None else None),
        ("monthly_obligations",capacity.upcoming_obligations if request.schedules_confirmed else None,capacity.upcoming_obligations if request.schedules_confirmed else None),
        ("monthly_savings_capacity",capacity.conservative_monthly_capacity,sc.conservative_monthly_capacity),
        ("monthly_free_capacity",available(capacity.conservative_monthly_capacity,base_commitment),available(sc.conservative_monthly_capacity,scenario_commitment)),
        ("monthly_goal_commitments",base_commitment,scenario_commitment),
        ("monthly_additional_savings",ZERO,savings_delta),
        ("trusted_available_cash",trusted,trusted),
        ("projected_end_cash",base_runway.projected_end_balance if trusted is not None and complete else None,scenario_runway.projected_end_balance if trusted is not None and complete else None),
        ("minimum_projected_cash",base_runway.minimum_projected_balance if trusted is not None and complete else None,scenario_runway.minimum_projected_balance if trusted is not None and complete else None)]
    comparisons=[compare(k,b,a,reasons) for k,b,a in pairs]
    comparisons.extend([compare("runway_months",None,None,"AI-15D does not infer an exact runway duration from monthly history."),
        compare("financial_health",None,None,LIMITATIONS[-1],unavailable=True)])
    base_goals=goal_facts(context);scenario_goals=goal_facts(hypothetical)
    for before,after in zip(base_goals,scenario_goals):
        for key in ("target_amount","required_contribution","projected_contribution_capacity","accepted_commitment"):
            comparisons.append(compare(f"goal_{before['goal_id']}_{key}",D(before[key]) if before[key] is not None else None,D(after[key]) if after[key] is not None else None,reasons))
        old=next(g for g in context.goals if g.id==before["goal_id"]).target_date
        new=next(g for g in goals if g.id==before["goal_id"]).target_date
        comparisons.append(compare(f"goal_{before['goal_id']}_days_to_target",D((old-as_of).days) if old else None,D((new-as_of).days) if new else None,"Goal deadline is unspecified",percentage=False))
    affordability=None
    purchases=[c for c in changes if c.change_type=="one_time_expense"]
    if purchases:
        # Represent purchases as competing hypothetical goals; reuse AI-15P classifier/allocation.
        purchase_context=planning.EvaluationContext(sc.model_copy(deep=True),list(goals),hypothetical.plans)
        if capacity.status=="sufficient":
            purchase_context.capacity.conservative_monthly_capacity=max(ZERO,planning.capacity_from_facts(adjusted_income,adjusted_expense,near_term,
                capacity.trusted_cash+current_windfalls,capacity.overdue_obligations,capacity.reported_earmarks)[0]-max(ZERO,savings_delta))
        for i,c in enumerate(purchases):purchase_context.goals.append(SimpleNamespace(id=-(i+1),user_id=uid,name=c.description or "Hypothetical purchase",target_amount=c.amount,target_date=c.effective_date,current_saved=ZERO,priority=5,status="active"))
        statuses=[planning.assess_goal(g,purchase_context).feasibility for g in purchase_context.goals if g.id<0]
        affordability="insufficient_data" if "insufficient_data" in statuses else "not_affordable" if any(s in {"challenging","not_currently_feasible"} for s in statuses) or scenario_runway.runway_status=="cash_shortfall" else "affordable_with_adjustments" if "feasible_with_adjustments" in statuses else "affordable"
    evidence={"history":history.to_dict(),"capacity":capacity.model_dump(mode="json"),"baseline_runway":base_runway.model_dump(mode="json"),"scenario_runway":scenario_runway.model_dump(mode="json"),"baseline_goals":base_goals,"scenario_goals":scenario_goals}
    reference=sha256(json.dumps({"date":str(as_of),"history":evidence["history"],"capacity":evidence["capacity"],"runway":evidence["baseline_runway"],"goals":base_goals},sort_keys=True,default=str).encode()).hexdigest()
    result=ScenarioResult(scenario_id=sid,calculation_version=VERSION,baseline_snapshot_date=as_of,baseline_snapshot_reference=reference,horizon_end=end,comparisons=comparisons,
        baseline_goals=base_goals,scenario_goals=scenario_goals,assumptions=assumptions,limitations=LIMITATIONS+base_runway.limitations+capacity.limitations,affordability=affordability)
    return result,evidence

def result_for(db,uid,sid,run_id=None):
    owned(db,uid,sid)
    row=repository.run(db,uid,sid,run_id)
    if row is None:raise HTTPException(404,"No scenario result yet")
    metrics=repository.comparisons(db,uid,row.id)
    return ScenarioResult.model_validate({**row.evidence["result"],"run_id":row.id,"comparisons":[{k:getattr(m,k) for k in MetricComparison.model_fields} for m in metrics]})

def simulate(db,uid,sid,payload,*,as_of=None):
    planning.lock_user(db,uid);row=owned(db,uid,sid)
    request={**payload.model_dump(mode="json"),"scenario_id":sid,"revision":row.revision}
    prior=db.query(ScenarioRun).filter_by(user_id=uid,idempotency_key=payload.idempotency_key).one_or_none()
    if prior:
        if prior.request!=request:raise HTTPException(409,"Idempotency key already belongs to a different request")
        return result_for(db,uid,sid,prior.id)
    editable(row)
    result,evidence=calculate(db,uid,sid,changes_for(db,row),payload,as_of=as_of)
    run=ScenarioRun(scenario_id=sid,user_id=uid,idempotency_key=payload.idempotency_key,request=request,calculation_version=VERSION,
        baseline_snapshot_date=result.baseline_snapshot_date,baseline_snapshot_reference=result.baseline_snapshot_reference,
        evidence=json.loads(json.dumps({**evidence,"result":result.model_dump(mode="json",exclude={"comparisons","run_id"})},default=str)))
    db.add(run);db.flush()
    for metric in result.comparisons:db.add(ScenarioComparison(run_id=run.id,**metric.model_dump()))
    row.base_snapshot_reference=result.baseline_snapshot_reference;row.calculation_version=VERSION;row.updated_at=datetime.now(timezone.utc)
    db.commit();return result_for(db,uid,sid,run.id)
