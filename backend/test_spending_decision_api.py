
"""Integration tests for the purchase-affordability API."""

from uuid import uuid4
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models.user import User

client = TestClient(app)


def create_user(db) -> User:
    user = User(
        email=f"spending-decision-{uuid4()}@example.com",
        hashed_password="test-password",
        full_name="Spending Decision Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.email,
            "user_id": user.id,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def cleanup_user(db, user: User | None) -> None:
    if user is not None:
        db.delete(user)
        db.commit()


def test_spending_decision_requires_authentication():
    response = client.post(
        "/finance/spending-decision",
        json={
            "purchase_amount": "2000.00",
            "starting_balance": "10000.00",
            "safety_buffer": "3000.00",
        },
    )

    assert response.status_code == 401


def test_spending_decision_returns_deterministic_assessment():
    db = SessionLocal()
    user = None

    try:
        user = create_user(db)

        response = client.post(
            "/finance/spending-decision",
            json={
                "purchase_amount": "2000.00",
                "starting_balance": "10000.00",
                "safety_buffer": "3000.00",
            },
            headers=auth_headers(user),
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "safe"
        assert data["currency"] == "BDT"
        assert Decimal(data["purchase_amount"]) == Decimal("2000.00")
        assert Decimal(data["starting_balance"]) == Decimal("10000.00")
        assert Decimal(data["safety_buffer"]) == Decimal("3000.00")
        assert Decimal(data["remaining_after_purchase"]) == Decimal("8000.00")
        assert (
            Decimal(data["amount_available_above_buffer"])
            == Decimal("7000.00")
        )
        assert data["can_afford_without_breaching_buffer"] is True
        assert data["explanation_code"] == "purchase_fits_buffer"
        assert data["assumptions"]
        assert data["warnings"]

    finally:
        cleanup_user(db, user)
        db.close()


def test_spending_decision_rejects_invalid_amount():
    db = SessionLocal()
    user = None

    try:
        user = create_user(db)

        response = client.post(
            "/finance/spending-decision",
            json={
                "purchase_amount": "0",
                "starting_balance": "10000.00",
                "safety_buffer": "3000.00",
            },
            headers=auth_headers(user),
        )

        assert response.status_code == 422

    finally:
        cleanup_user(db, user)
        db.close()


def test_spending_decision_rejects_unexpected_fields():
    db = SessionLocal()
    user = None

    try:
        user = create_user(db)

        response = client.post(
            "/finance/spending-decision",
            json={
                "purchase_amount": "2000.00",
                "starting_balance": "10000.00",
                "safety_buffer": "3000.00",
                "future_salary": "50000.00",
            },
            headers=auth_headers(user),
        )

        assert response.status_code == 422

    finally:
        cleanup_user(db, user)
        db.close()
