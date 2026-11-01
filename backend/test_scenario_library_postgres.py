"""Real PostgreSQL library metadata migration, locking, constraints and rollback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect,text
from sqlalchemy.orm import Session
from test_goal_planning_postgres import postgres,setup
from app.core.database import engine
from app.main import app
from app.models.scenarios import Scenario,ScenarioRun
from app.services.finance import scenario_library as service
pytestmark=pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real PostgreSQL required")


def test_r_migration_preserves_q_history_and_backfills_only_known_time(postgres):
    users,goals,headers=setup(postgres)
    config=Config("alembic.ini");command.downgrade(config,"f15q00000001")
    with postgres.begin() as c:
        c.execute(text("INSERT INTO financial_scenarios (user_id,name,description,created_at,status,calculation_version,revision) VALUES (:uid,'Legacy saved','',:stamp,'saved','ai-15q-v1',1),(:uid,'Legacy archive','',:stamp,'archived','ai-15q-v1',1)"),{"uid":users[0],"stamp":datetime(2026,1,1,tzinfo=timezone.utc)})
    command.upgrade(config,"head")
    with Session(postgres) as db:
        rows=db.query(Scenario).filter_by(user_id=users[0]).all()
        assert len(rows)==2 and all(r.updated_at==r.created_at and r.saved_at is None and r.archived_at is None for r in rows)
    assert "source_scenario_id" in {r["name"] for r in inspect(postgres).get_columns("financial_scenarios")}
    command.downgrade(config,"f15q00000001")
    assert "source_scenario_id" not in {r["name"] for r in inspect(postgres).get_columns("financial_scenarios")}
    with postgres.connect() as c:assert c.execute(text("SELECT count(*) FROM financial_scenarios WHERE user_id=:uid"),{"uid":users[0]}).scalar_one()==2
    command.upgrade(config,"head")


def test_concurrent_duplicate_archive_restore_and_metadata(postgres):
    users,goals,headers=setup(postgres)
    with TestClient(app) as c:
        source=c.post("/finance/scenarios",headers=headers[0],json={"name":"Rent"}).json()
        assert c.post(f"/finance/scenarios/{source['id']}/save",headers=headers[0]).status_code==200
    def duplicate(_):
        with TestClient(app) as c:
            r=c.post(f"/finance/scenarios/{source['id']}/duplicate",headers=headers[0]);assert r.status_code==200,r.text
            return r.json()
    with ThreadPoolExecutor(max_workers=6) as pool:copies=list(pool.map(duplicate,range(6)))
    assert len({r["id"] for r in copies})==6 and len({r["name"] for r in copies})==6
    assert {r["name"] for r in copies}=={"Rent (Copy)",*[f"Rent (Copy {i})" for i in range(2,7)]}
    def lifecycle(action):
        with TestClient(app) as c:
            r=c.post(f"/finance/scenarios/{source['id']}/{action}",headers=headers[0]);assert r.status_code==200,r.text
            return r.json()
    for action in ["archive","restore","save"]:
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lifecycle,[action]*6))
        assert len({r["updated_at"] for r in results})==1
    def metadata(pair):
        field,value=pair
        with TestClient(app) as c:
            r=c.patch(f"/finance/scenarios/{source['id']}",headers=headers[0],json={field:value});assert r.status_code==200,r.text
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(metadata,[("name","Renamed"),("description","Description")]))
    with Session(postgres) as db:
        row=db.query(Scenario).filter_by(id=source["id"],user_id=users[0]).one()
        assert row.name=="Renamed" and row.description=="Description" and row.revision==1
        assert db.query(ScenarioRun).filter_by(user_id=users[0]).count()==0


def test_duplicate_write_failure_rolls_back_all_metadata(postgres,monkeypatch):
    users,goals,headers=setup(postgres)
    with TestClient(app) as c:source=c.post("/finance/scenarios",headers=headers[0],json={"name":"Rent"}).json()
    def fail(*args,**kwargs):raise RuntimeError("Injected failure after duplicate insert")
    monkeypatch.setattr(service.simulator,"changes_for",fail)
    with TestClient(app,raise_server_exceptions=False) as c:
        assert c.post(f"/finance/scenarios/{source['id']}/duplicate",headers=headers[0]).status_code==500
    with Session(postgres) as db:assert db.query(Scenario).filter_by(user_id=users[0]).count()==1
