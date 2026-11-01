"""Health normalization, missing-data semantics, persistence and tenant contract."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import User, Account, Transaction, ScheduledCashflowItem
from app.models.savings_goal import SavingsGoal
from app.models.financial_health import FinancialHealthSnapshot
from app.services.finance import financial_health as h

DAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)

@pytest.fixture
def data():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        users = [User(email=f"health{i}@example.com", hashed_password="x") for i in range(2)]
        db.add_all(users); db.commit()
        yield db, users
    engine.dispose()

def seed(db, user, income="10000", expenses=("5000", "5000", "5000"), cash="60000", verified=True):
    for month, expense in zip((8,9,10), expenses):
        if income:
            db.add(Transaction(user_id=user.id, date=date(2026,month,2), amount=D(income)))
        db.add(Transaction(user_id=user.id, date=date(2026,month,3), amount=-D(expense)))
    db.add(Account(user_id=user.id, name="Private account", currency="BDT", opening_balance=D(cash), opening_balance_date=DAY,
        current_balance=D(cash) if verified else None, balance_as_of=NOW if verified else None))
    db.add(ScheduledCashflowItem(user_id=user.id, title="Private bill", kind="expense", amount=D("1000"), due_date=DAY+timedelta(days=5), status="scheduled"))
    db.add(SavingsGoal(user_id=user.id, name="Private goal", target_amount=D("10000"), current_saved=D("8000"), target_date=date(2027,1,1), status="active"))
    db.commit()

def components(profile):
    return {c.key:c for c in profile.components}

@pytest.mark.parametrize("score,status", [(None,"insufficient_data"),(D("0"),"strained"),(D("39.99"),"strained"),(D("40"),"watch"),(D("59.99"),"watch"),(D("60"),"stable"),(D("79.99"),"stable"),(D("80"),"strong"),(D("100"),"strong")])
def test_thresholds(score,status):
    assert h.classify(score) == status

@pytest.mark.parametrize("count", [0,1,3,7])
def test_equal_weight_coverage_and_decimal(count):
    rows = [h.component(k, D("61.23") if i<count else None) for i,k in enumerate(h.COMPONENT_WEIGHTS)]
    p = h.aggregate(rows, DAY)
    assert p.overall_score == (D("61.23") if count else None)
    assert p.coverage_percent == h.rounded(D(count) / 7 * 100)
    assert len(p.available_components) == count
    assert all(c.score is None for c in p.components[count:])

def test_weighted_aggregation():
    keys=list(h.COMPONENT_WEIGHTS)
    p=h.aggregate([h.component(k, D(i*10) if i<3 else None) for i,k in enumerate(keys)], DAY)
    assert p.overall_score == D("10")

@pytest.mark.parametrize("income,expenses,cash,expected", [
    ("10000",("5000","5000","5000"),"60000","strong"),
    ("1000",("5000","8000","9000"),"100","strained"),
    ("5000",("5000","5000","5000"),"3000","watch"),
])
def test_authoritative_evidence_and_conditions(data,income,expenses,cash,expected):
    db,users=data;seed(db,users[0],income,expenses,cash)
    p=h.gather_profile(db,users[0].id,as_of=DAY,observed_at=NOW); c=components(p)
    assert len(p.available_components)==7
    assert c["cashflow_stability"].status == expected if expected != "watch" else c["cashflow_stability"].score == 50
    assert c["liquidity"].evidence[0].value==D(cash)
    assert c["obligation_pressure"].evidence[0].value==D("1000")
    assert all(e.as_of_date <= DAY for v in p.components for e in v.evidence)
    assert isinstance(p.overall_score,D)
    text=p.model_dump_json()
    assert "Private account" not in text and "Private bill" not in text and "Private goal" not in text
    assert "caused" not in text

def test_empty_and_no_implicit_evaluation(data):
    db,users=data
    p=h.current_profile(db,users[0].id)
    assert p.overall_score is None and p.coverage_percent==0 and p.observed_at is None
    assert db.query(FinancialHealthSnapshot).count()==0
    p=h.evaluate(db,users[0].id,as_of=DAY)
    assert p.overall_score is None and p.missing_components==list(h.COMPONENT_WEIGHTS)

@pytest.mark.parametrize("missing", ["cash","income","obligations","goals","verification","stale"])
def test_missing_data_stays_unknown(data,missing):
    db,users=data;u=users[0];seed(db,u,income=None if missing=="income" else "10000",verified=missing!="verification")
    if missing=="cash": db.query(Account).filter_by(user_id=u.id).delete()
    if missing=="obligations": db.query(ScheduledCashflowItem).filter_by(user_id=u.id).delete()
    if missing=="goals": db.query(SavingsGoal).filter_by(user_id=u.id).delete()
    if missing=="stale": db.query(Account).filter_by(user_id=u.id).one().balance_as_of=NOW-timedelta(days=31)
    db.commit();c=components(h.gather_profile(db,u.id,as_of=DAY))
    key={"cash":"liquidity","income":"cashflow_stability","obligations":"obligation_pressure","goals":"savings_progress","verification":"account_reliability","stale":"liquidity"}[missing]
    assert c[key].score is None and c[key].status=="insufficient_data"

def test_single_large_purchase_is_not_repeated_growth(data):
    db,users=data;seed(db,users[0],expenses=("1000","1000","50000"))
    assert components(h.gather_profile(db,users[0].id,as_of=DAY))["spending_stability"].score==100

def test_obligation_pressure_not_large_balance_alone(data):
    db,users=data;seed(db,users[0])
    db.query(ScheduledCashflowItem).one().amount=D("100000");db.commit()
    c=components(h.gather_profile(db,users[0].id,as_of=DAY))
    assert c["obligation_pressure"].score==0
    assert c["liquidity"].score<40

def test_idempotency_history_and_tenant_isolation(data):
    db,users=data;u=users[0]
    h.evaluate(db,u.id,as_of=DAY-timedelta(days=8));h.evaluate(db,u.id,as_of=DAY)
    h.evaluate(db,u.id,as_of=DAY)
    assert db.query(FinancialHealthSnapshot).filter_by(user_id=u.id).count()==2
    assert len(h.history_profiles(db,u.id,from_date=DAY))==1
    assert h.history_profiles(db,users[1].id)==[]
    rows=h.history_profiles(db,u.id)
    assert rows[0].as_of_date < rows[1].as_of_date
    row=db.query(FinancialHealthSnapshot).first();payload=dict(row.profile);payload["calculation_version"]="old-v0";row.calculation_version="old-v0";row.profile=payload;db.commit()
    assert h.history_profiles(db,u.id)[0].calculation_version=="old-v0"

@pytest.mark.parametrize("change,direction", [(D("8"),"improving"),(D("2.99"),"stable"),(D("-3"),"declining")])
def test_descriptive_trend(change,direction):
    def p(day,score):return h.aggregate([h.component(k,score) for k in h.COMPONENT_WEIGHTS],day)
    first=p(DAY-timedelta(days=30),D("60"));last=p(DAY,D("60")+change)
    trend=h.trend_from_profiles([first,last]);assert trend.direction==direction and trend.change==change
    assert h.trend_from_profiles([last]).direction=="insufficient_data"
    last.calculation_version="future-v2"
    assert h.trend_from_profiles([first,last]).direction=="insufficient_data"
    last.calculation_version=first.calculation_version;last.available_components=[]
    assert h.trend_from_profiles([first,last]).direction=="insufficient_data"

def test_api_auth_scope_validation_and_openapi(data):
    db,users=data
    app.dependency_overrides[get_db]=lambda:db
    try:
        with TestClient(app) as client:
            for method,path in [("get",""),("post","/evaluate"),("get","/history"),("get","/trend")]:
                assert getattr(client,method)("/finance/health"+path).status_code==401
            app.dependency_overrides[get_current_user]=lambda:users[0]
            assert client.post("/finance/health/evaluate").status_code==200
            assert len(client.get("/finance/health/history").json())==1
            assert client.get("/finance/health/history?from_date=2027-01-01&to_date=2026-01-01").status_code==422
            assert client.get("/finance/health/history?limit=0").status_code==422
            app.dependency_overrides[get_current_user]=lambda:users[1]
            assert client.get("/finance/health/history").json()==[]
            assert client.get("/finance/health").json()["overall_score"] is None
            assert client.get("/finance/health/trend").json()["direction"]=="insufficient_data"
    finally:app.dependency_overrides.clear()
    spec=app.openapi()
    for path in ("/finance/health","/finance/health/history","/finance/health/trend","/finance/health/evaluate"):
        assert path in spec["paths"]


@pytest.mark.parametrize("age,available", [(0,True),(30,True),(31,False),(-1,False)])
def test_balance_freshness_boundaries(data,age,available):
    db,users=data;seed(db,users[0])
    db.query(Account).one().balance_as_of=NOW-timedelta(days=age);db.commit()
    profile=h.gather_profile(db,users[0].id,as_of=DAY)
    assert components(profile)["liquidity"].data_available is available


def test_partial_trusted_cash_is_not_a_complete_position(data):
    db,users=data;seed(db,users[0])
    db.add(Account(user_id=users[0].id,name="Unknown account",currency="BDT"));db.commit()
    c=components(h.gather_profile(db,users[0].id,as_of=DAY))
    assert c["liquidity"].score is None
    assert c["obligation_pressure"].score is None
    assert c["account_reliability"].score is None


def test_overdue_pressure_counts_dates_not_alerts(data):
    db,users=data;seed(db,users[0]);uid=users[0].id
    for back in [1,1,2]:
        db.add(ScheduledCashflowItem(user_id=uid,title="Late",kind="expense",amount=D("100"),due_date=DAY-timedelta(days=back),status="scheduled"))
    db.commit();c=components(h.gather_profile(db,uid,as_of=DAY))
    assert c["financial_stress"].score==40
    assert c["financial_stress"].evidence[0].value==2
    assert c["obligation_pressure"].evidence[0].value==D("1000")


def test_zero_denominator_stays_unknown(data):
    db,users=data;seed(db,users[0],cash="0")
    schedule=db.query(ScheduledCashflowItem).one();schedule.status="paid";db.commit()
    c=components(h.gather_profile(db,users[0].id,as_of=DAY))
    assert c["obligation_pressure"].score is None


def test_account_reconciliation_query_count_does_not_grow(data):
    from sqlalchemy import event
    db,users=data;seed(db,users[0]);queries=[]
    def before(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith("SELECT"):queries.append(statement)
    engine=db.get_bind();event.listen(engine,"before_cursor_execute",before)
    try:
        h.gather_profile(db,users[0].id,as_of=DAY);first=len(queries)
        for n in range(20):db.add(Account(user_id=users[0].id,name=f"Cash {n}",currency="BDT",opening_balance=D("100"),opening_balance_date=DAY,current_balance=D("100"),balance_as_of=NOW))
        db.commit();queries.clear()
        h.gather_profile(db,users[0].id,as_of=DAY)
        assert len(queries)==first
    finally:event.remove(engine,"before_cursor_execute",before)
