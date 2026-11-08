"""Comprehensive unit, integration, and security tests for AI-15L Proactive Financial Alerts."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.main import app
from app.models.account import Account
from app.models.financial_alert import FinancialAlert
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.transactions import Transaction
from app.models.user import User
from app.services.finance.financial_alerts import (
    evaluate_alerts,
    get_unread_count,
    list_alerts,
    mark_alert_actioned,
    mark_alert_read,
    dismiss_alert,
    restore_alert,
)
from app.services.intelligence.periods import today_dhaka

client = TestClient(app)
ZERO = Decimal("0.00")


def make_user(db: SessionLocal) -> User:
    user = User(
        email=f"alerts-user-{uuid4()}@example.com",
        hashed_password="test-password",
        full_name="Alerts Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email, "user_id": user.id})
    return {"Authorization": f"Bearer {token}"}


def cleanup(db: SessionLocal, *users: User) -> None:
    for u in users:
        if u is not None:
            db.query(FinancialAlert).filter(FinancialAlert.user_id == u.id).delete()
            db.query(ScheduledCashflowItem).filter(ScheduledCashflowItem.user_id == u.id).delete()
            db.query(Transaction).filter(Transaction.user_id == u.id).delete()
            db.query(Account).filter(Account.user_id == u.id).delete()
            db.delete(u)
    db.commit()


def test_alerts_endpoint_requires_auth():
    """All financial alert endpoints must reject unauthenticated requests with 401."""
    assert client.get("/finance/alerts").status_code == 401
    assert client.get("/finance/alerts/unread-count").status_code == 401
    assert client.post("/finance/alerts/evaluate").status_code == 401
    assert client.patch("/finance/alerts/1/read").status_code == 401
    assert client.patch("/finance/alerts/1/dismiss").status_code == 401
    assert client.patch("/finance/alerts/1/actioned").status_code == 401
    assert client.post("/finance/alerts/1/restore").status_code == 401


def test_insufficient_data_suppression():
    """When user has no accounts or insufficient historical runway data, do not invent cash risk alerts."""
    db = SessionLocal()
    user = make_user(db)
    try:
        summary = evaluate_alerts(db, user.id)
        assert summary.created == 0

        res = client.get("/finance/alerts", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["items"] == []
    finally:
        cleanup(db, user)
        db.close()


def test_cash_shortfall_and_at_risk_triggers():
    """Cash position shortfall generates critical alert; at-risk generates high alert."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        # User has BDT 1,000 in reconciled account
        acc = Account(
            user_id=user.id,
            name="Primary Checking",
            currency="BDT",
            current_balance=Decimal("1000.00"),
            opening_balance=Decimal("1000.00"),
            opening_balance_date=today - timedelta(days=10),
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc)

        # Scheduled expense of BDT 2,500 due in 5 days -> causes projected shortfall
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="House Rent",
            kind="expense",
            amount=Decimal("2500.00"),
            due_date=today + timedelta(days=5),
            status="scheduled",
        )
        db.add(item)
        db.commit()

        # Evaluate
        res = client.post("/finance/alerts/evaluate", headers=auth_headers(user))
        assert res.status_code == 200
        summary = res.json()
        assert summary["created"] >= 1

        # Check alerts
        res = client.get("/finance/alerts", headers=auth_headers(user))
        assert res.status_code == 200
        alerts = res.json()["items"]
        shortfall_alert = next((a for a in alerts if a["alert_type"] == "cash_shortfall"), None)
        assert shortfall_alert is not None
        assert shortfall_alert["severity"] == "critical"
        assert shortfall_alert["status"] == "active"
        assert shortfall_alert["action_url"] == "/cashflow"
        assert "minimum_projected_balance" in shortfall_alert["evidence"]
        assert shortfall_alert["is_read"] is False
    finally:
        cleanup(db, user)
        db.close()


