"""Real PostgreSQL migration and simultaneous authenticated evaluations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.core.config import settings
from app.core.database import engine, get_db
from app.api.auth import create_access_token
from app.main import app
from app.models.user import User
from app.models.financial_health import FinancialHealthSnapshot
from app.services.finance.financial_health import current_profile

pytestmark=pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Real PostgreSQL required")

def test_migration_roundtrip_and_concurrent_evaluation(monkeypatch):
    schema="health_test_"+uuid4().hex
    assert schema.isidentifier() and schema.startswith("health_test_")
    with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    url=engine.url.set(query={**engine.url.query,"options":f"-csearch_path={schema}"})
    isolated=create_engine(url)
    monkeypatch.setattr(settings,"DATABASE_URL",url.render_as_string(hide_password=False))
    config=Config("alembic.ini")
    try:
        command.upgrade(config,"f15n00000001")
        command.upgrade(config,"head")
        assert "financial_health_snapshots" in inspect(isolated).get_table_names()
        command.downgrade(config,"f15n00000001")
        assert "financial_health_snapshots" not in inspect(isolated).get_table_names()
        command.upgrade(config,"head")
        with Session(isolated,expire_on_commit=False) as db:
            users=[User(email=f"healthpg{i}@example.com",hashed_password="x") for i in range(2)]
            db.add_all(users);db.commit()
            ids=[u.id for u in users]
            tokens=[create_access_token({"sub":u.email,"user_id":u.id}) for u in users]
        def dependency():
            with Session(isolated) as db:yield db
        app.dependency_overrides[get_db]=dependency
        def request(i):
            with TestClient(app) as client:
                response=client.post("/finance/health/evaluate",headers={"Authorization":"Bearer "+tokens[i]})
                assert response.status_code==200,response.text
                return response.json()
        with ThreadPoolExecutor(max_workers=4) as pool:
            profiles=list(pool.map(request,[0,0,1,1]))
        assert all(p["overall_score"] is None for p in profiles)
        with Session(isolated) as db:
            for uid in ids:
                assert db.query(FinancialHealthSnapshot).filter_by(user_id=uid).count()==1
                assert current_profile(db,uid).overall_score is None
    finally:
        app.dependency_overrides.clear()
        isolated.dispose()
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
