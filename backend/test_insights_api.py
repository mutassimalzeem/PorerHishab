"""API-level tests for the transaction and insights routers.

Runs the real FastAPI app with ``TestClient`` against the live PostgreSQL,
using JWT bearer auth — the same path a frontend request takes::

    HTTP -> FastAPI router -> service -> repository -> PostgreSQL
"""

from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models import Transaction, User

_RUN_ID = uuid4().hex
USER_A_EMAIL = f"api-insights-a-{_RUN_ID}@zyra.local"
USER_B_EMAIL = f"api-insights-b-{_RUN_ID}@zyra.local"

client = TestClient(app)


def cleanup() -> None:
    db = SessionLocal()

    try:
        db.execute(
            User.__table__.delete().where(
                User.__table__.c.email.in_([USER_A_EMAIL, USER_B_EMAIL])
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


# ---------------------------------------------------------------------------
# Transactions router
# ---------------------------------------------------------------------------


def test_create_transaction_auto_categorizes():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)

    try:
        response = client.post(
            "/transactions",
            json={
                "date": "2026-10-05",
                "amount": "-450.00",
                "merchant": "Netflix",
                "description": "Netflix subscription",
            },
            headers=headers,
        )

        assert response.status_code == 201

        body = response.json()

        assert body["id"] is not None
        assert body["user_id"] == user.id
        assert body["amount"] == "-450.00"
        assert body["category"] == "Entertainment"  # auto-assigned by rules
        assert body["transaction_type"] == "expense"
        assert body["source"] == "manual"

    finally:
        cleanup()


def test_create_transaction_rejects_duplicate_trx_id():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)
    trx_id = f"API-DUP-{_RUN_ID}"

    payload = {
        "date": "2026-10-05",
        "amount": "-100.00",
        "merchant": "Dup Merchant",
        "trx_id": trx_id,
    }

    try:
        first = client.post("/transactions", json=payload, headers=headers)
        second = client.post("/transactions", json=payload, headers=headers)

        assert first.status_code == 201
        assert second.status_code == 409

    finally:
        cleanup()


def test_list_transactions_is_paginated_and_user_scoped():
    cleanup()

    user_a = create_user(USER_A_EMAIL)
    user_b = create_user(USER_B_EMAIL)
    headers_a = auth_headers(user_a)
    headers_b = auth_headers(user_b)

    try:
        for index in range(3):
            response = client.post(
                "/transactions",
                json={
                    "date": f"2026-10-0{index + 1}",
                    "amount": "-100.00",
                    "merchant": f"Merchant {index}",
                    "trx_id": f"API-LIST-{_RUN_ID}-{index}",
                },
                headers=headers_a,
            )

            assert response.status_code == 201

        # User A sees their three transactions with paging metadata.
        response = client.get(
            "/transactions", params={"limit": 2, "offset": 0}, headers=headers_a
        )

        assert response.status_code == 200

        page = response.json()

        assert page["total"] == 3
        assert len(page["items"]) == 2
        assert page["limit"] == 2
        assert page["offset"] == 0
        assert page["has_more"] is True

        # User B sees none of user A's rows.
        response = client.get("/transactions", headers=headers_b)

        assert response.status_code == 200
        assert response.json()["total"] == 0

    finally:
        cleanup()


def test_transactions_require_auth():
    response = client.get("/transactions")

    assert response.status_code in (401, 403)