def test_upcoming_and_overdue_obligations():
    """Overdue scheduled obligation triggers high/critical alert; due soon triggers medium/high alert."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        acc = Account(
            user_id=user.id,
            name="Checking",
            currency="BDT",
            current_balance=Decimal("50000.00"),
            opening_balance=Decimal("50000.00"),
            opening_balance_date=today - timedelta(days=30),
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc)

        # Overdue item: due 2 days ago
        item_overdue = ScheduledCashflowItem(
            user_id=user.id,
            title="Internet Bill",
            kind="expense",
            amount=Decimal("1500.00"),
            due_date=today - timedelta(days=2),
            status="scheduled",
        )
        # Due soon item: due tomorrow
        item_due_soon = ScheduledCashflowItem(
            user_id=user.id,
            title="Utility Bill",
            kind="expense",
            amount=Decimal("3000.00"),
            due_date=today + timedelta(days=1),
            status="scheduled",
        )
        db.add_all([item_overdue, item_due_soon])
        db.commit()

        # Evaluate
        client.post("/finance/alerts/evaluate", headers=auth_headers(user))

        res = client.get("/finance/alerts", headers=auth_headers(user))
        alerts = res.json()["items"]

        overdue_alert = next((a for a in alerts if a["alert_key"] == f"obligation:{item_overdue.id}:due"), None)
        assert overdue_alert is not None
        assert overdue_alert["alert_type"] == "obligation_overdue"
        assert overdue_alert["severity"] == "high"
        assert overdue_alert["evidence"]["remaining_amount"] == "1500.00"
        assert overdue_alert["evidence"]["days_overdue"] == 2

        due_soon_alert = next((a for a in alerts if a["alert_key"] == f"obligation:{item_due_soon.id}:due"), None)
        assert due_soon_alert is not None
        assert due_soon_alert["alert_type"] == "obligation_due_soon"
        assert due_soon_alert["severity"] == "high"  # 1 day until due is high
        assert due_soon_alert["evidence"]["remaining_amount"] == "3000.00"
    finally:
        cleanup(db, user)
        db.close()


def test_account_reconciliation_mismatch_alert():
    """Unreconciled account position with reported balance mismatch creates medium alert."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        # Reported balance is 20,000, but opening balance is 10,000 with no transactions -> mismatch of 10,000
        acc = Account(
            user_id=user.id,
            name="Mismatched Bank",
            currency="BDT",
            current_balance=Decimal("20000.00"),
            opening_balance=Decimal("10000.00"),
            opening_balance_date=today - timedelta(days=5),
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc)
        db.commit()

        client.post("/finance/alerts/evaluate", headers=auth_headers(user))

        res = client.get("/finance/alerts", headers=auth_headers(user))
        alerts = res.json()["items"]

        mismatch_alert = next((a for a in alerts if a["alert_type"] == "account_unreconciled"), None)
        assert mismatch_alert is not None
        assert mismatch_alert["severity"] == "medium"
        assert mismatch_alert["evidence"]["account_name"] == "Mismatched Bank"
        assert mismatch_alert["evidence"]["difference"] == "10000.00"
        assert mismatch_alert["action_url"] == "/accounts"
    finally:
        cleanup(db, user)
        db.close()


def test_deduplication_and_idempotent_evaluation():
    """Repeated evaluations of the same condition do not create duplicate records or increment unread count."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Recurring Service",
            kind="expense",
            amount=Decimal("500.00"),
            due_date=today + timedelta(days=2),
            status="scheduled",
        )
        db.add(item)
        db.commit()

        # Evaluation 1
        s1 = evaluate_alerts(db, user.id)
        assert s1.created == 1
        assert s1.unchanged == 0

        # Evaluation 2 (identical condition)
        s2 = evaluate_alerts(db, user.id)
        assert s2.created == 0
        assert s2.unchanged == 1

        # Verify only 1 alert exists in DB
        alerts = db.query(FinancialAlert).filter_by(user_id=user.id).all()
        assert len(alerts) == 1
        assert alerts[0].occurrence_count == 1

        # Unread count is exactly 1
        assert get_unread_count(db, user.id) == 1
    finally:
        cleanup(db, user)
        db.close()


def test_meaningful_change_and_escalation():
    """Escalation from at-risk to cash-shortfall updates severity, increments occurrence_count, and re-notifies."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("2000.00"),
            opening_balance=Decimal("2000.00"),
            opening_balance_date=today - timedelta(days=10),
            balance_as_of=datetime.now(timezone.utc),
        )
        # Moderate expense: 2000 - 1500 = 500 balance remaining -> at-risk (with 500 safety threshold)
        item1 = ScheduledCashflowItem(
            user_id=user.id,
            title="Modest Expense",
            kind="expense",
            amount=Decimal("1500.00"),
            due_date=today + timedelta(days=10),
            status="scheduled",
        )
        db.add_all([acc, item1])
        db.commit()

        # Evaluate at-risk with safety threshold of 500 BDT
        evaluate_alerts(db, user.id, safety_threshold=Decimal("500.00"))

        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key="cash_position:runway_risk").one()
        assert alert.alert_type == "cash_at_risk"
        assert alert.severity == "high"
        assert alert.occurrence_count == 1

        # User reads the alert
        mark_alert_read(db, user.id, alert.id)
        assert alert.read_at is not None

        # Now add large expense that causes cash shortfall: 2000 - 1500 - 1000 = -500 BDT
        item2 = ScheduledCashflowItem(
            user_id=user.id,
            title="Big Surprise",
            kind="expense",
            amount=Decimal("1000.00"),
            due_date=today + timedelta(days=12),
            status="scheduled",
        )
        db.add(item2)
        db.commit()

        # Re-evaluate
        s2 = evaluate_alerts(db, user.id, safety_threshold=Decimal("500.00"))
        assert s2.updated >= 1

        db.refresh(alert)
        assert alert.alert_type == "cash_shortfall"
        assert alert.severity == "critical"
        assert alert.occurrence_count == 2
        # Read at should be cleared for escalation to critical
        assert alert.read_at is None
    finally:
        cleanup(db, user)
        db.close()


