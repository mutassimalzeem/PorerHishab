"""Integration coverage for user-owned planned cashflow."""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.transactions import Transaction
from app.models.user import User

client = TestClient(app)
URL = "/finance/scheduled-cashflow"
PAYLOAD = {"title": " Rent ", "kind": "expense", "amount": "1250.50", "due_date": "2026-11-01", "category": " Housing ", "notes": "Planned"}


@pytest.fixture
def users():
    db = SessionLocal()
    people = []
    try:
        for _ in range(2):
            user = User(email=f"scheduled-{uuid4().hex}@example.com", hashed_password="test-password")
            db.add(user)
            db.commit()
            db.refresh(user)
            people.append(user)
        headers = [{"Authorization": "Bearer " + create_access_token({"sub": u.email, "user_id": u.id})} for u in people]
        yield db, people, headers
    finally:
        db.rollback()
        for user in people:
            db.query(ScheduledCashflowItem).filter_by(user_id=user.id).delete()
            db.delete(user)
        db.commit()
        db.close()


def create(headers, **changes):
    response = client.post(URL, headers=headers, json={**PAYLOAD, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_authentication_required():
    for method, url in [("post", URL), ("get", URL), ("get", URL + "/1"), ("patch", URL + "/1"), ("delete", URL + "/1")]:
        assert client.request(method, url, json=PAYLOAD).status_code == 401


def test_create_read_update_delete(users):
    _, _, headers = users
    item = create(headers[0])
    assert item["title"] == "Rent"
    assert item["category"] == "Housing"
    assert item["status"] == "scheduled"
    assert Decimal(item["amount"]) == Decimal("1250.50")
    url = f"{URL}/{item['id']}"
    assert client.get(url, headers=headers[0]).json() == item
    response = client.patch(url, headers=headers[0], json={"title": " New rent ", "category": None, "notes": None})
    assert response.status_code == 200
    assert response.json()["title"] == "New rent"
    assert response.json()["category"] is None
    assert response.json()["notes"] is None
    response = client.delete(url, headers=headers[0])
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(url, headers=headers[0]).status_code == 404


def test_user_isolation_and_missing_items(users):
    _, _, headers = users
    item = create(headers[0])
    assert client.get(URL, headers=headers[1]).json()["total"] == 0
    for item_id in (item["id"], 2147483647):
        url = f"{URL}/{item_id}"
        for method, payload in [("get", None), ("patch", {"title": "Stolen"}), ("delete", None)]:
            assert client.request(method, url, headers=headers[1], json=payload).status_code == 404
    assert client.get(f"{URL}/{item['id']}", headers=headers[0]).json()["title"] == "Rent"


def test_filters_and_pagination(users):
    _, _, headers = users
    first = create(headers[0])
    create(headers[0], kind="income", due_date="2026-12-01")
    last = create(headers[0], due_date="2026-11-02")
    client.patch(f"{URL}/{last['id']}", headers=headers[0], json={"status": "paid"})
    create(headers[1])
    result = client.get(URL, headers=headers[0], params={"kind": "expense", "status": "scheduled", "due_date_from": "2026-11-01", "due_date_to": "2026-11-01"}).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == first["id"]
    result = client.get(URL, headers=headers[0], params={"limit": 1, "offset": 1}).json()
    assert result["total"] == 3
    assert result["items"][0]["id"] == last["id"]
    for params in ({"kind": "other"}, {"status": "other"}, {"limit": 0}, {"offset": -1}, {"due_date_from": "2026-12-01", "due_date_to": "2026-11-01"}):
        assert client.get(URL, headers=headers[0], params=params).status_code == 422


def test_create_validation(users):
    _, _, headers = users
    for changes in ({"amount": "0"}, {"amount": "-1"}, {"amount": "1.001"}, {"amount": "1000000000000.00"}, {"amount": "NaN"}, {"title": "   "}, {"title": "x" * 161}, {"kind": "other"}, {"due_date": "invalid"}, {"status": "paid"}, {"user_id": 1}, {"category": "x" * 101}, {"notes": "x" * 4001}):
        assert client.post(URL, headers=headers[0], json={**PAYLOAD, **changes}).status_code == 422
    assert client.get(URL, headers=headers[0]).json()["total"] == 0


def test_patch_validation(users):
    _, _, headers = users
    item = create(headers[0])
    url = f"{URL}/{item['id']}"
    for field in ("title", "kind", "amount", "due_date", "status"):
        assert client.patch(url, headers=headers[0], json={field: None}).status_code == 422
    for changes in ({"amount": "1.001"}, {"amount": 0}, {"title": " "}, {"status": "other"}, {"user_id": 1}):
        assert client.patch(url, headers=headers[0], json=changes).status_code == 422
    assert client.patch(url, headers=headers[0], json={}).status_code == 200
    assert client.get(url, headers=headers[0]).json()["title"] == "Rent"


def test_terminal_statuses_do_not_create_transactions(users):
    db, people, headers = users
    for terminal in ("paid", "cancelled"):
        item = create(headers[0], kind="income")
        url = f"{URL}/{item['id']}"
        transactions_before = (
            db.query(func.count(Transaction.id))
            .filter(Transaction.user_id == people[0].id)
            .scalar()
        )
        assert client.patch(url, headers=headers[0], json={"status": terminal}).status_code == 200
        db.expire_all()
        transactions_after = (
            db.query(func.count(Transaction.id))
            .filter(Transaction.user_id == people[0].id)
            .scalar()
        )
        assert transactions_after == transactions_before
        assert client.patch(url, headers=headers[0], json={"status": terminal, "notes": "Corrected"}).status_code == 200
        for status in {"scheduled", "paid", "cancelled"} - {terminal}:
            assert client.patch(url, headers=headers[0], json={"status": status, "title": "Invalid change"}).status_code == 409
        assert client.get(url, headers=headers[0]).json()["title"] == "Rent"
