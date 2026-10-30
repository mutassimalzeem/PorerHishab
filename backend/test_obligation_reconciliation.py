"""Real PostgreSQL integration, concurrent writes and migration roundtrip."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.database import engine, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import User, ScheduledCashflowItem, Transaction
from app.models.obligation_allocation import ObligationAllocation
from app.schemas.obligation_reconciliation import ObligationReconciliation
from app.services.finance.obligation_reconciliation import confirm, reconcile, revoke

DUE = date(2026, 11, 1)

@pytest.fixture(scope="module")
def store():
    schema = "obligation_test_" + uuid4().hex
    assert schema.isidentifier() and schema.startswith("obligation_test_")
    with engine.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.set(query={**engine.url.query, "options": f"-csearch_path={schema}"})
    isolated = create_engine(url)
    old = settings.DATABASE_URL
    settings.DATABASE_URL = url.render_as_string(hide_password=False)
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield sessionmaker(bind=isolated, expire_on_commit=False), isolated
    finally:
        settings.DATABASE_URL = old
        isolated.dispose()
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))

@pytest.fixture
def data(store):
    factory, _ = store
    with factory() as db:
        users = [User(email=uuid4().hex + "@test.local", hashed_password="test") for _ in range(2)]
        db.add_all(users); db.flush()
        item = ScheduledCashflowItem(user_id=users[0].id, title="Rent", kind="expense", amount=Decimal("100"), due_date=DUE, category="Housing")
        db.add(item); db.commit()
        yield db, users, item

def transaction(db, user, amount="-100", **kw):
    row = Transaction(user_id=user.id, amount=Decimal(amount), date=kw.pop("date", DUE), **kw)
    db.add(row); db.commit()
    return row

def test_suggestions_are_read_only_and_explainable(data):
    db, users, item = data
    tx = transaction(db, users[0], merchant="Rent", category="Housing")
    result = reconcile(db, users[0].id, item.id, as_of=DUE)
    assert result == reconcile(db, users[0].id, item.id, as_of=DUE)
    assert result["status"] == "review_required"
    assert result["candidates"][0]["transaction_id"] == tx.id
    assert result["candidates"][0]["confidence"] == "medium"
    assert result["candidates"][0]["category_match"]
    assert result["allocations"] == []
    assert item.status == "scheduled"
    ObligationReconciliation.model_validate(result)

def test_partial_multiple_full_and_idempotency(data):
    db, users, item = data
    first = transaction(db, users[0], "-40")
    second = transaction(db, users[0], "-60")
    result = confirm(db, users[0].id, item.id, first.id)
    assert result["allocated_amount"] == Decimal("40")
    assert result["remaining_amount"] == Decimal("60")
    assert item.amount == Decimal("100")
    assert result["status"] == "partial"
    confirm(db, users[0].id, item.id, first.id)
    assert len(reconcile(db, users[0].id, item.id)["allocations"]) == 1
    result = confirm(db, users[0].id, item.id, second.id)
    assert result["remaining_amount"] == 0
    assert item.status == "scheduled"
    confirm(db, users[0].id, item.id, second.id, True)
    assert item.status == "paid"
    result = revoke(db, users[0].id, item.id, first.id)
    assert result["remaining_amount"] == 40
    assert item.status == "scheduled"
    assert result["allocations"][0].revoked_at is not None
    revoke(db, users[0].id, item.id, first.id)
    confirm(db, users[0].id, item.id, first.id, True)
    assert item.status == "paid"
    assert len(reconcile(db, users[0].id, item.id)["allocations"]) == 3

def test_direction_overallocation_and_full_validation(data):
    db, users, item = data
    for amount, full in [("100", False), ("-101", False), ("0", False), ("-40", True)]:
        tx = transaction(db, users[0], amount)
        with pytest.raises(HTTPException) as error:
            confirm(db, users[0].id, item.id, tx.id, full)
        assert error.value.status_code == 422
        db.rollback()

def test_candidates_boundaries_ambiguity_and_timing(data):
    db, users, item = data
    tx = transaction(db, users[0], "-101", date=DUE + timedelta(days=7))
    transaction(db, users[0], "-40", date=DUE - timedelta(days=7))
    transaction(db, users[0], "-100", date=DUE + timedelta(days=8))
    transaction(db, users[0], "100")
    transaction(db, users[1], "-100")
    result = reconcile(db, users[0].id, item.id, amount_tolerance=Decimal("1"), as_of=DUE)
    assert len(result["candidates"]) == 2
    assert result["ambiguous"]
    assert any(c["transaction_id"] == tx.id and c["amount_signal"] == "within_tolerance" for c in result["candidates"])
    assert len(reconcile(db, users[0].id, item.id, amount_tolerance=Decimal("0.99"))["candidates"]) == 1
    assert not reconcile(db, users[0].id, item.id, date_tolerance_days=6)["candidates"]
    assert reconcile(db, users[0].id, item.id, as_of=DUE - timedelta(days=1), date_tolerance_days=0)["status"] == "not_due"
    assert reconcile(db, users[0].id, item.id, as_of=DUE + timedelta(days=1), date_tolerance_days=0)["status"] == "overdue"
    assert reconcile(db, users[0].id, item.id, as_of=DUE, date_tolerance_days=0)["status"] == "unmatched"
    item.status = "cancelled"; db.commit()
    assert not reconcile(db, users[0].id, item.id)["candidates"]
    with pytest.raises(HTTPException): confirm(db, users[0].id, item.id, tx.id)
    db.rollback()

def test_insufficient_data_and_income(data):
    db, users, item = data
    assert reconcile(db, users[0].id, item.id)["status"] == "insufficient_data"
    item.kind = "income"; db.commit()
    tx = transaction(db, users[0], "100")
    assert confirm(db, users[0].id, item.id, tx.id, True)["status"] == "paid"

def test_one_transaction_cannot_pay_two_obligations(data):
    db, users, item = data
    other = ScheduledCashflowItem(user_id=users[0].id, title="Other", kind="expense", amount=100, due_date=DUE)
    db.add(other); db.commit()
    tx = transaction(db, users[0])
    confirm(db, users[0].id, item.id, tx.id)
    assert not reconcile(db, users[0].id, other.id)["candidates"]
    with pytest.raises(HTTPException) as error: confirm(db, users[0].id, other.id, tx.id)
    assert error.value.status_code == 409
    db.rollback()

def test_api_scoping_and_history_protection(data, store):
    db, users, item = data
    factory, _ = store
    tx = transaction(db, users[0])
    foreign = transaction(db, users[1])
    def get_test_db():
        with factory() as session: yield session
    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: users[1]
    base = f"/finance/scheduled-cashflow/{item.id}"
    try:
        with TestClient(app) as client:
            assert client.get(base + "/matches").status_code == 404
            assert client.post(base + f"/matches/{tx.id}/confirm", json={}).status_code == 404
            assert client.delete(base + f"/matches/{tx.id}").status_code == 404
            page = client.get("/finance/scheduled-cashflow/reconciliation").json()
            assert page["total"] == 0
            app.dependency_overrides[get_current_user] = lambda: users[0]
            assert client.post(base + f"/matches/{foreign.id}/confirm", json={}).status_code == 404
            assert client.get(base + "/matches?date_tolerance_days=-1").status_code == 422
            assert client.post(base + f"/matches/{tx.id}/confirm", json={"confirm_full_settlement": True}).status_code == 200
            assert client.patch(base, json={"amount": "200"}).status_code == 409
            assert client.delete(base).status_code == 409
            assert client.delete(base + f"/matches/{tx.id}").status_code == 200
            assert client.delete(base + f"/matches/{tx.id}").status_code == 200
            app.dependency_overrides.pop(get_current_user)
            assert client.get(base + "/matches").status_code == 401
    finally:
        app.dependency_overrides.clear()

def test_concurrent_confirmations(data, store):
    db, users, item = data
    factory, _ = store
    txs = [transaction(db, users[0], "-60") for _ in range(2)]
    barrier = Barrier(2)
    def run(tx_id):
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                confirm(session, users[0].id, item.id, tx_id)
                return 200
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, [t.id for t in txs]))
    assert sorted(results) == [200, 422]
    db.expire_all()
    assert reconcile(db, users[0].id, item.id)["allocated_amount"] == 60

def test_concurrent_same_transaction_is_idempotent(data, store):
    db, users, item = data
    factory, _ = store
    tx = transaction(db, users[0])
    barrier = Barrier(2)
    def run(_):
        with factory() as session:
            barrier.wait(timeout=10)
            return confirm(session, users[0].id, item.id, tx.id)["allocated_amount"]
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(run, range(2))) == [Decimal("100"), Decimal("100")]
    db.expire_all()
    assert len(reconcile(db, users[0].id, item.id)["allocations"]) == 1

def test_partial_payment_reduces_scenario_reserve(data):
    from app.services.intelligence.facts import scheduled_totals
    db, users, item = data
    tx = transaction(db, users[0], "-40")
    confirm(db, users[0].id, item.id, tx.id)
    assert scheduled_totals(db, users[0].id, DUE, DUE) == (Decimal("60"), Decimal("0"))
    assert item.amount == 100


def test_database_constraints_enforce_ownership_and_uniqueness(data):
    from sqlalchemy.exc import IntegrityError
    db, users, item = data
    tx = transaction(db, users[0])
    foreign = transaction(db, users[1])
    db.add(ObligationAllocation(user_id=users[0].id, item_id=item.id, transaction_id=foreign.id, amount=100))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    confirm(db, users[0].id, item.id, tx.id)
    db.add(ObligationAllocation(user_id=users[0].id, item_id=item.id, transaction_id=tx.id, amount=100))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()


def test_full_confirmation_retry_rejects_partial_settlement(data):
    db, users, item = data
    tx = transaction(db, users[0], "-40")
    confirm(db, users[0].id, item.id, tx.id)
    with pytest.raises(HTTPException) as error:
        confirm(db, users[0].id, item.id, tx.id, True)
    assert error.value.status_code == 422
    db.rollback()
    assert item.status == "scheduled"


def test_foreign_currency_is_excluded(data):
    from app.models.account import Account
    db, users, item = data
    account = Account(user_id=users[0].id, name="USD", currency="USD")
    db.add(account); db.commit()
    tx = transaction(db, users[0], account_id=account.id)
    assert not reconcile(db, users[0].id, item.id)["candidates"]
    with pytest.raises(HTTPException) as error:
        confirm(db, users[0].id, item.id, tx.id)
    assert error.value.status_code == 422
    db.rollback()


def test_concurrent_transaction_competes_for_two_obligations(data, store):
    db, users, item = data
    factory, _ = store
    other = ScheduledCashflowItem(user_id=users[0].id, title="Other", kind="expense", amount=100, due_date=DUE)
    db.add(other); db.commit()
    tx = transaction(db, users[0])
    barrier = Barrier(2)
    def run(item_id):
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                confirm(session, users[0].id, item_id, tx.id)
                return 200
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, [item.id, other.id])) == [200, 409]


def test_migration_roundtrip(store):
    _, isolated = store
    with isolated.begin() as c:
        # This isolated schema belongs exclusively to this module.
        c.execute(text("DELETE FROM obligation_allocations"))
        before = c.execute(text("SELECT count(*) FROM scheduled_cashflow_items")).scalar_one()
    command.downgrade(Config("alembic.ini"), "8d51117bc8d5")
    assert "obligation_allocations" not in inspect(isolated).get_table_names()
    with isolated.connect() as c:
        assert c.execute(text("SELECT count(*) FROM scheduled_cashflow_items")).scalar_one() == before
    command.upgrade(Config("alembic.ini"), "head")
    assert "obligation_allocations" in inspect(isolated).get_table_names()