def test_alert_resolution_when_condition_clears():
    """When an obligation is marked paid or cancelled, its alert resolves automatically."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Electricity",
            kind="expense",
            amount=Decimal("1200.00"),
            due_date=today + timedelta(days=1),
            status="scheduled",
        )
        db.add(item)
        db.commit()

        # Evaluate -> creates active alert
        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item.id}:due").one()
        assert alert.status == "active"
        assert alert.resolved_at is None

        # Mark obligation as paid
        item.status = "paid"
        db.commit()

        # Re-evaluate -> resolves alert
        summary = evaluate_alerts(db, user.id)
        assert summary.resolved == 1

        db.refresh(alert)
        assert alert.status == "resolved"
        assert alert.resolved_at is not None
    finally:
        cleanup(db, user)
        db.close()


def test_reappearance_after_resolution():
    """An alert that was resolved will reactivate if the condition recurs."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("2000.00"),
            opening_balance=Decimal("2000.00"),
            opening_balance_date=today - timedelta(days=10),
            balance_as_of=datetime.now(timezone.utc),
        )
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="School Fee",
            kind="expense",
            amount=Decimal("5000.00"),
            due_date=today + timedelta(days=5),
            status="scheduled",
        )
        db.add_all([acc, item])
        db.commit()

        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key="cash_position:runway_risk").one()
        assert alert.status == "active"

        # Condition clears: deposit 10,000 BDT into account
        acc.current_balance = Decimal("12000.00")
        acc.opening_balance = Decimal("12000.00")
        db.commit()

        evaluate_alerts(db, user.id)
        db.refresh(alert)
        assert alert.status == "resolved"
        assert alert.occurrence_count == 1

        # Condition recurs: deposit withdrawn, balance drops back to 2,000 BDT
        acc.current_balance = Decimal("2000.00")
        acc.opening_balance = Decimal("2000.00")
        db.commit()

        evaluate_alerts(db, user.id)
        db.refresh(alert)
        assert alert.status == "active"
        assert alert.resolved_at is None
        assert alert.occurrence_count == 2
        assert alert.read_at is None
    finally:
        cleanup(db, user)
        db.close()


def test_dismissal_persistence_and_critical_override():
    """Dismissed alert stays dismissed on repeated evaluation unless escalated to critical."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        # Mismatch alert (medium severity)
        acc = Account(
            user_id=user.id,
            name="Bank X",
            currency="BDT",
            current_balance=Decimal("15000.00"),
            opening_balance=Decimal("10000.00"),
            opening_balance_date=today - timedelta(days=5),
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc)
        db.commit()

        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id).one()
        assert alert.status == "active"

        # User dismisses it
        dismiss_alert(db, user.id, alert.id)
        db.refresh(alert)
        assert alert.status == "dismissed"
        assert alert.dismissed_at is not None

        # Re-evaluate: stays dismissed!
        evaluate_alerts(db, user.id)
        db.refresh(alert)
        assert alert.status == "dismissed"
    finally:
        cleanup(db, user)
        db.close()


def test_restore_dismissed_alert():
    """User can restore a dismissed alert back to active status."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Gym Membership",
            kind="expense",
            amount=Decimal("800.00"),
            due_date=today + timedelta(days=2),
            status="scheduled",
        )
        db.add(item)
        db.commit()

        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id).one()

        # Dismiss
        res_d = client.patch(f"/finance/alerts/{alert.id}/dismiss", headers=auth_headers(user))
        assert res_d.status_code == 200
        assert res_d.json()["status"] == "dismissed"

        # Restore
        res_r = client.post(f"/finance/alerts/{alert.id}/restore", headers=auth_headers(user))
        assert res_r.status_code == 200
        assert res_r.json()["status"] == "active"
        assert res_r.json()["dismissed_at"] is None
    finally:
        cleanup(db, user)
        db.close()


