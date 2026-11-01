"""Independent arithmetic, tenant isolation, frozen history and real-state safety."""
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal as D
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from pydantic import ValidationError
from test_goal_planning import data, seed, DAY, request as plan_request
from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, Transaction, SavingsGoal, ScheduledCashflowItem
from app.models.financial_health import FinancialHealthSnapshot
from app.models.scenarios import ScenarioRun
from app.schemas.scenarios import ScenarioCreate, ScenarioChange, ChangesRequest, SimulationRequest
from app.services.finance import scenarios as s, goal_planning as p

def change(kind,amount=None,**kw):
    recurring=kind in {"income_adjustment","recurring_expense_adjustment","savings_contribution_adjustment"}
    return ScenarioChange(change_type=kind,amount=amount,effective_date=DAY,frequency="monthly" if recurring else None,**kw)

def setup(db,user,changes=()):
    row=s.create(db,user.id,ScenarioCreate(name="What if"))
    return s.replace_changes(db,user.id,row.id,ChangesRequest(changes=list(changes)))

def run(db,user,row,key="simulation-0001",**kw):
    return s.simulate(db,user.id,row.id,SimulationRequest(idempotency_key=key,schedules_confirmed=True,**kw),as_of=DAY)

def metrics(result):return {m.metric:m for m in result.comparisons}

@pytest.mark.parametrize("kind,amount,metric,delta",[
    ("income_adjustment","5000","monthly_income","5000"),("income_adjustment","-5000","monthly_income","-5000"),
    ("recurring_expense_adjustment","2000","monthly_expenses","2000"),("recurring_expense_adjustment","-2000","monthly_expenses","-2000"),
    ("one_time_expense","6000","projected_end_cash","-6000"),("one_time_income","6000","projected_end_cash","6000"),
    ("savings_contribution_adjustment","2000","monthly_free_capacity","-2000")])
def test_arithmetic(data,kind,amount,metric,delta):
    db,users=data;seed(db,users[0]);row=setup(db,users[0],[change(kind,amount)])
    m=metrics(run(db,users[0],row));assert m[metric].absolute_delta==D(delta)
    assert m["trusted_available_cash"].absolute_delta==0
    assert m["financial_health"].status=="not_available_for_scenario"

def test_savings_decrease_and_goal_commitment(data):
    db,users=data;g=seed(db,users[0]);plan=p.create_plan(db,g.user_id,g.id,plan_request(),as_of=DAY)
    row=setup(db,users[0],[change("savings_contribution_adjustment","-500")]);result=run(db,users[0],row)
    assert metrics(result)["monthly_goal_commitments"].absolute_delta==D("-500")
    assert metrics(result)["monthly_free_capacity"].absolute_delta==D("500")
    assert p.current_plan(db,g.user_id,g.id).proposed_monthly==plan.proposed_monthly
    row=setup(db,users[0],[change("goal_commitment_adjustment","100",target_id=g.id)])
    assert run(db,users[0],row,key="commitment-0001").scenario_goals[0]["accepted_commitment"]=="100.00"

@pytest.mark.parametrize("kind,amount,deadline",[("goal_target_amount_adjustment","20000",None),("goal_target_amount_adjustment","5000",None),("goal_target_date_adjustment",None,date(2027,1,31)),("goal_target_date_adjustment",None,date(2027,9,30))])
def test_goal_replacements(data,kind,amount,deadline):
    db,users=data;g=seed(db,users[0]);row=setup(db,users[0],[change(kind,amount,target_id=g.id,target_date=deadline)])
    result=run(db,users[0],row);goal=result.scenario_goals[0]
    target=D(amount) if amount else D("10000");end=deadline or g.target_date
    months=(end.year-DAY.year)*12+end.month-DAY.month+1
    from decimal import ROUND_UP
    assert D(goal["required_contribution"])==(target/D(months)).quantize(D(".01"),rounding=ROUND_UP)
    assert g.target_amount==10000 and g.target_date==date(2027,4,30)

@pytest.mark.parametrize("before,after,direction,pct",[("100","150","increased","50"),("100","50","decreased","-50"),("100","100","unchanged","0"),("0","50","increased",None),(None,"50","unknown",None),("-100","50","increased",None)])
def test_comparisons(before,after,direction,pct):
    m=s.compare("test",D(before) if before else None,D(after),"Missing data")
    assert m.direction==direction and m.percentage_delta==(D(pct) if pct else None)
    if before is None:assert m.status=="insufficient_data" and m.reason

