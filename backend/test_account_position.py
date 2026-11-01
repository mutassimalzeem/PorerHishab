"""Comprehensive tests for AI-15K Account Position & Trusted Cash Integration."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models.account import Account
from app.models.transactions import Transaction
from app.models.user import User

client = TestClient(app)


def make_user(db) -> User:
    user = User(
        email=f"account-pos-{uuid4()}@example.com",
        hashed_password="test-password",
        full_name="Account Position Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email, "user_id": user.id})
    return {"Authorization": f"Bearer {token}"}


def cleanup(db, *users: User) -> None:
    for u in users:
        if u is not None:
            # Delete transactions and accounts for user
            db.query(Transaction).filter(Transaction.user_id == u.id).delete()
            db.query(Account).filter(Account.user_id == u.id).delete()
            db.delete(u)
    db.commit()


def test_accounts_endpoint_requires_auth():
    res = client.get("/accounts")
    assert res.status_code == 401


def test_accounts_ownership_and_isolation():
    db = SessionLocal()
    user_a = make_user(db)
    user_b = make_user(db)
    try:
        acc_a = Account(user_id=user_a.id, name="User A Bank", currency="BDT", current_balance=Decimal("5000.00"))
        acc_b = Account(user_id=user_b.id, name="User B Bank", currency="BDT", current_balance=Decimal("9999.00"))
        db.add_all([acc_a, acc_b])
        db.commit()

        # User A requests /accounts
        res_a = client.get("/accounts", headers=auth_headers(user_a))
        assert res_a.status_code == 200
        data_a = res_a.json()
        assert len(data_a["items"]) == 1
        assert data_a["items"][0]["name"] == "User A Bank"
        assert not any(item["id"] == acc_b.id for item in data_a["items"])

        # User A tries to get User B's account
        res_single = client.get(f"/accounts/{acc_b.id}", headers=auth_headers(user_a))
        assert res_single.status_code == 404
    finally:
        cleanup(db, user_a, user_b)
        db.close()


def test_account_creation():
    db = SessionLocal()
    user = make_user(db)
    try:
        payload = {
            "name": "Savings Account",
            "account_type": "bank",
            "currency": "BDT",
            "opening_balance": "10000.00",
            "opening_balance_date": "2026-10-01",
            "current_balance": "10000.00",
            "balance_source": "manual",
            "balance_as_of": "2026-10-15T12:00:00Z",
        }
        res = client.post("/accounts", json=payload, headers=auth_headers(user))
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Savings Account"
        assert data["currency"] == "BDT"
        assert data["position_status"] == "trusted"
        assert data["is_eligible_for_bdt_aggregate"] is True
    finally:
        cleanup(db, user)
        db.close()


def test_one_trusted_bdt_account():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(
            user_id=user.id,
            name="Main Bank",
            currency="BDT",
            opening_balance=Decimal("20000.00"),
            opening_balance_date=date(2026, 10, 1),
            current_balance=Decimal("25000.00"),
            balance_source="manual",
            balance_as_of=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
        )
        db.add(acc)
        db.commit()
        db.refresh(acc)

        # Add transaction for 5000 income
        tx = Transaction(
            user_id=user.id,
            account_id=acc.id,
            date=date(2026, 10, 5),
            amount=Decimal("5000.00"),
            fee=Decimal("0.00"),
        )
        db.add(tx)
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["position_status"] == "trusted"
        assert item["reconciliation"]["status"] == "reconciled"
        assert item["reconciliation"]["derived_balance"] == "25000.00"
        assert item["reconciliation"]["difference"] == "0.00"

        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] == "25000.00"
        assert trusted_pos["eligible_accounts_count"] == 1
        assert trusted_pos["review_accounts_count"] == 0
        assert trusted_pos["status"] == "trusted"
        assert "Main Bank" in trusted_pos["contributing_account_names"]
    finally:
        cleanup(db, user)
        db.close()


def test_multiple_trusted_bdt_accounts():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc1 = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            opening_balance=Decimal("10000.00"),
            opening_balance_date=date(2026, 10, 1),
            current_balance=Decimal("12000.00"),
            balance_source="manual",
        )
        acc2 = Account(
            user_id=user.id,
            name="Cash",
            currency="BDT",
            opening_balance=Decimal("5000.00"),
            opening_balance_date=date(2026, 10, 1),
            current_balance=Decimal("4500.00"),
            balance_source="manual",
        )
        db.add_all([acc1, acc2])
        db.commit()
        db.refresh(acc1)
        db.refresh(acc2)

        tx1 = Transaction(user_id=user.id, account_id=acc1.id, date=date(2026, 10, 2), amount=Decimal("2000.00"), fee=Decimal("0.00"))
        tx2 = Transaction(user_id=user.id, account_id=acc2.id, date=date(2026, 10, 3), amount=Decimal("-500.00"), fee=Decimal("0.00"))
        db.add_all([tx1, tx2])
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 2
        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] == "16500.00"
        assert trusted_pos["eligible_accounts_count"] == 2
        assert trusted_pos["review_accounts_count"] == 0
        assert trusted_pos["status"] == "trusted"
    finally:
        cleanup(db, user)
        db.close()


def test_account_with_missing_balance():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(user_id=user.id, name="Empty Account", currency="BDT")
        db.add(acc)
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        item = data["items"][0]
        assert item["position_status"] == "insufficient_data"
        assert item["is_eligible_for_bdt_aggregate"] is False

        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] is None
        assert trusted_pos["status"] == "unavailable"
    finally:
        cleanup(db, user)
        db.close()


def test_account_with_insufficient_evidence():
    db = SessionLocal()
    user = make_user(db)
    try:
        # Has reported balance, but no transactions or opening balance
        acc = Account(user_id=user.id, name="Reported Only", currency="BDT", current_balance=Decimal("3000.00"))
        db.add(acc)
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        item = data["items"][0]
        assert item["position_status"] == "reported"
        assert item["is_eligible_for_bdt_aggregate"] is False
        assert item["reconciliation"]["derived_balance"] is None

        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] is None
        assert trusted_pos["status"] == "unavailable"
        assert trusted_pos["review_accounts_count"] == 1
    finally:
        cleanup(db, user)
        db.close()


def test_foreign_currency_account():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(
            user_id=user.id,
            name="USD Account",
            currency="USD",
            current_balance=Decimal("500.00"),
            opening_balance=Decimal("500.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add(acc)
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        item = data["items"][0]
        assert item["currency"] == "USD"
        assert item["position_status"] == "unsupported_currency"
        assert item["is_eligible_for_bdt_aggregate"] is False

        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] is None
        assert trusted_pos["status"] == "unavailable"
        assert trusted_pos["excluded_accounts_count"] == 1
    finally:
        cleanup(db, user)
        db.close()


def test_mixed_bdt_and_foreign_currency():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc_bdt = Account(
            user_id=user.id,
            name="BDT Bank",
            currency="BDT",
            current_balance=Decimal("20000.00"),
            opening_balance=Decimal("20000.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        acc_usd = Account(
            user_id=user.id,
            name="USD Wallet",
            currency="USD",
            current_balance=Decimal("100.00"),
            opening_balance=Decimal("100.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add_all([acc_bdt, acc_usd])
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) == 2

        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] == "20000.00"
        assert trusted_pos["eligible_accounts_count"] == 1
        assert trusted_pos["excluded_accounts_count"] == 1
        assert trusted_pos["status"] == "trusted"
        assert "BDT Bank" in trusted_pos["contributing_account_names"]
        assert "USD Wallet" not in trusted_pos["contributing_account_names"]
    finally:
        cleanup(db, user)
        db.close()


def test_mismatch_account_excluded_and_needs_review():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc_trusted = Account(
            user_id=user.id,
            name="Good Bank",
            currency="BDT",
            current_balance=Decimal("10000.00"),
            opening_balance=Decimal("10000.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        acc_mismatch = Account(
            user_id=user.id,
            name="Mismatch Bank",
            currency="BDT",
            current_balance=Decimal("5000.00"),  # Reported is 5000
            opening_balance=Decimal("4000.00"),  # Derived will be 4000 (diff = 1000)
            opening_balance_date=date(2026, 10, 1),
        )
        db.add_all([acc_trusted, acc_mismatch])
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()

        mismatch_item = next(i for i in data["items"] if i["name"] == "Mismatch Bank")
        assert mismatch_item["position_status"] == "unreconciled"
        assert mismatch_item["is_eligible_for_bdt_aggregate"] is False
        assert mismatch_item["reconciliation"]["difference"] == "1000.00"

        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] == "10000.00"  # Only good bank counted
        assert trusted_pos["eligible_accounts_count"] == 1
        assert trusted_pos["review_accounts_count"] == 1
        assert trusted_pos["status"] == "partially_trusted"
        assert "1 account needs review" in trusted_pos["message"]
    finally:
        cleanup(db, user)
        db.close()


def test_zero_balance_trusted():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(
            user_id=user.id,
            name="Zero Account",
            currency="BDT",
            current_balance=Decimal("0.00"),
            opening_balance=Decimal("0.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add(acc)
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] == "0.00"  # Distinct from None!
        assert trusted_pos["status"] == "trusted"
    finally:
        cleanup(db, user)
        db.close()


def test_negative_balance_trusted():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(
            user_id=user.id,
            name="Credit Card",
            currency="BDT",
            current_balance=Decimal("-1500.50"),
            opening_balance=Decimal("-1500.50"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add(acc)
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        trusted_pos = data["trusted_bdt_position"]
        assert trusted_pos["total"] == "-1500.50"
        assert trusted_pos["status"] == "trusted"
    finally:
        cleanup(db, user)
        db.close()


def test_decimal_precision():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc1 = Account(
            user_id=user.id,
            name="Bank 1",
            currency="BDT",
            current_balance=Decimal("12345.67"),
            opening_balance=Decimal("12345.67"),
            opening_balance_date=date(2026, 10, 1),
        )
        acc2 = Account(
            user_id=user.id,
            name="Bank 2",
            currency="BDT",
            current_balance=Decimal("87654.33"),
            opening_balance=Decimal("87654.33"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add_all([acc1, acc2])
        db.commit()

        res = client.get("/accounts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        trusted_pos = data["trusted_bdt_position"]
        # 12345.67 + 87654.33 = 100000.00
        assert trusted_pos["total"] == "100000.00"
    finally:
        cleanup(db, user)
        db.close()


def test_balance_updates_and_reconciliation():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(user_id=user.id, name="Test Account", currency="BDT")
        db.add(acc)
        db.commit()
        db.refresh(acc)

        # Step 1: Update opening balance
        res_op = client.patch(
            f"/accounts/{acc.id}/balance/opening",
            json={"opening_balance": "5000.00", "opening_balance_date": "2026-10-01"},
            headers=auth_headers(user),
        )
        assert res_op.status_code == 200
        assert res_op.json()["opening_balance"] == "5000.00"

        # Step 2: Update current balance
        res_bal = client.patch(
            f"/accounts/{acc.id}/balance",
            json={"current_balance": "5000.00", "balance_source": "manual", "balance_as_of": "2026-10-15T00:00:00Z"},
            headers=auth_headers(user),
        )
        assert res_bal.status_code == 200
        assert res_bal.json()["status"] == "reconciled"
        assert res_bal.json()["difference"] == "0.00"

        # Verify through overview
        res_all = client.get("/accounts", headers=auth_headers(user))
        assert res_all.json()["trusted_bdt_position"]["total"] == "5000.00"
        assert res_all.json()["trusted_bdt_position"]["status"] == "trusted"
    finally:
        cleanup(db, user)
        db.close()


def test_cashflow_with_account_position():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(
            user_id=user.id,
            name="Payroll Bank",
            currency="BDT",
            current_balance=Decimal("50000.00"),
            opening_balance=Decimal("50000.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add(acc)
        db.commit()

        # Call cashflow with use_account_position=True
        res = client.post(
            "/finance/coach/cashflow",
            json={"use_account_position": True, "months_ahead": 3},
            headers=auth_headers(user),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["starting_balance"] == "50000.00"
        assert data["balance_source"] == "account_position"
        assert any("trusted BDT account positions" in a for a in data["assumptions"])
    finally:
        cleanup(db, user)
        db.close()


def test_cashflow_with_account_position_unavailable_error():
    db = SessionLocal()
    user = make_user(db)
    try:
        # No accounts exist
        res = client.post(
            "/finance/coach/cashflow",
            json={"use_account_position": True, "months_ahead": 3},
            headers=auth_headers(user),
        )
        assert res.status_code == 422
        assert "Trusted account position is unavailable" in res.json()["detail"]
    finally:
        cleanup(db, user)
        db.close()


def test_cashflow_preserves_caller_starting_balance():
    db = SessionLocal()
    user = make_user(db)
    try:
        res = client.post(
            "/finance/coach/cashflow",
            json={"starting_balance": "12345.00", "months_ahead": 3},
            headers=auth_headers(user),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["starting_balance"] == "12345.00"
        assert data["balance_source"] == "caller"
    finally:
        cleanup(db, user)
        db.close()


def test_purchase_decision_with_account_position():
    db = SessionLocal()
    user = make_user(db)
    try:
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("30000.00"),
            opening_balance=Decimal("30000.00"),
            opening_balance_date=date(2026, 10, 1),
        )
        db.add(acc)
        db.commit()

        res = client.post(
            "/finance/coach/spending-decision",
            json={
                "use_account_position": True,
                "purchase_amount": "5000.00",
                "safety_buffer": "10000.00",
                "horizon_days": 30,
            },
            headers=auth_headers(user),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "safe"
        assert data["balance_source"] == "account_position"
        assert any("trusted account position" in a for a in data["assumptions"])
    finally:
        cleanup(db, user)
        db.close()


def test_purchase_decision_with_account_position_unavailable_error():
    db = SessionLocal()
    user = make_user(db)
    try:
        res = client.post(
            "/finance/coach/spending-decision",
            json={
                "use_account_position": True,
                "purchase_amount": "5000.00",
                "safety_buffer": "10000.00",
                "horizon_days": 30,
            },
            headers=auth_headers(user),
        )
        assert res.status_code == 422
        assert "Trusted account position is unavailable" in res.json()["detail"]
    finally:
        cleanup(db, user)
        db.close()


def test_purchase_decision_preserves_caller_starting_balance():
    db = SessionLocal()
    user = make_user(db)
    try:
        res = client.post(
            "/finance/coach/spending-decision",
            json={
                "starting_balance": "20000.00",
                "purchase_amount": "5000.00",
                "safety_buffer": "5000.00",
                "horizon_days": 30,
            },
            headers=auth_headers(user),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "safe"
        assert data["balance_source"] == "caller"
    finally:
        cleanup(db, user)
        db.close()