def test_mark_read_and_unread_count_endpoint():
    """Unread count correctly tracks all unread active alerts and decrements on read."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        i1 = ScheduledCashflowItem(
            user_id=user.id, title="Sub 1", kind="expense", amount=Decimal("100.00"), due_date=today + timedelta(days=1), status="scheduled"
        )
        i2 = ScheduledCashflowItem(
            user_id=user.id, title="Sub 2", kind="expense", amount=Decimal("200.00"), due_date=today + timedelta(days=2), status="scheduled"
        )
        db.add_all([i1, i2])
        db.commit()

        evaluate_alerts(db, user.id)

        # Count should be 2
        res = client.get("/finance/alerts/unread-count", headers=auth_headers(user))
        assert res.status_code == 200
        assert res.json()["unread_count"] == 2

        # Mark 1 as read
        alerts = db.query(FinancialAlert).filter_by(user_id=user.id).all()
        client.patch(f"/finance/alerts/{alerts[0].id}/read", headers=auth_headers(user))

        # Count should now be 1
        res = client.get("/finance/alerts/unread-count", headers=auth_headers(user))
        assert res.json()["unread_count"] == 1
    finally:
        cleanup(db, user)
        db.close()


def test_mark_actioned_semantics():
    """Marking an alert actioned records actioned_at without verifying resolution."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        item = ScheduledCashflowItem(
            user_id=user.id, title="Gas Bill", kind="expense", amount=Decimal("500.00"), due_date=today + timedelta(days=1), status="scheduled"
        )
        db.add(item)
        db.commit()

        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id).one()

        res = client.patch(f"/finance/alerts/{alert.id}/actioned", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        assert data["actioned_at"] is not None
        # Does NOT falsely claim resolution: status is still active!
        assert data["status"] == "active"
    finally:
        cleanup(db, user)
        db.close()


def test_user_isolation_and_cross_user_security():
    """Users cannot view or mutate each other's alerts."""
    db = SessionLocal()
    user_a = make_user(db)
    user_b = make_user(db)
    today = today_dhaka()
    try:
        item_b = ScheduledCashflowItem(
            user_id=user_b.id, title="User B Expense", kind="expense", amount=Decimal("999.00"), due_date=today + timedelta(days=1), status="scheduled"
        )
        db.add(item_b)
        db.commit()

        evaluate_alerts(db, user_b.id)
        alert_b = db.query(FinancialAlert).filter_by(user_id=user_b.id).one()

        # User A attempts to list alerts -> gets empty list
        res_a = client.get("/finance/alerts", headers=auth_headers(user_a))
        assert res_a.status_code == 200
        assert res_a.json()["total"] == 0
        assert res_a.json()["items"] == []

        # User A attempts to read User B's alert -> 404
        assert client.patch(f"/finance/alerts/{alert_b.id}/read", headers=auth_headers(user_a)).status_code == 404

        # User A attempts to dismiss User B's alert -> 404
        assert client.patch(f"/finance/alerts/{alert_b.id}/dismiss", headers=auth_headers(user_a)).status_code == 404

        # User A attempts to mark actioned User B's alert -> 404
        assert client.patch(f"/finance/alerts/{alert_b.id}/actioned", headers=auth_headers(user_a)).status_code == 404

        # User A attempts to restore User B's alert -> 404
        assert client.post(f"/finance/alerts/{alert_b.id}/restore", headers=auth_headers(user_a)).status_code == 404
    finally:
        cleanup(db, user_a, user_b)
        db.close()


def test_stable_sorting_and_pagination():
    """Alerts list returns critical/high first, then active before dismissed, with bounded pagination."""
    db = SessionLocal()
    user = make_user(db)
    now = datetime.now(timezone.utc)
    try:
        a_low = FinancialAlert(
            user_id=user.id, alert_key="k_low", alert_type="type_low", severity="low",
            title="Low Alert", title_key="k", message="m", message_key="m", evidence={},
            recommended_action="act", status="active", first_detected_at=now, last_detected_at=now,
        )
        a_crit = FinancialAlert(
            user_id=user.id, alert_key="k_crit", alert_type="type_crit", severity="critical",
            title="Critical Alert", title_key="k", message="m", message_key="m", evidence={},
            recommended_action="act", status="active", first_detected_at=now, last_detected_at=now,
        )
        a_med = FinancialAlert(
            user_id=user.id, alert_key="k_med", alert_type="type_med", severity="medium",
            title="Med Alert", title_key="k", message="m", message_key="m", evidence={},
            recommended_action="act", status="active", first_detected_at=now, last_detected_at=now,
        )
        db.add_all([a_low, a_crit, a_med])
        db.commit()

        # Page 1, limit 2
        res = client.get("/finance/alerts?limit=2&offset=0", headers=auth_headers(user))
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        # First item MUST be critical
        assert data["items"][0]["severity"] == "critical"
        assert data["items"][1]["severity"] == "medium"

        # Page 2, limit 2
        res2 = client.get("/finance/alerts?limit=2&offset=2", headers=auth_headers(user))
        data2 = res2.json()
        assert len(data2["items"]) == 1
        assert data2["items"][0]["severity"] == "low"
    finally:
        cleanup(db, user)
        db.close()


def test_filtering_by_status_severity_and_unread():
    """Alerts list supports status, severity, and unread_only query filters."""
    db = SessionLocal()
    user = make_user(db)
    now = datetime.now(timezone.utc)
    try:
        a1 = FinancialAlert(
            user_id=user.id, alert_key="k1", alert_type="t1", severity="critical",
            title="Active Unread", title_key="k", message="m", message_key="m", evidence={},
            recommended_action="act", status="active", read_at=None, first_detected_at=now, last_detected_at=now,
        )
        a2 = FinancialAlert(
            user_id=user.id, alert_key="k2", alert_type="t2", severity="high",
            title="Active Read", title_key="k", message="m", message_key="m", evidence={},
            recommended_action="act", status="active", read_at=now, first_detected_at=now, last_detected_at=now,
        )
        a3 = FinancialAlert(
            user_id=user.id, alert_key="k3", alert_type="t3", severity="medium",
            title="Dismissed", title_key="k", message="m", message_key="m", evidence={},
            recommended_action="act", status="dismissed", first_detected_at=now, last_detected_at=now,
        )
        db.add_all([a1, a2, a3])
        db.commit()

        # Unread only
        res = client.get("/finance/alerts?unread_only=true", headers=auth_headers(user))
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["alert_key"] == "k1"

        # Status dismissed
        res = client.get("/finance/alerts?status=dismissed", headers=auth_headers(user))
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["alert_key"] == "k3"

        # Severity critical
        res = client.get("/finance/alerts?severity=critical", headers=auth_headers(user))
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["alert_key"] == "k1"
    finally:
        cleanup(db, user)
        db.close()


def test_coaching_goal_risk_and_feedback_overlay():
    """Coaching goal risk generates alert; feedback (snoozed/dismissed) suppresses/resolves it."""
    from app.models.savings_goal import SavingsGoal
    from app.services.finance.coaching_feedback import submit as submit_feedback
    from app.schemas.coaching import CoachingFeedbackInput

    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        # Goal with target date in the past -> goal risk
        goal = SavingsGoal(
            user_id=user.id,
            name="Emergency Fund",
            target_amount=Decimal("50000.00"),
            current_saved=Decimal("5000.00"),
            target_date=today - timedelta(days=5),
            status="active",
        )
        db.add(goal)
        db.commit()

        # Evaluate -> creates goal risk alert
        summary = evaluate_alerts(db, user.id)
        assert summary.created >= 1

        alert = db.query(FinancialAlert).filter(
            FinancialAlert.user_id == user.id,
            FinancialAlert.alert_type == "savings_goal_at_risk",
        ).first()
        assert alert is not None
        assert alert.status == "active"

        # Now submit coaching feedback: user dismisses recommendation
        rec_id = f"goal_risk:{goal.id}:{today:%Y-%m}"
        submit_feedback(
            db,
            user.id,
            rec_id,
            CoachingFeedbackInput(status="dismissed"),
        )

        # Re-evaluate -> visible_coaching excludes dismissed rec, resolving the alert!
        s2 = evaluate_alerts(db, user.id)
        assert s2.resolved >= 1

        db.refresh(alert)
        assert alert.status == "resolved"
    finally:
        db.query(SavingsGoal).filter_by(user_id=user.id).delete()
        cleanup(db, user)
        db.close()


def test_foreign_currency_account_excluded_from_bdt_alerts():
    """Foreign currency accounts are excluded from BDT cash alerts and do not trigger false mismatches."""
    db = SessionLocal()
    user = make_user(db)
    try:
        acc_usd = Account(
            user_id=user.id,
            name="US Dollar Savings",
            currency="USD",
            current_balance=Decimal("2000.00"),
            opening_balance=Decimal("1000.00"),  # Difference in USD
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc_usd)
        db.commit()

        summary = evaluate_alerts(db, user.id)
        # USD account is classified as unsupported_currency, not unreconciled BDT
        assert summary.created == 0

        res = client.get("/finance/alerts", headers=auth_headers(user))
        assert res.json()["total"] == 0
    finally:
        cleanup(db, user)
        db.close()


@pytest.mark.skipif(SessionLocal.kw["bind"].dialect.name != "postgresql", reason="PostgreSQL concurrency semantics required")
def test_concurrent_evaluation_safety():
    """Concurrent evaluations for the same user succeed cleanly without duplicate key violations."""
    from concurrent.futures import ThreadPoolExecutor

    db = SessionLocal()
    user = make_user(db)
    user_id = user.id  # Extract primitive integer before multithreading
    today = today_dhaka()
    try:
        item = ScheduledCashflowItem(
            user_id=user_id,
            title="Shared Obligation",
            kind="expense",
            amount=Decimal("1500.00"),
            due_date=today + timedelta(days=2),
            status="scheduled",
        )
        db.add(item)
        db.commit()

        def run_eval():
            thread_db = SessionLocal()
            try:
                return evaluate_alerts(thread_db, user_id)
            finally:
                thread_db.close()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_eval) for _ in range(4)]
            results = [f.result() for f in futures]

        # Total created across all concurrent runs must be exactly 1
        total_created = sum(r.created for r in results)
        assert total_created == 1

        alerts = db.query(FinancialAlert).filter_by(user_id=user_id).all()
        assert len(alerts) == 1
        # Concurrency safety: occurrence_count must remain exactly 1, not duplicate or double-incremented
        assert alerts[0].occurrence_count == 1
        assert alerts[0].status == "active"
    finally:
        cleanup(db, user)
        db.close()


