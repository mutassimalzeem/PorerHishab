"""One read-only cash-position engine. Allocation metadata never becomes cashflow."""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from app.models.account import Account
from app.schemas.runway import FinancialRunway, RunwayMode
from app.services.finance.account_reconciliation import reconcile_account_balance
from app.services.intelligence.facts import scheduled_obligation_values
from app.services.intelligence.periods import Period, money, month_end, today_dhaka
from app.services.intelligence.snapshot import monthly_history

ZERO = Decimal("0.00")
DEFAULT_SAFETY_THRESHOLD = ZERO


def cash_position(db, user_id, as_of):
    """All owned BDT accounts must be known; never sum a misleading subset."""
    accounts = db.query(Account).filter_by(user_id=user_id, currency="BDT").order_by(Account.id).all()
    rows = [reconcile_account_balance(db, account=a, user_id=user_id, as_of=as_of) for a in accounts]
    reported = sum((r["reported_balance"] for r in rows), ZERO) if rows and all(r["reported_balance"] is not None for r in rows) else None
    derived = sum((r["derived_balance"] for r in rows), ZERO) if rows and all(r["derived_balance"] is not None for r in rows) else None
    values, sources, confidences = [], set(), []
    for row in rows:
        if row["status"] in {"mismatch", "unreconciled"} or row["difference"] not in {None, ZERO}:
            return None, reported, derived, "unknown", "unknown"
        value = row["derived_balance"]
        source = "reconciled" if row["status"] == "reconciled" else "derived"
        if value is None:
            value, source = row["reported_balance"], "reported"
        if value is None:
            return None, reported, derived, "unknown", "unknown"
        values.append(value)
        sources.add(source)
        confidences.append(row["confidence"])
    if not values:
        return None, reported, derived, "unknown", "unknown"
    confidence = "high" if all(c == "high" for c in confidences) else "low" if "low" in confidences else "medium"
    return money(sum(values, ZERO)), reported, derived, next(iter(sources)) if len(sources) == 1 else "mixed", confidence


