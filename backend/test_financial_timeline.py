"""AI-15E event scopes, deterministic ordering, and owner-scoped read-only API."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, ScheduledCashflowItem, Transaction
from app.schemas.timeline import FinancialTimeline
from app.services.finance.obligation_reconciliation import confirm, revoke
from app.services.finance.runway import financial_runway
from app.services.finance.timeline import financial_timeline
from backend.test_financial_runway import data, history, plan, transaction, AS_OF  # noqa: F401

D = Decimal


def read(data, **kw):
    db, users, _ = data
    return financial_timeline(db, users[0].id, as_of=AS_OF, **kw)


def select(result, kind):
    return [e for e in result.events if e.event_type == kind]


def test_actual_amount_fee_direction_source_and_cash_anchor(data):
    db, users, account = data
    tx = transaction(db, users[0], account, amount="-6000.25", fee=D("2.50"), merchant="Rent", category="Housing")
    result = read(data)
    actual = select(result, "transaction")[0]
    assert actual.amount == D("-6000.25")
    assert actual.balance_impact == D("-6002.75")
    assert actual.direction == "expense" and actual.certainty == "actual"
    assert actual.source_id == str(tx.id)
    assert actual.evidence.account_name == "Cash"
    assert actual.evidence.category == "Housing" and actual.evidence.fee == D("2.50")
    assert actual.impact_scope == "actual_history"
    assert result.starting_balance == D("23997.25")
    assert result.ending_projected_balance is None


@pytest.mark.parametrize("principal,direction", [("100.25", "income"), ("-100.25", "expense"), ("0", "neutral")])
def test_transaction_signs(data, principal, direction):
    db, users, account = data
    transaction(db, users[0], account, amount=principal)
    event = select(read(data), "transaction")[0]
    assert event.amount == D(principal)
    assert event.direction == direction


@pytest.mark.parametrize("payments,remaining", [([], "15000"), (["6000"], "9000"), (["4000", "6000.25"], "4999.75"), (["15000"], "0")])
def test_remaining_and_payment_metadata_never_duplicate_cash(data, payments, remaining):
    db, users, account = data
    item = plan(db, users[0])
    for amount in payments:
        tx = transaction(db, users[0], account, amount="-" + amount)
        confirm(db, users[0].id, item.id, tx.id)
    result = read(data)
    obligations = select(result, "obligation")
    assert sum((e.balance_impact for e in obligations), D("0")) == -D(remaining)
    assert len(obligations) == (1 if D(remaining) else 0)
    if obligations:
        assert obligations[0].original_amount == 15000
        assert obligations[0].allocated_amount == sum(map(D, payments), D("0"))
        assert obligations[0].remaining_amount == D(remaining)
    metadata = select(result, "obligation_payment")
    assert len(metadata) == len(payments)
    for event in metadata:
        assert event.certainty == "confirmed"
        assert event.balance_impact == 0 and not event.cash_impacting
        assert event.impact_scope == "context"
        assert event.evidence.transaction_id in {e.evidence.transaction_id for e in select(result, "transaction")}
        assert event.evidence.obligation_id == item.id
    assert result.starting_balance - D(remaining) == 15000
    assert db.query(Transaction).count() == len(payments)
    assert item.amount == 15000


def test_candidates_revoked_and_manual_terminal_records(data):
    db, users, account = data
    item = plan(db, users[0])
    tx = transaction(db, users[0], account, amount="-6000")
    assert select(read(data), "obligation")[0].remaining_amount == 15000
    assert not select(read(data), "obligation_payment")
    confirm(db, users[0].id, item.id, tx.id)
    revoke(db, users[0].id, item.id, tx.id)
    assert select(read(data), "obligation")[0].remaining_amount == 15000
    assert not select(read(data), "obligation_payment")
    for status in ["paid", "cancelled"]:
        item.status = status; db.commit()
        assert not select(read(data), "obligation")
    assert select(read(data), "transaction")[0].amount == -6000


def test_paid_full_allocation_retains_payment_context(data):
    db, users, account = data
    item = plan(db, users[0])
    tx = transaction(db, users[0], account, amount="-15000")
    confirm(db, users[0].id, item.id, tx.id, full=True)
    result = read(data)
    assert not select(result, "obligation")
    assert select(result, "obligation_payment")[0].remaining_amount == 0
    assert result.starting_balance == 15000


def test_uncertain_income_and_overdue_context(data):
    db, users, _ = data
    plan(db, users[0], kind="income", amount="30000")
    plan(db, users[0], amount="500", due=AS_OF - timedelta(days=1))
    result = read(data)
    overdue, income = sorted(select(result, "obligation"), key=lambda e: e.direction)
    assert income.certainty == "uncertain" and income.balance_impact == 0
    assert overdue.status == "overdue" and overdue.balance_impact == 0
    assert all(e.impact_scope == "context" for e in [income, overdue])


@pytest.mark.parametrize("scheduled", ["500", "1500", "4000"])
def test_forecast_attribution_reuses_runway_and_does_not_add_bills_twice(data, scheduled):
    db, users, _ = data
    history(db, users[0], income="3000", expense="1500")
    plan(db, users[0], amount=scheduled, due=AS_OF + timedelta(days=3))
    end = date(2026, 11, 30)
    result = read(data, start_date=AS_OF, end_date=end)
    runway = financial_runway(db, users[0].id, as_of=AS_OF, horizon_days=29)
    income = select(result, "forecast_income")[0]
    expense = select(result, "forecast_expense")[0]
    checkpoint = select(result, "runway_checkpoint")[0]
    assert income.amount == runway.checkpoints[0].forecast_income == runway.forecast_income
    assert expense.amount == runway.checkpoints[0].forecast_expense == runway.forecast_expense
    assert expense.balance_impact == -(runway.expected_expense_reserve - D(scheduled))
    assert expense.evidence.period.start == AS_OF
    assert checkpoint.evidence.projected_balance == runway.projected_end_balance
    assert checkpoint.evidence.minimum_balance == runway.minimum_projected_balance
    assert checkpoint.balance_impact == 0 and checkpoint.impact_scope == "context"
    impacts = sum((e.balance_impact for e in result.events if e.impact_scope == "future_projection"), D("0"))
    assert result.starting_balance + impacts == result.ending_projected_balance == runway.projected_end_balance
    assert all(e.certainty == "estimated" for e in [income, expense, checkpoint])


def test_opening_actual_allocation_remaining_and_forecast_regression(data):
    db, users, account = data
    history(db, users[0])
    item = plan(db, users[0])
    tx = transaction(db, users[0], account, amount="-6000")
    confirm(db, users[0].id, item.id, tx.id)
    result = read(data, end_date=date(2026, 11, 30))
    assert result.starting_balance == 24000
    projected = sum((e.balance_impact for e in result.events if e.impact_scope == "future_projection"), D("0"))
    assert result.starting_balance + projected == result.ending_projected_balance == 17000
    assert sum(e.balance_impact for e in select(result, "obligation_payment")) == 0


def test_insufficient_history_and_unknown_cash_do_not_fabricate_forecasts(data):
    db, users, account = data
    plan(db, users[0])
    assert not select(read(data), "forecast_income")
    assert not select(read(data), "runway_checkpoint")
    assert select(read(data), "obligation")
    account.opening_balance = account.opening_balance_date = None; db.commit()
    history(db, users[0])
    result = read(data)
    assert result.starting_balance is result.ending_projected_balance is None
    assert not select(result, "forecast_expense")


def test_ordering_is_stable_by_day_priority_and_numeric_source(data):
    db, users, account = data
    first = transaction(db, users[0], account, amount="-10")
    second = transaction(db, users[0], account, amount="-20")
    item = plan(db, users[0], amount="100")
    confirm(db, users[0].id, item.id, first.id)
    result = read(data)
    assert [e.event_type for e in result.events] == ["transaction", "transaction", "obligation_payment", "obligation"]
    assert [e.source_id for e in select(result, "transaction")] == [str(first.id), str(second.id)]
    assert result.model_dump(mode="json") == read(data).model_dump(mode="json")
    assert len({e.id for e in result.events}) == len(result.events)


def test_foreign_users_and_account_metadata_do_not_leak(data):
    db, users, account = data
    tx = transaction(db, users[0], account, amount="-100")
    foreign = Account(user_id=users[1].id, name="Private account", current_balance=D("99999"))
    db.add(foreign); db.commit()
    transaction(db, users[1], foreign, amount="99999", merchant="Private")
    plan(db, users[1], amount="99999")
    # A malformed account link must not expose the foreign account's name/currency.
    transaction(db, users[0], foreign, amount="99999")
    result = read(data)
    assert [e.source_id for e in select(result, "transaction")] == [str(tx.id)]
    assert "Private" not in result.model_dump_json()
    assert not select(result, "obligation")


def test_foreign_currency_actual_retains_native_values_without_bdt_projection(data):
    db, users, _ = data
    usd = Account(user_id=users[0].id, name="USD account", currency="USD")
    db.add(usd); db.commit()
    transaction(db, users[0], usd, amount="-10", fee=D("1"))
    result = read(data)
    actual = select(result, "transaction")[0]
    assert actual.currency == "USD" and actual.balance_impact == -11
    assert actual.impact_scope == "actual_history"
    assert result.starting_balance == 30000


def test_date_filters_future_actuals_and_historical_only_windows(data):
    db, users, account = data
    transaction(db, users[0], account, day=AS_OF - timedelta(days=2))
    transaction(db, users[0], account, day=AS_OF - timedelta(days=1))
    transaction(db, users[0], account, day=AS_OF + timedelta(days=1))
    result = read(data, start_date=AS_OF - timedelta(days=1), end_date=AS_OF - timedelta(days=1))
    assert len(result.events) == 1
    assert result.starting_balance is result.projection_period is None
    assert result.events[0].date == AS_OF - timedelta(days=1)
    assert len(select(read(data), "transaction")) == 2


def test_hide_estimates_crops_events_without_changing_projection(data):
    db, users, _ = data
    history(db, users[0])
    full = read(data)
    hidden = read(data, include_estimates=False)
    assert hidden.ending_projected_balance == full.ending_projected_balance
    assert not any(e.certainty == "estimated" for e in hidden.events)


def test_empty_unknown_and_read_only(data):
    db, users, _ = data
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = financial_timeline(db, users[1].id, as_of=AS_OF)
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert result.events == [] and result.starting_balance is None
    assert set(result.event_counts.values()) == {0}
    assert not {"INSERT", "UPDATE", "DELETE"} & set(statements)
    FinancialTimeline.model_validate_json(result.model_dump_json())


def test_api_auth_ranges_serialization_and_repeatability(data, monkeypatch):
    db, users, account = data
    monkeypatch.setattr("app.services.finance.timeline.today_dhaka", lambda: AS_OF)
    transaction(db, users[0], account, amount="-10.25")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            assert client.get("/finance/timeline").status_code == 401
            app.dependency_overrides[get_current_user] = lambda: users[0]
            for params in [{"start_date": "bad"}, {"start_date": "2026-11-02", "end_date": "2026-11-01"}, {"end_date": "2030-01-01"}, {"start_date": "2000-01-01"}]:
                assert client.get("/finance/timeline", params=params).status_code == 422
            response = client.get("/finance/timeline")
            assert response.status_code == 200
            assert response.json() == client.get("/finance/timeline").json()
            assert response.json()["events"][0]["amount"] == "-10.25"
            assert response.json()["ending_projected_balance"] is None
            assert client.get("/finance/timeline", params={"start_date": "2026-10-01", "end_date": "2026-10-31"}).json()["events"] == []
            app.dependency_overrides[get_current_user] = lambda: users[1]
            assert client.get("/finance/timeline").json()["events"] == []
    finally:
        app.dependency_overrides.clear()


def test_payment_relationship_uses_transaction_date_when_due_date_is_outside_window(data):
    db, users, account = data
    item = plan(db, users[0], due=AS_OF + timedelta(days=60))
    tx = transaction(db, users[0], account, amount="-6000")
    confirm(db, users[0].id, item.id, tx.id)
    result = read(data)
    assert not select(result, "obligation")
    assert select(result, "obligation_payment")[0].date == tx.date
    assert result.event_counts["actual"] == result.event_counts["confirmed"] == 1


def test_multimonth_forecast_segments_reuse_amounts_and_priority(data):
    db, users, account = data
    history(db, users[0])
    plan(db, users[0], amount="500", due=date(2026, 11, 30))
    result = read(data, start_date=AS_OF, end_date=date(2026, 12, 1))
    runway = financial_runway(db, users[0].id, as_of=AS_OF, horizon_days=30)
    assert sum(e.amount for e in select(result, "forecast_income")) == runway.forecast_income
    assert sum(e.amount for e in select(result, "forecast_expense")) == runway.forecast_expense
    assert [e.event_type for e in result.events if e.date == date(2026, 11, 30)] == ["obligation", "forecast_expense", "forecast_income", "runway_checkpoint"]
    impacts = sum((e.balance_impact for e in result.events if e.impact_scope == "future_projection"), D("0"))
    assert result.starting_balance + impacts == runway.projected_end_balance