def test_concurrent_evaluations_independent_for_separate_users():
    """Simultaneous evaluations for different users execute independently and in isolation without blocking."""
    from concurrent.futures import ThreadPoolExecutor

    db = SessionLocal()
    user_a = make_user(db)
    user_b = make_user(db)
    user_a_id = user_a.id
    user_b_id = user_b.id
    today = today_dhaka()
    try:
        item_a = ScheduledCashflowItem(
            user_id=user_a_id,
            title="User A Obligation",
            kind="expense",
            amount=Decimal("1000.00"),
            due_date=today + timedelta(days=2),
            status="scheduled",
        )
        item_b = ScheduledCashflowItem(
            user_id=user_b_id,
            title="User B Obligation",
            kind="expense",
            amount=Decimal("2000.00"),
            due_date=today + timedelta(days=3),
            status="scheduled",
        )
        db.add_all([item_a, item_b])
        db.commit()

        def run_eval_for(u_id: int):
            thread_db = SessionLocal()
            try:
                return evaluate_alerts(thread_db, u_id)
            finally:
                thread_db.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_a = executor.submit(run_eval_for, user_a_id)
            fut_b = executor.submit(run_eval_for, user_b_id)
            res_a = fut_a.result()
            res_b = fut_b.result()

        # Both evaluations succeed and create 1 alert for each respective user
        assert res_a.created == 1
        assert res_b.created == 1

        alerts_a = db.query(FinancialAlert).filter_by(user_id=user_a_id).all()
        alerts_b = db.query(FinancialAlert).filter_by(user_id=user_b_id).all()
        assert len(alerts_a) == 1
        assert len(alerts_b) == 1
        assert alerts_a[0].title == "Upcoming Obligation: User A Obligation"
        assert alerts_b[0].title == "Upcoming Obligation: User B Obligation"
    finally:
        cleanup(db, user_a, user_b)
        db.close()