def state(db):
    tables=[t for t in Base.metadata.sorted_tables if t.name not in {"financial_scenarios","scenario_changes","scenario_runs","scenario_comparisons"}]
    return {t.name:[tuple(row) for row in db.execute(select(t).order_by(*t.primary_key.columns))] for t in tables}

def test_isolation_determinism_immutable_history_and_replay(data):
    db,users=data;g=seed(db,users[0]);db.add(ScheduledCashflowItem(user_id=g.user_id,title="Bill",kind="expense",amount=D("1000"),due_date=DAY+timedelta(days=3),status="scheduled"))
    db.add(FinancialHealthSnapshot(user_id=g.user_id,snapshot_date=DAY,observed_at=datetime.now(timezone.utc),overall_score=D("50"),status="fair",coverage_percent=D("100"),data_quality_status="sufficient",schema_version="v1",calculation_version="test",profile={}))
    db.commit();row=setup(db,users[0],[change("income_adjustment","-1000"),change("goal_target_amount_adjustment","20000",target_id=g.id)])
    before=state(db);first=run(db,users[0],row);again=run(db,users[0],row)
    assert first==again and state(db)==before and db.query(ScenarioRun).count()==1
    other=run(db,users[0],row,key="simulation-0002")
    assert first.model_dump(exclude={"run_id"})==other.model_dump(exclude={"run_id"})
    account=db.query(Account).filter_by(user_id=g.user_id).one();account.current_balance=D("1");db.commit()
    assert run(db,users[0],row)==first
    assert s.result_for(db,g.user_id,row.id,first.run_id)==first
    s.replace_changes(db,g.user_id,row.id,ChangesRequest(changes=[]))
    with pytest.raises(HTTPException) as exc:run(db,users[0],row)
    assert exc.value.status_code==409

@pytest.mark.parametrize("missing",["cash","income","schedules","earmarks"])
def test_missing(data,missing):
    db,users=data;seed(db,users[0],saved=None if missing=="earmarks" else "0")
    if missing=="cash":db.query(Account).delete()
    if missing=="income":db.query(Transaction).filter(Transaction.amount>0).delete()
    db.commit();row=setup(db,users[0],[change("income_adjustment","5000")])
    result=s.simulate(db,users[0].id,row.id,SimulationRequest(idempotency_key="missing-data",schedules_confirmed=missing!="schedules"),as_of=DAY)
    m=metrics(result);assert m["monthly_savings_capacity"].status=="insufficient_data" and m["monthly_savings_capacity"].reason
    if missing=="cash":assert m["trusted_available_cash"].scenario_value is None
    if missing=="income":assert m["monthly_income"].scenario_value is None

def test_api_owner_scope_and_archive(data):
    db,users=data;g=seed(db,users[0]);foreign=seed(db,users[1]);row=setup(db,users[0])
    app.dependency_overrides[get_db]=lambda:db
    try:
        with TestClient(app) as client:
            assert client.get("/finance/scenarios").status_code==401
            app.dependency_overrides[get_current_user]=lambda:users[1]
            for suffix in ["","/result","/comparison"]:assert client.get(f"/finance/scenarios/{row.id}{suffix}").status_code==404
            for suffix,body in [("/changes",{"changes":[]}),("/simulate",{"idempotency_key":"foreign-run"}),("/archive",{}),("/save",{})]:assert client.post(f"/finance/scenarios/{row.id}{suffix}",json=body).status_code==404
            assert client.get("/finance/scenarios").json()["items"]==[]
            app.dependency_overrides[get_current_user]=lambda:users[0]
            c=change("goal_target_amount_adjustment","1",target_id=foreign.id)
            assert client.post(f"/finance/scenarios/{row.id}/changes",json={"changes":[c.model_dump(mode="json")]}).status_code==404
            assert client.get("/finance/scenarios/baseline").status_code==200
            assert client.post("/finance/scenarios",json={"name":"x","user_id":users[1].id}).status_code==422
            assert client.post(f"/finance/scenarios/{row.id}/save").json()["status"]=="saved"
            assert client.post(f"/finance/scenarios/{row.id}/archive").status_code==200
            assert client.post(f"/finance/scenarios/{row.id}/changes",json={"changes":[]}).status_code==409
            assert client.post(f"/finance/scenarios/{row.id}/simulate",json={"idempotency_key":"archived-run"}).status_code==409
    finally:app.dependency_overrides.clear()