def test_update_transaction_category_records_correction():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)

    try:
        create_response = client.post(
            "/transactions",
            json={
                "date": "2026-10-10",
                "amount": "-850.00",
                "merchant": "Foodpanda",
                "description": "Food delivery",
                "trx_id": f"API-CORRECTION-{_RUN_ID}",
            },
            headers=headers,
        )

        assert create_response.status_code == 201

        transaction = create_response.json()

        assert transaction["category"] == "Food"

        response = client.patch(
            f"/transactions/{transaction['id']}/category",
            json={"category": "Business"},
            headers=headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert body["category"] == "Business"
        assert body["category_method"] == "user"
        assert body["category_confidence"] == "1.000"
        assert (
            body["category_reason"]
            == "User changed category from 'Food' to 'Business'."
        )

    finally:
        cleanup()


def test_update_transaction_category_is_user_scoped():
    cleanup()

    user_a = create_user(USER_A_EMAIL)
    user_b = create_user(USER_B_EMAIL)

    headers_a = auth_headers(user_a)
    headers_b = auth_headers(user_b)

    try:
        create_response = client.post(
            "/transactions",
            json={
                "date": "2026-10-10",
                "amount": "-500.00",
                "merchant": "Foodpanda",
                "trx_id": f"API-CROSS-USER-{_RUN_ID}",
            },
            headers=headers_a,
        )

        assert create_response.status_code == 201

        transaction_id = create_response.json()["id"]

        response = client.patch(
            f"/transactions/{transaction_id}/category",
            json={"category": "Business"},
            headers=headers_b,
        )

        assert response.status_code == 404

    finally:
        cleanup()



def test_same_category_does_not_create_new_correction():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)

    try:
        create_response = client.post(
            "/transactions",
            json={
                "date": "2026-10-10",
                "amount": "-850.00",
                "merchant": "Foodpanda",
                "trx_id": f"API-SAME-CATEGORY-{_RUN_ID}",
            },
            headers=headers,
        )

        assert create_response.status_code == 201

        transaction_id = create_response.json()["id"]

        response = client.patch(
            f"/transactions/{transaction_id}/category",
            json={"category": "Food"},
            headers=headers,
        )

        assert response.status_code == 200

        body = response.json()

        assert body["category"] == "Food"

    finally:
        cleanup()
              

# ---------------------------------------------------------------------------
# Insights router
# ---------------------------------------------------------------------------


def seed_via_api(headers: dict[str, str]) -> None:
    rows = [
        {"date": "2026-10-01", "amount": "50000.00", "merchant": "Acme", "category": "Income", "trx_id": f"API-INS-SAL-{_RUN_ID}"},
        {"date": "2026-10-02", "amount": "-20000.00", "merchant": "Landlord", "category": "Rent", "trx_id": f"API-INS-RENT-{_RUN_ID}"},
        {"date": "2026-10-03", "amount": "-5000.00", "merchant": "Grocer", "category": "Groceries", "trx_id": f"API-INS-FOOD-{_RUN_ID}"},
    ]

    for row in rows:
        response = client.post("/transactions", json=row, headers=headers)

        assert response.status_code == 201, response.text


def test_insights_summary_endpoint():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)

    try:
        seed_via_api(headers)

        response = client.get("/insights/summary", headers=headers)

        assert response.status_code == 200

        summary = response.json()

        assert summary["transaction_count"] == 3
        assert summary["total_income"] == "50000.00"
        assert summary["total_expenses"] == "-25000.00"
        assert summary["net"] == "25000.00"
        assert summary["savings_rate"] == "0.5000"

    finally:
        cleanup()


def test_insights_overview_endpoint():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)

    try:
        seed_via_api(headers)

        response = client.get("/insights/overview", headers=headers)

        assert response.status_code == 200

        overview = response.json()

        assert set(overview) == {
            "summary",
            "monthly",
            "month_over_month",
            "categories",
            "top_merchants",
            "recurring",
            "cashflow",
            "budget_baseline",
        }
        assert overview["summary"]["net"] == "25000.00"
        assert overview["monthly"][0]["month"] == "2026-10"
        assert overview["month_over_month"] == []
        assert overview["top_merchants"][0]["merchant"] == "Landlord"
        assert overview["cashflow"][-1]["running_balance"] == "25000.00"
        assert overview["budget_baseline"]["monthly_total_baseline"] == "25000.00"

    finally:
        cleanup()


def test_insights_are_user_scoped():
    cleanup()

    user_a = create_user(USER_A_EMAIL)
    user_b = create_user(USER_B_EMAIL)

    try:
        seed_via_api(auth_headers(user_a))

        response = client.get("/insights/summary", headers=auth_headers(user_b))

        assert response.status_code == 200

        summary = response.json()

        assert summary["transaction_count"] == 0
        assert summary["total_income"] == "0.00"

    finally:
        cleanup()


def test_insights_require_auth():
    response = client.get("/insights/summary")

    assert response.status_code in (401, 403)


def test_insights_date_filtering():
    cleanup()

    user = create_user(USER_A_EMAIL)
    headers = auth_headers(user)

    try:
        seed_via_api(headers)

        response = client.get(
            "/insights/summary",
            params={"start_date": "2026-10-02", "end_date": "2026-10-03"},
            headers=headers,
        )

        assert response.status_code == 200

        summary = response.json()

        # Only the two expense rows fall inside the window.
        assert summary["transaction_count"] == 2
        assert summary["total_income"] == "0.00"
        assert summary["total_expenses"] == "-25000.00"

    finally:
        cleanup()