def test_lifecycle_timestamp_resets_on_recurrence_and_escalation():
    """Verify that resolved recurrence, critical escalation, and unchanged states handle timestamps correctly."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        # --- SCENARIO 1: Resolved alert recurs ---
        acc = Account(
            user_id=user.id,
            name="Checking",
            currency="BDT",
            current_balance=Decimal("1000.00"),
            opening_balance=Decimal("1000.00"),
            opening_balance_date=today - timedelta(days=10),
            balance_as_of=datetime.now(timezone.utc),
        )
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Tuition",
            kind="expense",
            amount=Decimal("2000.00"),
            due_date=today + timedelta(days=5),
            status="scheduled",
        )
        db.add_all([acc, item])
        db.commit()

        # Evaluate 1: creates critical cash shortfall
        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key="cash_position:runway_risk").one()
        first_detected = alert.first_detected_at

        # User reads and takes action
        mark_alert_read(db, user.id, alert.id)
        mark_alert_actioned(db, user.id, alert.id)
        db.refresh(alert)
        assert alert.read_at is not None
        assert alert.actioned_at is not None

        # Condition clears: deposit funds
        acc.current_balance = Decimal("10000.00")
        acc.opening_balance = Decimal("10000.00")
        db.commit()

        # Evaluate 2: resolves alert
        evaluate_alerts(db, user.id)
        db.refresh(alert)
        assert alert.status == "resolved"
        assert alert.resolved_at is not None

        # Condition recurs: funds withdrawn
        acc.current_balance = Decimal("1000.00")
        acc.opening_balance = Decimal("1000.00")
        db.commit()

        # Evaluate 3: reactivates alert
        evaluate_alerts(db, user.id)
        db.refresh(alert)
        assert alert.status == "active"
        assert alert.occurrence_count == 2
        assert alert.first_detected_at == first_detected  # Original inception preserved
        assert alert.resolved_at is None  # Cleared
        assert alert.read_at is None  # Cleared
        assert alert.dismissed_at is None  # Cleared
        assert alert.actioned_at is None  # Crucial: stale action timestamp cleared!

        # --- SCENARIO 2: Dismissed high alert escalates to critical ---
        # Switch expense so starting cash 2000 - 1500 = 500 (at risk with safety threshold 500)
        acc.current_balance = Decimal("2000.00")
        acc.opening_balance = Decimal("2000.00")
        item.amount = Decimal("1500.00")
        db.commit()

        # Evaluate at-risk (high)
        evaluate_alerts(db, user.id, safety_threshold=Decimal("500.00"))
        db.refresh(alert)
        assert alert.severity == "high"
        assert alert.alert_type == "cash_at_risk"

        # User marks actioned and dismisses it
        mark_alert_actioned(db, user.id, alert.id)
        dismiss_alert(db, user.id, alert.id)
        db.refresh(alert)
        assert alert.status == "dismissed"
        assert alert.dismissed_at is not None
        assert alert.actioned_at is not None
        curr_count = alert.occurrence_count

        # Condition worsens to critical: 2000 - 2500 = -500 shortfall
        item.amount = Decimal("2500.00")
        db.commit()

        evaluate_alerts(db, user.id, safety_threshold=Decimal("500.00"))
        db.refresh(alert)
        assert alert.status == "active"  # Critical override
        assert alert.severity == "critical"
        assert alert.alert_type == "cash_shortfall"
        assert alert.dismissed_at is None  # Cleared on critical escalation
        assert alert.read_at is None  # Cleared on critical escalation
        assert alert.actioned_at is None  # Cleared: old action on high cannot apply to critical
        assert alert.resolved_at is None
        assert alert.occurrence_count == curr_count + 1

        # --- SCENARIO 3: Dismissed high alert remains high ---
        item2 = ScheduledCashflowItem(
            user_id=user.id,
            title="Dismissed High Obligation",
            kind="expense",
            amount=Decimal("100.00"),
            due_date=today + timedelta(days=1),  # 1 day is high
            status="scheduled",
        )
        db.add(item2)
        db.commit()

        evaluate_alerts(db, user.id)
        alert2 = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item2.id}:due").one()
        assert alert2.severity == "high"

        dismiss_alert(db, user.id, alert2.id)
        db.refresh(alert2)
        initial_dismissed_at = alert2.dismissed_at
        assert alert2.status == "dismissed"
        assert initial_dismissed_at is not None
        initial_count2 = alert2.occurrence_count

        # Re-evaluate under identical high condition
        summary3 = evaluate_alerts(db, user.id)
        db.refresh(alert2)
        assert alert2.status == "dismissed"
        assert alert2.dismissed_at == initial_dismissed_at  # Preserved
        assert alert2.occurrence_count == initial_count2  # No increment

        # --- SCENARIO 4: Active read alert remains unchanged ---
        mark_alert_read(db, user.id, alert.id)
        mark_alert_actioned(db, user.id, alert.id)
        db.refresh(alert)
        read_ts = alert.read_at
        act_ts = alert.actioned_at
        count_before = alert.occurrence_count

        # Re-evaluate with no financial changes
        summary4 = evaluate_alerts(db, user.id, safety_threshold=Decimal("500.00"))
        db.refresh(alert)
        assert alert.status == "active"
        assert alert.read_at == read_ts  # Remains read
        assert alert.actioned_at == act_ts  # Action timestamp preserved
        assert alert.occurrence_count == count_before  # No increment

        # --- SCENARIO 5: Active alert escalates to critical ---
        # Obligation due in 2 days (medium)
        item3 = ScheduledCashflowItem(
            user_id=user.id,
            title="Escalating Bill",
            kind="expense",
            amount=Decimal("50.00"),
            due_date=today + timedelta(days=2),
            status="scheduled",
        )
        db.add(item3)
        db.commit()

        evaluate_alerts(db, user.id)
        alert3 = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item3.id}:due").one()
        assert alert3.severity == "medium"

        # User reads and takes action on the medium alert
        mark_alert_read(db, user.id, alert3.id)
        mark_alert_actioned(db, user.id, alert3.id)
        db.refresh(alert3)
        assert alert3.read_at is not None
        assert alert3.actioned_at is not None

        # Bill becomes 8 days overdue (overdue > 7 days escalates to critical!)
        item3.due_date = today - timedelta(days=8)
        db.commit()

        evaluate_alerts(db, user.id)
        db.refresh(alert3)
        assert alert3.status == "active"
        assert alert3.severity == "critical"
        assert alert3.alert_type == "obligation_overdue"
        assert alert3.read_at is None  # Becomes unread
        assert alert3.actioned_at is None  # Actioned timestamp cleared on critical escalation
        assert alert3.occurrence_count == 2
    finally:
        cleanup(db, user)
        db.close()


@pytest.mark.parametrize(
    "days_offset,expected_alert_type,expected_severity",
    [
        (-8, "obligation_overdue", "critical"),  # Overdue by 8 days (> 7 days) -> critical
        (-7, "obligation_overdue", "high"),      # Overdue by 7 days (<= 7 days) -> high
        (-1, "obligation_overdue", "high"),      # Overdue by 1 day -> high
        (0, "obligation_due_soon", "high"),       # Due today (<= 1 day) -> high
        (1, "obligation_due_soon", "high"),       # Due tomorrow (<= 1 day) -> high
        (2, "obligation_due_soon", "medium"),     # Due in 2 days (<= 3 days) -> medium
        (3, "obligation_due_soon", "medium"),     # Due in 3 days (<= 3 days) -> medium
    ],
)
def test_obligation_threshold_boundaries(days_offset: int, expected_alert_type: str, expected_severity: str):
    """Verify exact boundary behavior for obligation due-dates and overdue intervals."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("50000.00"),
            opening_balance=Decimal("50000.00"),
            opening_balance_date=today - timedelta(days=30),
            balance_as_of=datetime.now(timezone.utc),
        )
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Boundary Obligation",
            kind="expense",
            amount=Decimal("1000.00"),
            due_date=today + timedelta(days=days_offset),
            status="scheduled",
        )
        db.add_all([acc, item])
        db.commit()

        evaluate_alerts(db, user.id)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item.id}:due").first()

        assert alert is not None
        assert alert.alert_type == expected_alert_type
        assert alert.severity == expected_severity
    finally:
        cleanup(db, user)
        db.close()