def financial_runway(db, user_id, *, as_of=None, horizon_days=30,
                     safety_threshold=DEFAULT_SAFETY_THRESHOLD, mode: RunwayMode = "historical",
                     starting_balance=None, history=None):
    """Monthly historical estimate, or explicitly limited dated-obligations scenario.

    Caller balance is for existing coach APIs only; known account cash caps it.
    Historical minima assume expenses precede income within each month, so no
    precise depletion day can be inferred from monthly averages.
    """
    as_of = as_of or today_dhaka()
    if user_id <= 0 or not 1 <= horizon_days <= 366 or mode not in {"historical", "known_obligations"}:
        raise ValueError("Invalid runway scope")
    if not isinstance(safety_threshold, Decimal) or not safety_threshold.is_finite() or safety_threshold < ZERO:
        raise ValueError("Invalid safety threshold")
    if starting_balance is not None and (not isinstance(starting_balance, Decimal) or not starting_balance.is_finite()):
        raise ValueError("Starting balance must be finite Decimal")
    end = as_of + timedelta(days=horizon_days)
    period = Period(kind="runway_horizon", start=as_of, end=end, is_complete=False, label=f"next {horizon_days} days (inclusive)")
    balance, reported, derived, source, confidence = cash_position(db, user_id, as_of)
    limitations = [
        "Scheduled income is uncertain and never added to projected cash.",
        "Imported history, account reports and schedules may be incomplete or stale; pending transfers and unrecorded spending are unknown.",
        "Overdue obligations are excluded, following the existing future-scenario convention.",
        "As-of selects transaction and due-date windows, not historical allocation/report versions; allocations reflect current confirmed state.",
    ]
    if starting_balance is not None:
        balance = min(balance, starting_balance) if balance is not None else starting_balance
        source, confidence = "caller", "low"
        limitations.append("Caller-confirmed cash is capped by established account cash when available; account conflicts cannot validate the caller report.")
    values = scheduled_obligation_values(db, user_id, as_of, end)
    expenses = sum((v.reserved_amount for item, v in values if item.kind == "expense"), ZERO)
    income = sum((v.remaining_amount for item, v in values if item.kind == "income"), ZERO)
    payload = dict(period=period.to_dict(), mode=mode, starting_balance=balance,
                   reported_balance=reported, derived_balance=derived, balance_source=source,
                   known_future_income=income, scheduled_expense_reserve=expenses,
                   forecast_income=None, forecast_expense=None, expected_expense_reserve=None,
                   known_obligations_end_balance=money(balance - expenses) if balance is not None else None,
                   projected_end_balance=None, minimum_projected_balance=None,
                   safety_threshold=safety_threshold, runway_status="insufficient_data",
                   runway_days=None, first_shortfall_date=None, first_shortfall_period=None,
                   confidence="unknown", checkpoints=[], assumptions=[
                       "All amounts are BDT; foreign-currency accounts are excluded without conversion.",
                       "Allocations are reconciliation metadata, not transactions.",
                       "The safety threshold is user-configurable and defaults to zero BDT; at or below it is at risk.",
                       "The start and end dates are included; starting cash already includes actual transactions through as-of.",
                   ], limitations=limitations)
    if balance is None:
        limitations.append("Starting cash is unavailable: no BDT accounts, an unknown account balance, or a reconciliation mismatch. No partial account sum is substituted.")
        return FinancialRunway(**payload)
    current, minimum = balance, balance
    first_date = as_of if balance < ZERO else None
    first_period = period if balance < ZERO else None
    checkpoints = []
    forecast_income = forecast_expense = reserved = ZERO
    if mode == "known_obligations":
        limitations.append("Known-obligations-only scenario: no general spending or income forecast; a positive result is not a complete affordability assessment.")
        for item, amount in values:
            if item.kind != "expense":
                continue
            current = money(current - amount.reserved_amount)
            minimum = min(minimum, current)
            if first_date is None and current < ZERO:
                first_date = item.due_date
            checkpoints.append(dict(date=item.due_date, projected_balance=current, minimum_balance=minimum))
        reserved = expenses
        confidence = "low"
    else:
        history = history or monthly_history(db, user_id, as_of)
        if not history.adequate or history.baseline["status"] == "insufficient_data":
            limitations.append("Three complete prior months with usable observed activity are required for a historical runway; known obligations are still shown separately.")
            return FinancialRunway(**payload)
        start = as_of
        while start <= end:
            stop = min(month_end(start), end)
            fraction = Decimal((stop - start).days + 1) / Decimal(monthrange(start.year, start.month)[1])
            estimate_income = money(history.baseline["average_monthly_income"] * fraction)
            estimate_expense = money(history.baseline["average_monthly_expenses"] * fraction)
            scheduled = sum((v.reserved_amount for item, v in values if item.kind == "expense" and start <= item.due_date <= stop), ZERO)
            reserve = max(estimate_expense, scheduled)
            floor = money(current - reserve)
            minimum = min(minimum, floor)
            current = money(floor + estimate_income)
            if first_period is None and floor < ZERO:
                first_period = Period(kind="estimated_shortfall_window", start=start, end=stop, is_complete=False, label="expenses before estimated income")
            checkpoints.append(dict(date=stop, projected_balance=current, minimum_balance=floor))
            forecast_income += estimate_income
            forecast_expense += estimate_expense
            reserved += reserve
            start = stop + timedelta(days=1)
        limitations.append("Historical forecasts have monthly resolution. Minima conservatively place each segment's expenses before its income; an exact depletion date or runway day count is unavailable.")
        payload["assumptions"].append("Each calendar-month segment reserves max(prorated historical expense, remaining scheduled expenses), preserving the existing overlap assumption.")
    status = "cash_shortfall" if minimum < ZERO else "at_risk" if minimum <= safety_threshold else "positive"
    payload.update(projected_end_balance=current, minimum_projected_balance=minimum,
                   forecast_income=forecast_income, forecast_expense=forecast_expense,
                   expected_expense_reserve=reserved, runway_status=status, confidence=confidence,
                   checkpoints=checkpoints,
                   first_shortfall_date=first_date if mode == "known_obligations" else None,
                   runway_days=(first_date - as_of).days if mode == "known_obligations" and first_date is not None else None,
                   first_shortfall_period=(first_period.to_dict() if first_period is not None else None) if mode == "historical" else None)
    return FinancialRunway(**payload)
