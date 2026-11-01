"""Real PostgreSQL migration, authenticated concurrency, uniqueness and rollback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timezone
from decimal import Decimal as D
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,inspect,text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import engine,get_db
from app.api.auth import create_access_token
from app.main import app
from app.models import User,Account,Transaction,SavingsGoal
from app.models.goal_planning import GoalPlanRecord,GoalProgressEvent,GoalMilestone
from app.services.finance import goal_planning as service

pytestmark=pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real PostgreSQL required")

@pytest.fixture
def postgres(monkeypatch):
    schema="goal_planning_test_"+uuid4().hex
    assert schema.isidentifier() and schema.startswith("goal_planning_test_")
    with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    url=engine.url.set(query={**engine.url.query,"options":f"-csearch_path={schema}"})
    isolated=create_engine(url)
    monkeypatch.setattr(settings,"DATABASE_URL",url.render_as_string(hide_password=False))
    config=Config("alembic.ini")
    try:
        command.upgrade(config,"f15o00000001")
        with isolated.begin() as c:
            c.execute(text("INSERT INTO users (email,hashed_password,created_at,updated_at) VALUES ('preserve@test.local','x',now(),now())"))
            c.execute(text("INSERT INTO savings_goals (user_id,name,target_amount,current_saved,target_date,status,created_at,updated_at) SELECT id,'Legacy',1000,100,'2099-01-01','active',now(),now() FROM users"))
        command.upgrade(config,"head")
        assert "goal_plans" in inspect(isolated).get_table_names()
        with isolated.connect() as c:assert c.execute(text("SELECT current_saved FROM savings_goals WHERE name='Legacy'")).scalar_one()==100
        command.downgrade(config,"f15o00000001")
        assert "goal_plans" not in inspect(isolated).get_table_names()
        command.upgrade(config,"head")
        def dependency():
            with Session(isolated) as db:yield db
        app.dependency_overrides[get_db]=dependency
        yield isolated
    finally:
        app.dependency_overrides.clear();isolated.dispose()
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def setup(isolated):
    day=service.today_dhaka()
    from app.services.intelligence.periods import month_shift
    with Session(isolated,expire_on_commit=False) as db:
        users=[User(email=f"plan-{i}-{uuid4()}@test.local",hashed_password="x") for i in range(2)]
        db.add_all(users);db.flush();goals=[]
        for u in users:
            db.add(Account(user_id=u.id,name="Cash",currency="BDT",opening_balance=D("100000"),opening_balance_date=day,current_balance=D("100000"),balance_as_of=datetime.now(timezone.utc)))
            for back in [3,2,1]:
                d=month_shift(day,-back)
                db.add(Transaction(user_id=u.id,date=d,amount=D("30000")))
                db.add(Transaction(user_id=u.id,date=d,amount=D("-5000")))
            g=SavingsGoal(user_id=u.id,name="Laptop",target_amount=D("10000"),current_saved=D("0"),target_date=month_shift(day,5),priority=3)
            db.add(g);goals.append(g)
        db.commit()
        return [u.id for u in users],[g.id for g in goals],[{"Authorization":"Bearer "+create_access_token({"sub":u.email,"user_id":u.id})} for u in users]


def test_authenticated_concurrent_plans_and_contributions(postgres):
    users,goals,headers=setup(postgres)
    def plan(i):
        with TestClient(app) as c:
            r=c.post(f"/finance/goals/{goals[i]}/plan",headers=headers[i],json={"idempotency_key":"same-plan-request","schedules_confirmed":True})
            assert r.status_code==200,r.text
            return i,r.json()["id"]
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(plan,[0,0,0,1,1,1]))
    assert len({v for i,v in results if i==0})==1
    assert len({v for i,v in results if i==1})==1
    def contribute(i):
        with TestClient(app) as c:
            r=c.post(f"/finance/goals/{goals[i]}/contributions",headers=headers[i],json={"idempotency_key":"same-contribution","amount":"2000"})
            assert r.status_code==200,r.text
            return r.json()
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(contribute,[0,0,0,1,1,1]))
    with Session(postgres) as db:
        for uid,gid in zip(users,goals):
            assert db.query(SavingsGoal).filter_by(user_id=uid,id=gid).one().current_saved==2000
            assert db.query(GoalPlanRecord).filter_by(user_id=uid,goal_id=gid).count()==1
            assert db.query(GoalProgressEvent).filter_by(user_id=uid,goal_id=gid,kind="contribution_recorded").count()==1
            assert db.query(GoalProgressEvent).filter_by(user_id=uid,goal_id=gid,kind="milestone_achieved").count()==1
    with TestClient(app) as c:
        assert c.post(f"/finance/goals/{goals[0]}/contributions",headers=headers[1],json={"idempotency_key":"foreign-request","amount":"1"}).status_code==404


def test_atomic_rollback_and_constraint(postgres,monkeypatch):
    users,goals,headers=setup(postgres)
    with TestClient(app,raise_server_exceptions=False) as c:
        assert c.post(f"/finance/goals/{goals[0]}/plan",headers=headers[0],json={"idempotency_key":"create-request","schedules_confirmed":True}).status_code==200
        with Session(postgres) as db:original=db.query(SavingsGoal).filter_by(user_id=users[0],id=goals[0]).one().target_date
        far=service.month_end(service.month_shift(service.today_dhaka(),119))
        r=c.post(f"/finance/goals/{goals[0]}/replan",headers=headers[0],json={"idempotency_key":"rollback-replan","schedules_confirmed":True,"target_date":far.isoformat(),"cadence":"weekly"})
        assert r.status_code==422
        with Session(postgres) as db:
            assert db.query(SavingsGoal).filter_by(user_id=users[0],id=goals[0]).one().target_date==original
            assert db.query(GoalPlanRecord).filter_by(user_id=users[0],goal_id=goals[0]).count()==1
        def fail(*args,**kwargs):raise RuntimeError("Injected failure after contribution write")
        monkeypatch.setattr(service,"sync_milestones",fail)
        r=c.post(f"/finance/goals/{goals[0]}/contributions",headers=headers[0],json={"idempotency_key":"rollback-contribution","amount":"100"})
        assert r.status_code==500
        with Session(postgres) as db:
            assert db.query(SavingsGoal).filter_by(user_id=users[0],id=goals[0]).one().current_saved==0
            assert db.query(GoalProgressEvent).filter_by(user_id=users[0],goal_id=goals[0],kind="contribution_recorded").count()==0
        assert "uq_goal_event_request" in {v["name"] for v in inspect(postgres).get_unique_constraints("goal_progress_events")}