def test_dated_proration_percentage_and_future_windfall(data):
    db,users=data;seed(db,users[0]);row=setup(db,users[0],[change("income_adjustment",percentage=D("-15"))])
    assert metrics(run(db,users[0],row))["monthly_income"].absolute_delta==D("-4500")
    c=change("recurring_expense_adjustment","3000",end_date=date(2026,11,15))
    row=setup(db,users[0],[c]);m=metrics(run(db,users[0],row,key="prorated-run",horizon_days=30))
    assert m["monthly_expenses"].absolute_delta==0 and m["projected_end_cash"].absolute_delta==D("-1500")
    c=ScenarioChange(change_type="one_time_income",amount="100000",effective_date=DAY+timedelta(days=20))
    row=setup(db,users[0],[c]);m=metrics(run(db,users[0],row,key="future-windfall"))
    assert m["monthly_savings_capacity"].absolute_delta==0 and m["projected_end_cash"].absolute_delta==100000

@pytest.mark.parametrize("kw",[{"amount":"NaN"},{"amount":"0.001"},{"amount":"1","currency":"USD"},{"amount":"1","target_id":1},{"amount":"1","frequency":None}])
def test_invalid_change_contract(kw):
    with pytest.raises(ValidationError):ScenarioChange(change_type="income_adjustment",effective_date=DAY,**kw)

def test_affordability_and_multi_purchase_pressure(data):
    db,users=data;seed(db,users[0]);c=ScenarioChange(change_type="one_time_expense",amount="60000",effective_date=date(2027,2,28))
    row=setup(db,users[0],[c]);assert run(db,users[0],row).affordability=="affordable_with_adjustments"
    row=setup(db,users[0],[c,c.model_copy(update={"amount":D("60000")})]);assert run(db,users[0],row,key="multi-purchase").affordability=="not_affordable"


def test_intent_parser_never_guesses_or_runs(data):
    from app.services.finance.scenario_intent import parse_scenario_intent
    from app.services.finance.grounded_chat import answer_question
    from app.schemas.chat import FinanceQuestionRequest
    intent=parse_scenario_intent("What if my salary drops 15%?")
    assert intent["changes"][0]["percentage"]=="-15" and intent["status"]=="needs_confirmation"
    assert parse_scenario_intent("What if my rent goes up by 5000?")["changes"][0]["amount"]=="5000"
    assert parse_scenario_intent("What if I save 8000 per month?")["status"]=="clarification_required"
    assert parse_scenario_intent("What if rent increases by 5000 and salary falls?")["changes"]==[]
    db,users=data
    result=answer_question(db,users[0].id,FinanceQuestionRequest(question="What if my rent goes up by 5000?"),as_of=DAY)
    assert result["intent"]=="scenario" and result["status"]=="needs_confirmation"
    assert db.query(ScenarioRun).count()==0


def test_completed_commitments_are_not_reserved_again(data):
    db,users=data;goal=seed(db,users[0]);p.create_plan(db,users[0].id,goal.id,plan_request(),as_of=DAY)
    goal.status="completed";goal.current_saved=goal.target_amount;db.commit();scenario=setup(db,users[0]);m=metrics(run(db,users[0],scenario))
    assert m["monthly_goal_commitments"].baseline_value==0
    assert m["monthly_free_capacity"].baseline_value==m["monthly_savings_capacity"].baseline_value

def test_reductions_and_dates_fail_without_mutating(data):
    db,users=data;seed(db,users[0])
    for c in [change("recurring_expense_adjustment","-6000"),change("savings_contribution_adjustment","-1"),ScenarioChange(change_type="one_time_expense",amount="100",effective_date=DAY+timedelta(days=200))]:
        row=setup(db,users[0],[c]);before=state(db)
        with pytest.raises(HTTPException) as exc:run(db,users[0],row)
        assert exc.value.status_code==422 and state(db)==before
        db.rollback()


def test_percentage_rounding_is_presentational_not_a_capacity_policy():
    assert s.compare("capacity",D("12000"),D("7000")).percentage_delta==D("-41.67")
