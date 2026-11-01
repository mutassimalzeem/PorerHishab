"""Real PostgreSQL migrations, row locking, owner scope and transactional rollback."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from test_goal_planning_postgres import postgres, setup
from app.core.database import engine
from app.main import app
from app.models.scenarios import ScenarioRun, ScenarioComparison
from app.services.finance import scenarios as service
pytestmark=pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Real PostgreSQL required")

def test_q_migration_round_trip(postgres):
    config=Config("alembic.ini")
    assert "scenario_runs" in inspect(postgres).get_table_names()
    command.downgrade(config,"f15p00000001")
    assert "scenario_runs" not in inspect(postgres).get_table_names()
    command.upgrade(config,"head")
    assert "uq_scenario_run_request" in {c["name"] for c in inspect(postgres).get_unique_constraints("scenario_runs")}

def test_concurrent_simulations_and_rollback(postgres,monkeypatch):
    users,goals,headers=setup(postgres)
    with TestClient(app) as client:
        scenario=client.post("/finance/scenarios",headers=headers[0],json={"name":"Concurrency"}).json()
    def simulate(_):
        with TestClient(app) as client:
            response=client.post(f"/finance/scenarios/{scenario['id']}/simulate",headers=headers[0],json={"idempotency_key":"same-simulation-key","schedules_confirmed":True})
            assert response.status_code==200,response.text
            return response.json()
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(simulate,range(6)))
    assert all(r==results[0] for r in results)
    with Session(postgres) as db:
        assert db.query(ScenarioRun).filter_by(user_id=users[0],scenario_id=scenario["id"]).count()==1
        assert db.query(ScenarioComparison).filter_by(run_id=results[0]["run_id"]).count()==len(results[0]["comparisons"])
    with TestClient(app) as client:
        assert client.post(f"/finance/scenarios/{scenario['id']}/simulate",headers=headers[1],json={"idempotency_key":"foreign-simulation"}).status_code==404
    original=service.ScenarioComparison
    def fail(*args,**kwargs):raise RuntimeError("Injected comparison write failure")
    monkeypatch.setattr(service,"ScenarioComparison",fail)
    with TestClient(app,raise_server_exceptions=False) as client:
        assert client.post(f"/finance/scenarios/{scenario['id']}/simulate",headers=headers[0],json={"idempotency_key":"rollback-simulation"}).status_code==500
    monkeypatch.setattr(service,"ScenarioComparison",original)
    with Session(postgres) as db:
        assert db.query(ScenarioRun).filter_by(user_id=users[0],idempotency_key="rollback-simulation").count()==0
