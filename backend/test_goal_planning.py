"""Offline financial safety, ledger integrity, milestones and owner isolation."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.database import Base,get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import User,Account,Transaction,SavingsGoal,ScheduledCashflowItem
from app.models.goal_planning import GoalPlanRecord,GoalMilestone,GoalProgressEvent
from app.schemas.goal_planning import PlanRequest,ContributionRequest,MilestoneUpdate
from app.services.finance import goal_planning as p

DAY=date(2026,11,1)
@pytest.fixture
def data():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        users=[User(email=f"planner{i}@example.com",hashed_password="x") for i in range(2)]
        db.add_all(users);db.commit();yield db,users
    engine.dispose()

def seed(db,user,*,target="10000",saved="0",deadline=date(2027,4,30),cash="100000",priority=3):
    if db.query(Account).filter_by(user_id=user.id).count()==0:
        db.add(Account(user_id=user.id,name="Private cash",currency="BDT",opening_balance=D(cash),opening_balance_date=DAY,current_balance=D(cash),balance_as_of=datetime(2026,11,1,tzinfo=timezone.utc)))
        for month in [8,9,10]:
            db.add(Transaction(user_id=user.id,date=date(2026,month,2),amount=D("30000")))
            db.add(Transaction(user_id=user.id,date=date(2026,month,3),amount=D("-5000")))
    goal=SavingsGoal(user_id=user.id,name="Laptop",target_amount=D(target),current_saved=D(saved) if saved is not None else None,target_date=deadline,priority=priority)
    db.add(goal);db.commit();return goal

def request(key="request-0001",**kw):return PlanRequest(idempotency_key=key,schedules_confirmed=True,**kw)

def test_conservative_capacity_and_verified_progress(data):
    db,users=data;g=seed(db,users[0],saved="1000")
    context=p.build_context(db,g.user_id,schedules_confirmed=True,as_of=DAY)
    plan=p.assess_goal(g,context)
    assert plan.feasibility=="feasible" and plan.verified_goal_progress is None
    assert plan.remaining_amount==10000 and plan.reported_remaining_amount==9000
    assert context.capacity.conservative_income==24000
    assert context.capacity.conservative_monthly_capacity<19000
    assert plan.required_monthly==D("1666.67")
    assert context.capacity.protected_reserve>10000

@pytest.mark.parametrize("required,available,expected",[("100","100","feasible"),("110","100","feasible_with_adjustments"),("110.01","100","challenging"),("150","100","challenging"),("150.01","100","not_currently_feasible"),("1","0","not_currently_feasible")])
def test_status_boundaries(required,available,expected):assert p.classify(D(required),D(available))==expected

@pytest.mark.parametrize("missing",["income","expense","cash","verification","stale","earmarks","schedules"])
def test_missing_inputs_never_invent_capacity(data,missing):
    db,users=data;g=seed(db,users[0],saved=None if missing=="earmarks" else "0")
    if missing in {"income","expense"}:db.query(Transaction).filter(Transaction.user_id==g.user_id,Transaction.amount>0 if missing=="income" else Transaction.amount<0).delete()
    if missing=="cash":db.query(Account).filter_by(user_id=g.user_id).delete()
    if missing=="verification":db.query(Account).one().current_balance=None
    if missing=="stale":db.query(Account).one().balance_as_of=datetime(2026,9,1,tzinfo=timezone.utc)
    db.commit();context=p.build_context(db,g.user_id,schedules_confirmed=missing!="schedules",as_of=DAY)
    result=p.assess_goal(g,context)
    assert result.feasibility=="insufficient_data" and result.proposed_monthly==0
    assert context.capacity.conservative_monthly_capacity is None

def test_obligations_and_reserve_prevent_allocating_all_cash(data):
    db,users=data;g=seed(db,users[0],cash="20000")
    for due in [DAY+timedelta(days=3),DAY-timedelta(days=3)]:db.add(ScheduledCashflowItem(user_id=g.user_id,title="Bill",kind="expense",amount=D("9000"),due_date=due,status="scheduled"))
    db.commit();context=p.build_context(db,g.user_id,schedules_confirmed=True,as_of=DAY)
    assert context.capacity.conservative_monthly_capacity==0
    assert context.capacity.overdue_obligations==9000
    assert p.assess_goal(g,context).proposed_monthly==0

@pytest.mark.parametrize("cadence",["monthly","weekly"])
@pytest.mark.parametrize("target",["0.01","10000.01","12345.67"])
def test_milestones_exact_and_monthly_budget_safe(cadence,target):
    deadline=date(2027,4,30);rows=p.milestone_schedule(D(target),DAY,deadline,cadence)
    assert sum((r["expected_contribution"] for r in rows),D(0))==D(target)
    assert rows[-1]["target_cumulative"]==D(target) and rows[-1]["due_date"]==deadline
    assert all(r["expected_contribution"]>0 for r in rows)
    totals={}
    for row in rows:totals[row["due_date"].strftime("%Y-%m")]=totals.get(row["due_date"].strftime("%Y-%m"),D(0))+row["expected_contribution"]
    assert max(totals.values())<=p.required_monthly_contribution(D(target),deadline,DAY)

def test_multiple_goals_respect_priority_and_accepted_commitments(data):
    db,users=data;one=seed(db,users[0],target="100000",priority=1);two=seed(db,users[0],target="100000",priority=5)
    context=p.build_context(db,one.user_id,schedules_confirmed=True,as_of=DAY);shares=p.allocations(context)
    assert sum(shares.values(),D(0))<=context.capacity.conservative_monthly_capacity
    assert shares[one.id]>shares[two.id]
    first=p.create_plan(db,one.user_id,one.id,request(),as_of=DAY)
    second=p.create_plan(db,two.user_id,two.id,request("request-0002"),as_of=DAY)
    assert first.proposed_monthly+second.proposed_monthly<=context.capacity.conservative_monthly_capacity

def test_alternatives_are_recalculated_and_not_automatically_accepted(data):
    db,users=data;g=seed(db,users[0],target="100000",deadline=DAY)
    result=p.create_plan(db,g.user_id,g.id,request(),as_of=DAY)
    assert result.feasibility!="feasible" and result.milestones==[]
    assert result.alternatives and all(a.feasibility=="feasible" for a in result.alternatives)
    assert g.target_date==DAY and g.target_amount==100000
    alt=result.alternatives[0]
    revised=p.create_plan(db,g.user_id,g.id,request("request-0002",target_date=alt.target_date),replan=True,as_of=DAY)
    assert revised.version==2 and revised.feasibility=="feasible"
    assert db.query(GoalPlanRecord).filter_by(goal_id=g.id,user_id=g.user_id).count()==2
    assert db.query(GoalPlanRecord).filter_by(id=result.id,user_id=g.user_id).one().profile["target_date"]==DAY.isoformat()

def test_plan_and_contribution_idempotency_and_history(data):
    db,users=data;g=seed(db,users[0]);initial=p.create_plan(db,g.user_id,g.id,request(),as_of=DAY)
    assert p.create_plan(db,g.user_id,g.id,request(),as_of=DAY).id==initial.id
    assert p.create_plan(db,g.user_id,g.id,request("request-0002"),as_of=DAY).id==initial.id
    contribution=ContributionRequest(idempotency_key="contribute-001",amount=D("2000"))
    first=p.record_contribution(db,g.user_id,g.id,contribution)
    assert p.record_contribution(db,g.user_id,g.id,contribution).event_id==first.event_id
    assert g.current_saved==2000
    assert db.query(GoalMilestone).filter_by(user_id=g.user_id,goal_id=g.id,status="reported_completed").count()==1
    assert db.query(GoalProgressEvent).filter_by(user_id=g.user_id,kind="milestone_achieved").count()==1
    with pytest.raises(HTTPException) as ex:p.record_contribution(db,g.user_id,g.id,ContributionRequest(idempotency_key="contribute-001",amount=D("1")))
    assert ex.value.status_code==409
    final=p.record_contribution(db,g.user_id,g.id,ContributionRequest(idempotency_key="contribute-002",amount=D("8000")))
    assert final.goal_status=="completed" and g.current_saved==10000
    assert db.query(Account).one().current_balance==100000

def test_unknown_progress_and_overpayment_rejected(data):
    db,users=data;g=seed(db,users[0],saved=None)
    for amount in [D("1"),D("10001")]:
        with pytest.raises(HTTPException):p.record_contribution(db,g.user_id,g.id,ContributionRequest(idempotency_key="contribute-001",amount=amount))
    g.current_saved=D("0");db.commit()
    with pytest.raises(HTTPException):p.record_contribution(db,g.user_id,g.id,ContributionRequest(idempotency_key="contribute-002",amount=D("10001")))
    assert db.query(GoalProgressEvent).count()==0

def test_no_deadline_and_overdue_goals_have_explicit_alternatives(data):
    db,users=data;g=seed(db,users[0],deadline=None)
    context=p.build_context(db,g.user_id,schedules_confirmed=True,as_of=DAY);result=p.assess_goal(g,context)
    assert result.required_monthly is None and result.feasibility=="feasible_with_adjustments" and result.alternatives
    g.target_date=DAY-timedelta(days=1)
    assert p.assess_goal(g,context).feasibility=="not_currently_feasible"

def test_hypothetical_increases_never_inflate_current_capacity(data):
    db,users=data;g=seed(db,users[0])
    base=p.build_context(db,g.user_id,schedules_confirmed=True,as_of=DAY)
    optimistic=p.build_context(db,g.user_id,schedules_confirmed=True,income_change_percent=D("50"),expense_change_percent=D("-50"),as_of=DAY)
    assert optimistic.capacity.conservative_monthly_capacity==base.capacity.conservative_monthly_capacity
    pessimistic=p.build_context(db,g.user_id,schedules_confirmed=True,income_change_percent=D("-50"),as_of=DAY)
    assert pessimistic.capacity.conservative_monthly_capacity<base.capacity.conservative_monthly_capacity

def test_goal_count_does_not_multiply_financial_queries(data):
    db,users=data;g=seed(db,users[0]);queries=[];engine=db.get_bind()
    def track(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().startswith("SELECT"):queries.append(statement)
    event.listen(engine,"before_cursor_execute",track)
    try:
        p.planning_overview(db,g.user_id,schedules_confirmed=True,as_of=DAY);first=len(queries)
        for i in range(12):seed(db,users[0])
        queries.clear();p.planning_overview(db,g.user_id,schedules_confirmed=True,as_of=DAY)
        assert len(queries)==first
    finally:event.remove(engine,"before_cursor_execute",track)

def test_authenticated_apis_optional_deadline_and_tenant_isolation(data):
    db,users=data;g=seed(db,users[0]);app.dependency_overrides[get_db]=lambda:db
    try:
        with TestClient(app) as client:
            assert client.get("/finance/goals/planning/overview").status_code==401
            app.dependency_overrides[get_current_user]=lambda:users[0]
            created=client.post("/finance/goals",json={"name":"Emergency","target_amount":"20000","current_saved":"0","goal_type":"emergency_fund","priority":1}).json()
            assert created["target_date"] is None and created["currency"]=="BDT"
            assert client.get(f"/finance/goals/{created['id']}/plan").status_code==200
            assert client.patch(f"/finance/goals/{g.id}",json={"status":"paused"}).status_code==200
            assert client.patch(f"/finance/goals/{g.id}",json={"status":"active"}).status_code==200
            assert client.post(f"/finance/goals/{g.id}/plan",json=request().model_dump(mode="json")).status_code==200
            assert client.get(f"/finance/goals/{g.id}/plans/current").status_code==200
            assert client.get(f"/finance/goals/{g.id}/events").status_code==200
            app.dependency_overrides[get_current_user]=lambda:users[1]
            for path in ["plans/current","milestones","events","plans"]:assert client.get(f"/finance/goals/{g.id}/{path}").status_code==404
            assert client.post(f"/finance/goals/{g.id}/contributions",json={"amount":"1","idempotency_key":"foreign-0001"}).status_code==404
            assert client.get("/finance/goals/planning/overview").json()["goals"]==[]
    finally:app.dependency_overrides.clear()


def test_missed_milestones_feed_stable_coaching_and_reported_outcomes(data):
    from app.services.finance.coaching import financial_coaching
    from app.services.finance.action_plan import action_plan
    from app.services.finance.action_outcome import _goal_outcome
    db,users=data;g=seed(db,users[0]);plan=p.create_plan(db,g.user_id,g.id,request(),as_of=DAY)
    first=db.query(GoalMilestone).filter_by(user_id=g.user_id,goal_id=g.id,plan_id=plan.id).order_by(GoalMilestone.sequence).first()
    first.due_date=DAY-timedelta(days=1);db.commit()
    a=[r for r in financial_coaching(db,g.user_id,as_of=DAY).recommendations if r.type=="goal_risk"]
    b=[r for r in financial_coaching(db,g.user_id,as_of=DAY).recommendations if r.type=="goal_risk"]
    assert len(a)==1 and a[0].id==b[0].id and a[0].evidence.milestone_id==first.id
    from app.services.finance.coaching_feedback import evidence_key
    tomorrow=[r for r in financial_coaching(db,g.user_id,as_of=DAY+timedelta(days=1)).recommendations if r.type=="goal_risk"]
    assert evidence_key(a[0])==evidence_key(tomorrow[0])
    assert any(r.recommendation_id==a[0].id for r in action_plan(db,g.user_id,as_of=DAY).actions)
    p.record_contribution(db,g.user_id,g.id,ContributionRequest(idempotency_key="complete-goal-01",amount=D("10000")))
    # Completion stamps real wall-clock time; pin it onto DAY so the fixed action window stays deterministic.
    for m in db.query(GoalMilestone).filter_by(user_id=g.user_id,goal_id=g.id,status="reported_completed"):m.completed_at=datetime(2026,11,1,12,tzinfo=timezone.utc)
    db.commit()
    outcome=_goal_outcome(db,g.user_id,a[0].id,"goal_risk",DAY,DAY,None)
    assert outcome.evidence.reported_completed_milestones==len(plan.milestones)
    assert outcome.evidence.goal_progress_source=="user_reported" and outcome.causal_claim is False


def test_openapi_planning_contract_and_invalid_payload(data):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):ContributionRequest(idempotency_key="valid-key",amount="-1")
    with pytest.raises(ValidationError):PlanRequest(idempotency_key="valid-key",income_change_percent="51")
    spec=app.openapi()
    for suffix,method in [("planning/overview","get"),("{goal_id}/plan","post"),("{goal_id}/replan","post"),("{goal_id}/contributions","post"),("{goal_id}/plans/current","get"),("{goal_id}/milestones","get"),("{goal_id}/milestones/{milestone_id}","patch")]:
        assert method in spec["paths"]["/finance/goals/"+suffix]


def test_replay_distinguishes_cleared_deadline_and_internal_event_keys(data):
    db,users=data;g=seed(db,users[0]);p.create_plan(db,g.user_id,g.id,request(),as_of=DAY)
    payload=request("replan-same-key")
    p.create_plan(db,g.user_id,g.id,payload,replan=True,as_of=DAY)
    with pytest.raises(HTTPException) as ex:p.create_plan(db,g.user_id,g.id,request("replan-same-key",target_date=None),replan=True,as_of=DAY)
    assert ex.value.status_code==409 and g.target_date is not None
    m=db.query(GoalMilestone).filter_by(user_id=g.user_id,goal_id=g.id).order_by(GoalMilestone.id).first()
    p.record_contribution(db,g.user_id,g.id,ContributionRequest(idempotency_key=f"milestone-{m.id}-achieved",amount=D("2000")))
    assert db.query(GoalProgressEvent).filter_by(user_id=g.user_id,idempotency_key=f"milestone-{m.id}-achieved").count()==1
    assert db.query(GoalProgressEvent).filter_by(user_id=g.user_id,idempotency_key=f"request-milestone-{m.id}-achieved").count()==1


def test_reported_completed_goal_never_allocates_extra_cash(data):
    db,users=data;g=seed(db,users[0],saved="10000");g.status="completed";db.commit()
    result=p.create_plan(db,g.user_id,g.id,request(),as_of=DAY)
    assert result.proposed_monthly==0 and result.verified_goal_progress is None
    assert result.reported_remaining_amount==0 and result.milestones==[]
