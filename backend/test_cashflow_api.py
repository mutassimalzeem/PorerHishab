from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.main import app
from app.models.transactions import Transaction
from app.models.user import User
from app.core.database import SessionLocal


client = TestClient(app)


def create_user(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password="test-password",
        full_name="Cashflow API Test User",
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


def create_transaction(
    db,
    user: User,
    *,
    trx_id: str | None = None,
    transaction_date: date,
    description: str,
    merchant: str,
    amount: Decimal,
    category: str,
) -> Transaction:
    transaction = Transaction(
        user_id=user.id,
        trx_id=trx_id or str(uuid4()),
        date=transaction_date,
        description=description,
        merchant=merchant,
        amount=amount,
        category=category,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def cleanup_user(db, user: User | None) -> None:
    if user is not None:
        db.delete(user)
        db.commit()


def test_cashflow_endpoint_requires_authentication():
    response = client.get(
        "/forecast/cashflow",
        params={
            "starting_balance": "50000",
            "months_ahead": 3,
        },
    )

    assert response.status_code == 401


def test_cashflow_endpoint_validates_starting_balance():
    db = SessionLocal()
    user = None

    try:
        user = create_user(
            db,
            f"cashflow-validation-{uuid4()}@example.com",
        )

        response = client.get(
            "/forecast/cashflow",
            params={
                "starting_balance": "0",
                "months_ahead": 3,
            },
            headers=auth_headers(user),
        )

        assert response.status_code == 422
    finally:
        cleanup_user(db, user)
        db.close()


def test_cashflow_endpoint_validates_month_horizon():
    db = SessionLocal()
    user = None

    try:
        user = create_user(
            db,
            f"cashflow-horizon-{uuid4()}@example.com",
        )

        too_many_months = client.get("/forecast/cashflow",
            params={
                "starting_balance": "50000",
                "months_ahead": 13,
            },
            headers=auth_headers(user),
        )

        assert too_many_months.status_code == 422

        zero_months = client.get(
            "/forecast/cashflow",
            params={
                "starting_balance": "50000",
                "months_ahead": 0,
            },
            headers=auth_headers(user),
        )

        assert zero_months.status_code == 422
    finally:
        cleanup_user(db, user)
        db.close()


def test_cashflow_endpoint_returns_forecast_for_authenticated_user(monkeypatch):
    monkeypatch.setattr(
        "app.services.forecasting.cashflow._forecast_date",
        lambda: date(2026, 10, 25),
    )
    db = SessionLocal()
    user = None

    try:
        user = create_user(
            db,
            f"cashflow-success-{uuid4()}@example.com",
        )

        create_transaction(
            db,
            user,
            transaction_date=date(2026, 9, 1),
            description="Salary",
            merchant="Employer",
            amount=Decimal("50000.00"),
            category="Income",
        )

        create_transaction(
            db,
            user,
            transaction_date=date(2026, 9, 5),
            description="Rent",
            merchant="Landlord",
            amount=Decimal("-20000.00"),
            category="Housing",
        )

        create_transaction(
            db,
            user,
            transaction_date=date(2026, 10, 1),
            description="Salary",
            merchant="Employer",
            amount=Decimal("50000.00"),
            category="Income",
        )

        create_transaction(
            db,
            user,
            transaction_date=date(2026, 10, 5),
            description="Rent",
            merchant="Landlord",
            amount=Decimal("-20000.00"),
            category="Housing",
        )

        response = client.get(
            "/forecast/cashflow",
            params={
                "starting_balance": "100000.00",
                "months_ahead": 2,
            },
            headers=auth_headers(user),
        )

        assert response.status_code == 200

        data = response.json()

        assert Decimal(str(data["starting_balance"])) == Decimal("100000.00")
        assert data["historical_months_count"] == 2
        assert data["months_with_activity"] == 2

        assert Decimal(str(data["average_monthly_income"])) == Decimal(
            "50000.00"
        )
        assert Decimal(str(data["average_monthly_expenses"])) == Decimal(
            "20000.00"
        )
        assert Decimal(str(data["average_monthly_net"])) == Decimal(
            "30000.00"
        )

        assert data["months_ahead"] == 2
        assert data["forecast_anchor_date"] == "2026-10-25"
        assert data["forecast_start_month"] == "2026-11"
        assert len(data["projected_months"]) == 2

        assert data["projected_months"][0]["month"] == "2026-11"
        assert Decimal(
            str(data["projected_months"][0]["projected_balance"])
        ) == Decimal("130000.00")

        assert data["status"] == "healthy"
        assert data["cash_depletion_date"] is None

    finally:
        cleanup_user(db, user)
        db.close()


def test_cashflow_endpoint_isolates_users():
    db = SessionLocal()
    user_a = None
    user_b = None

    try:
        user_a = create_user(
            db,
            f"cashflow-owner-{uuid4()}@example.com",
        )
        user_b = create_user(
            db,
            f"cashflow-other-{uuid4()}@example.com",
        )

        create_transaction(
            db,
            user_a,
            transaction_date=date(2026, 10, 1),
            description="Salary",
            merchant="Employer",
            amount=Decimal("100000.00"),
            category="Income",
        )

        create_transaction(
            db,
            user_a,
            transaction_date=date(2026, 10, 5),
            description="Rent",
            merchant="Landlord",
            amount=Decimal("-30000.00"),
            category="Housing",
        )

        response = client.get(
            "/forecast/cashflow",
            params={
                "starting_balance": "50000.00",
                "months_ahead": 2,
            },
            headers=auth_headers(user_b),
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "insufficient_data"
        assert data["historical_months_count"] == 0
        assert data["months_with_activity"] == 0
        assert data["projected_months"] == []

    finally:
        cleanup_user(db, user_b)
        cleanup_user(db, user_a)
        db.close()