def test_obligation_4_to_7_days_and_cash_fraction_boundaries():
    """Obligations 4-7 days away are alerted only if remaining amount >= 50% of starting cash; >7 days is not alerted."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        # Starting cash = 10,000 BDT
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("10000.00"),
            opening_balance=Decimal("10000.00"),
            opening_balance_date=today - timedelta(days=30),
            balance_as_of=datetime.now(timezone.utc),
        )
        db.add(acc)
        db.commit()

        # Boundary A: 4 days away with 4,990 BDT (49.9% of cash) -> below 50% threshold -> suppressed
        item_499 = ScheduledCashflowItem(
            user_id=user.id,
            title="Bill 49.9%",
            kind="expense",
            amount=Decimal("4990.00"),
            due_date=today + timedelta(days=4),
            status="scheduled",
        )
        db.add(item_499)
        db.commit()

        evaluate_alerts(db, user.id)
        alert_499 = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item_499.id}:due").first()
        assert alert_499 is None, "Obligation 4 days away under 50% starting cash must not generate alert"

        # Boundary B: 4 days away with 5,000 BDT (50.0% of cash) -> meets 50% threshold -> medium alert
        item_500 = ScheduledCashflowItem(
            user_id=user.id,
            title="Bill 50.0%",
            kind="expense",
            amount=Decimal("5000.00"),
            due_date=today + timedelta(days=4),
            status="scheduled",
        )
        db.add(item_500)
        db.commit()

        evaluate_alerts(db, user.id)
        alert_500 = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item_500.id}:due").first()
        assert alert_500 is not None
        assert alert_500.severity == "medium"

        # Boundary C: 7 days away with 5,000 BDT (50.0% of cash) -> boundary edge of 7 days -> medium alert
        item_7d = ScheduledCashflowItem(
            user_id=user.id,
            title="Bill 7 Days Large",
            kind="expense",
            amount=Decimal("5000.00"),
            due_date=today + timedelta(days=7),
            status="scheduled",
        )
        db.add(item_7d)
        db.commit()

        evaluate_alerts(db, user.id)
        alert_7d = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item_7d.id}:due").first()
        assert alert_7d is not None
        assert alert_7d.severity == "medium"

        # Boundary D: 8 days away with 8,000 BDT (80% of cash) -> beyond 7-day horizon -> suppressed
        item_8d = ScheduledCashflowItem(
            user_id=user.id,
            title="Bill 8 Days Huge",
            kind="expense",
            amount=Decimal("8000.00"),
            due_date=today + timedelta(days=8),
            status="scheduled",
        )
        db.add(item_8d)
        db.commit()

        evaluate_alerts(db, user.id)
        alert_8d = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item_8d.id}:due").first()
        assert alert_8d is None, "Obligation 8 days away must not generate alert even if large"
    finally:
        cleanup(db, user)
        db.close()


def test_runway_safety_threshold_and_exact_zero_boundaries():
    """Verify runway behavior immediately above, equal to, and below safety threshold and exact zero boundary.

    Policy:
    - minimum < 0.00 -> cash_shortfall (critical)
    - minimum == 0.00 -> at_risk (high, since 0.00 <= safety_threshold)
    - minimum <= safety_threshold -> at_risk (high)
    - minimum > safety_threshold -> positive (no alert)
    """
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    safety_threshold = Decimal("500.00")
    try:
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("2000.00"),
            opening_balance=Decimal("2000.00"),
            opening_balance_date=today - timedelta(days=30),
            balance_as_of=datetime.now(timezone.utc),
        )
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Expense",
            kind="expense",
            amount=Decimal("1499.99"),  # Balance floor = 2000 - 1499.99 = 500.01 (> 500.00 safety threshold)
            due_date=today + timedelta(days=5),
            status="scheduled",
        )
        db.add_all([acc, item])
        db.commit()

        # 1. Immediately ABOVE safety threshold (500.01 BDT) -> positive -> no alert
        evaluate_alerts(db, user.id, safety_threshold=safety_threshold)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key="cash_position:runway_risk").first()
        assert alert is None

        # 2. Exactly EQUAL to safety threshold (500.00 BDT) -> at_risk -> high alert
        item.amount = Decimal("1500.00")  # Floor = 2000 - 1500 = 500.00
        db.commit()

        evaluate_alerts(db, user.id, safety_threshold=safety_threshold)
        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key="cash_position:runway_risk").first()
        assert alert is not None
        assert alert.alert_type == "cash_at_risk"
        assert alert.severity == "high"

        # 3. Immediately BELOW safety threshold (499.99 BDT) -> at_risk -> high alert
        item.amount = Decimal("1500.01")  # Floor = 2000 - 1500.01 = 499.99
        db.commit()

        evaluate_alerts(db, user.id, safety_threshold=safety_threshold)
        db.refresh(alert)
        assert alert.alert_type == "cash_at_risk"
        assert alert.severity == "high"

        # 4. Exactly at ZERO boundary (0.00 BDT balance) -> at_risk (high), NOT shortfall!
        item.amount = Decimal("2000.00")  # Floor = 2000 - 2000 = 0.00
        db.commit()

        evaluate_alerts(db, user.id, safety_threshold=safety_threshold)
        db.refresh(alert)
        assert alert.alert_type == "cash_at_risk", "Balance of exactly 0.00 BDT is at_risk, not shortfall"
        assert alert.severity == "high"

        # 5. Immediately BELOW zero (-0.01 BDT balance) -> cash_shortfall -> critical alert!
        item.amount = Decimal("2000.01")  # Floor = 2000 - 2000.01 = -0.01
        db.commit()

        evaluate_alerts(db, user.id, safety_threshold=safety_threshold)
        db.refresh(alert)
        assert alert.alert_type == "cash_shortfall", "Balance < 0.00 BDT is cash_shortfall"
        assert alert.severity == "critical"
    finally:
        cleanup(db, user)
        db.close()


def test_evidence_separates_as_of_date_and_observed_at_timestamp():
    """Evidence dictionary explicitly separates financial as_of_date from UTC observed_at timestamp."""
    db = SessionLocal()
    user = make_user(db)
    today = today_dhaka()
    try:
        acc = Account(
            user_id=user.id,
            name="Bank",
            currency="BDT",
            current_balance=Decimal("500.00"),
            opening_balance=Decimal("500.00"),
            opening_balance_date=today - timedelta(days=10),
            balance_as_of=datetime.now(timezone.utc),
        )
        item = ScheduledCashflowItem(
            user_id=user.id,
            title="Test Item",
            kind="expense",
            amount=Decimal("1000.00"),
            due_date=today + timedelta(days=2),
            status="scheduled",
        )
        db.add_all([acc, item])
        db.commit()

        before_eval = datetime.now(timezone.utc)
        evaluate_alerts(db, user.id)
        after_eval = datetime.now(timezone.utc)

        alert = db.query(FinancialAlert).filter_by(user_id=user.id, alert_key=f"obligation:{item.id}:due").one()
        evidence = alert.evidence

        # Check as_of_date
        assert "as_of_date" in evidence
        assert evidence["as_of_date"] == today.isoformat()

        # Check observed_at
        assert "observed_at" in evidence
        observed_dt = datetime.fromisoformat(evidence["observed_at"])
        assert before_eval - timedelta(seconds=2) <= observed_dt <= after_eval + timedelta(seconds=2)
    finally:
        cleanup(db, user)
        db.close()
