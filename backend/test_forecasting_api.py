"""API-level tests for the forecasting router."""

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models import Transaction, User

_RUN_ID = uuid4().hex
USER_EMAIL = f"api-forecast-{_RUN_ID}@porer-hishab.local"


client = TestClient(app)


def cleanup() -> None:
    db = SessionLocal()
    try:
        db.execute(
            User.__table__.delete().where(
                User.__table__.c.email.in_([USER_EMAIL])
            )
        )
        db.commit()
    finally:
        db.close()


def create_user(email: str) -> User:
    db = SessionLocal()
    try:
        user = User(
            email=email,
            hashed_password="test-password",
            full_name="API Test User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email, "user_id": user.id})
    return {"Authorization": f"Bearer {token}"}


def seed_via_api(headers: dict[str, str]) -> None:
    rows = [
        {
            "date": "2026-10-01",
            "amount": "50000.00",
            "merchant": "Acme",
            "category": "Income",
            "trx_id": f"API-FORE-{_RUN_ID}",
        },
        {
            "date": "2026-10-02",
            "amount": "-20000.00",
            "merchant": "Landlord",
            "category": "Rent",
            "trx_id": f"API-FORE-RENT-{_RUN_ID}",
        },
        {
            "date": "2026-10-03",
            "amount": "-5000.00",
            "merchant": "Grocer",
            "category": "Groceries",
            "trx_id": f"API-FORE-FOOD-{_RUN_ID}",
        },
    ]
    for row in rows:
        response = client.post("/transactions", json=row, headers=headers)
        assert response.status_code == 201, response.text


def test_forecast_budget_endpoint():
    cleanup()
    user = create_user(USER_EMAIL)
    headers = auth_headers(user)

    # Seed transaction data that the forecast endpoint can use.
    seed_via_api(headers)

    response = client.get("/forecast/budget", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "forecast" in data
    assert "historical_average" in data
    assert "recent_average" in data
    assert "confidence" in data
    assert "categories" in data
