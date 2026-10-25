"""Deterministic coaching over scoped SQL aggregates; no raw-history retrieval."""
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from hashlib import sha256
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_
from app.models.transactions import Transaction
from app.models.account import Account
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.savings_goal import SavingsGoal
from app.schemas.coach import Coverage
from app.schemas.spending_decision import SpendingDecisionRequest
from app.services.finance.spending_decision import assess_spending_decision
from app.services.forecasting.cashflow import calculate_cashflow_forecast

ZERO = Decimal("0.00")
LIMITATIONS = [
    "Imported records may be incomplete; observed totals are not proof of full coverage.",
    "No trustworthy current account balance is inferred from transaction history.",
    "Account-linked records are included only for this user's BDT accounts; unlinked imported records are assumed BDT.",
]


def today_dhaka():
    return datetime.now(ZoneInfo("Asia/Dhaka")).date()


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_shift(value, offset):
    index = value.year * 12 + value.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def scoped(db, user_id, start, end):
    if user_id <= 0 or start > end:
        raise ValueError("Invalid financial query scope")
    owned_bdt_accounts = db.query(Account.id).filter(Account.user_id == user_id, Account.currency == "BDT")
    return db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.date >= start, Transaction.date <= end,
        or_(Transaction.account_id.is_(None), Transaction.account_id.in_(owned_bdt_accounts)),
    )


def totals(db, user_id, start, end, category=None):
    query = scoped(db, user_id, start, end)
    if category:
        query = query.filter(func.lower(Transaction.category) == category.lower())
    count, first, last, income, expenses = query.with_entities(
        func.count(Transaction.id), func.min(Transaction.date), func.max(Transaction.date),
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
        func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)),
    ).one()
    coverage = Coverage(start_date=start, end_date=end, transaction_count=count,
                        first_transaction_date=first, last_transaction_date=last,
                        limitations=LIMITATIONS)
    return {"income": money(income) if count else None,
            "expenses": money(expenses) if count else None,
            "net": money(income - expenses) if count else None,
            "coverage": coverage.model_dump(mode="json")}


def grouped_expenses(db, user_id, start, end, group="category", limit=10):
    column = Transaction.category if group == "category" else Transaction.merchant
    label = func.coalesce(column, "Uncategorized" if group == "category" else "Unknown merchant")
    amount = func.sum(-Transaction.amount)
    rows = scoped(db, user_id, start, end).filter(Transaction.amount < 0).with_entities(
        label, amount, func.count(Transaction.id),
    ).group_by(label).order_by(amount.desc(), label.asc()).limit(limit).all()
    return [{group: name, "expenses": money(total), "transaction_count": count} for name, total, count in rows]


def history(db, user_id, as_of):
    start = month_shift(as_of, -3)
    end = as_of.replace(day=1) - timedelta(days=1)
    monthly = []
    records = []
    for offset in range(3):
        first = month_shift(start, offset)
        last = month_shift(first, 1) - timedelta(days=1)
        values = totals(db, user_id, first, last)
        monthly.append(values)
        if values["income"] is not None:
            records.extend([SimpleNamespace(date=last, amount=values["income"]),
                            SimpleNamespace(date=last, amount=-values["expenses"])])
    adequate = all(item["coverage"]["transaction_count"] > 0 for item in monthly)
    # Reuse the existing Decimal forecast with monthly aggregate records only.
    baseline = calculate_cashflow_forecast(records, ZERO, months_ahead=1, as_of_date=as_of)
    return {"monthly": monthly, "adequate": adequate, "baseline": baseline,
            "coverage": totals(db, user_id, start, end)["coverage"]}


def scheduled_totals(db, user_id, start, end):
    rows = db.query(ScheduledCashflowItem.kind, func.sum(ScheduledCashflowItem.amount)).filter(
        ScheduledCashflowItem.user_id == user_id,
        ScheduledCashflowItem.status == "scheduled",
        ScheduledCashflowItem.due_date >= start, ScheduledCashflowItem.due_date <= end,
    ).group_by(ScheduledCashflowItem.kind).all()
    values = {kind: money(amount) for kind, amount in rows}
    return values.get("expense", ZERO), values.get("income", ZERO)


def recommendations(db, user_id, as_of=None, history_data=None):
    as_of = as_of or today_dhaka()
    h = history_data or history(db, user_id, as_of)
    items = []
    if h["adequate"]:
        latest_start = month_shift(as_of, -1)
        latest_end = month_shift(as_of, 0) - timedelta(days=1)
        previous_start = month_shift(as_of, -2)
        previous_end = latest_start - timedelta(days=1)
        latest = grouped_expenses(db, user_id, latest_start, latest_end, limit=1000)
        previous = {row["category"]: row["expenses"] for row in grouped_expenses(db, user_id, previous_start, previous_end, limit=1000)}
        # Essential categories are not assumed reducible. One opportunity per category.
        for row in latest:
            category, spending = row["category"], row["expenses"]
            if category not in {"Food", "Shopping", "Entertainment", "Subscription", "Travel"}:
                continue
            prior = previous.get(category)
            if prior is None or prior <= 0 or spending <= prior * Decimal("1.10"):
                continue
            saving = money(min(spending * Decimal("0.10"), spending - prior))
            if saving <= 0:
                continue
            key = sha256(category.encode()).hexdigest()[:12]
            items.append({"id": f"review-category:{latest_start:%Y-%m}:{key}",
                          "category": category, "title": f"Review increased {category} spending",
                          "evidence": {"period_start": str(latest_start), "period_end": str(latest_end),
                                       "latest_expenses": str(spending), "previous_expenses": str(prior)},
                          "estimated_monthly_saving": saving, "estimated_annual_saving": money(saving * 12),
                          "confidence": "low", "assumptions": [
                              "Consider a reduction of up to 10% only if feasible; essential needs come first.",
                              "Annual impact assumes the same optional reduction for twelve months; it is not guaranteed."]})
    items.sort(key=lambda row: (-row["estimated_monthly_saving"], row["id"]))
    return {"coverage": h["coverage"], "recommendations": items[:5],
            "limitations": LIMITATIONS + (["Three complete calendar months with observed records are required; missing months are unknown."] if not h["adequate"] else [])}


def coach_cashflow(db, user_id, request, as_of=None):
    as_of = as_of or today_dhaka()
    h = history(db, user_id, as_of)
    income = h["baseline"]["average_monthly_income"] if h["adequate"] else None
    expense = h["baseline"]["average_monthly_expenses"] if h["adequate"] else None
    projected = request.starting_balance
    no_income = request.starting_balance
    months = []
    for offset in range(request.months_ahead):
        start = as_of if offset == 0 else month_shift(as_of, offset)
        end = month_shift(as_of, offset + 1) - timedelta(days=1)
        planned_expenses, planned_income = scheduled_totals(db, user_id, start, end)
        fraction = Decimal((end - start).days + 1) / Decimal(monthrange(start.year, start.month)[1])
        historical_income = money(income * fraction) if income is not None else None
        historical_expense = money(expense * fraction) if expense is not None else None
        reserve = max(historical_expense or ZERO, planned_expenses)
        projected = money(projected + (historical_income or ZERO) - reserve)
        no_income = money(no_income - reserve)
        months.append({"month": start.strftime("%Y-%m"), "historical_income_estimate": historical_income,
                       "historical_expense_estimate": historical_expense, "scheduled_expenses": planned_expenses,
                       "uncertain_scheduled_income": planned_income, "reserved_expenses": reserve,
                       "projected_balance": projected if h["adequate"] else None,
                       "balance_without_future_income": no_income})
    return {"as_of_date": as_of, "starting_balance": request.starting_balance, "months": months,
            "coverage": h["coverage"], "assumptions": [
                "Starting balance is caller-confirmed, not a bank-reconciled balance.",
                "Current-month estimates are prorated by remaining calendar days; later months use historical averages.",
                "Each month reserves the larger of estimated historical expenses and scheduled expenses to avoid adding overlapping bills twice.",
                "Schedules may omit other spending; the maximum is a scenario assumption, not reconciliation.",
                "Scheduled income is uncertain and is displayed separately, never added to projected balances.",
                "Paid and cancelled plans are excluded; paid plans never become actual transactions.",
                "Overdue scheduled records need review and are not assumed still payable in this future scenario."],
            "limitations": LIMITATIONS + (["Insufficient history: only the known-obligations scenario is available."] if not h["adequate"] else ["Historical income is an estimate, not guaranteed income."])}


def coach_purchase(db, user_id, request, as_of=None):
    as_of = as_of or today_dhaka()
    end = as_of + timedelta(days=request.horizon_days)
    reserve, uncertain = scheduled_totals(db, user_id, as_of, end)
    base = assess_spending_decision(SpendingDecisionRequest(
        purchase_amount=request.purchase_amount, starting_balance=request.starting_balance,
        safety_buffer=request.safety_buffer + reserve))
    return {"status": "not_recommended" if request.starting_balance - request.purchase_amount - reserve < 0 else base.status, "purchase_amount": request.purchase_amount,
            "scheduled_expense_reserve": reserve,
            "remaining_after_purchase_and_reserve": money(request.starting_balance - request.purchase_amount - reserve),
            "uncertain_scheduled_income": uncertain, "horizon_end": end,
            "assumptions": ["Caller confirms the available balance and safety buffer.",
                            "Scheduled expenses in the inclusive horizon are reserved; scheduled income is excluded.",
                            "The purchase is assumed additional to scheduled expenses."],
            "warnings": ["This checks known plans only; unrecorded expenses, overdue bills, and future purchases may make it unaffordable.",
                         "No income projection is treated as money available today."]}


def goal_plan(db, user_id, goal, as_of=None, history_data=None):
    as_of = as_of or today_dhaka()
    h = history_data or history(db, user_id, as_of)
    remaining = money(max(ZERO, goal.target_amount - goal.current_saved)) if goal.current_saved is not None else None
    days = max(1, (goal.target_date - as_of).days)
    weeks = (days + 6) // 7
    months = max(1, (goal.target_date.year - as_of.year) * 12 + goal.target_date.month - as_of.month + 1)
    weekly = (remaining / weeks).quantize(Decimal("0.01"), rounding=ROUND_UP) if remaining is not None else None
    monthly = (remaining / months).quantize(Decimal("0.01"), rounding=ROUND_UP) if remaining is not None else None
    capacity = None
    limitations = list(LIMITATIONS)
    if h["adequate"]:
        next_end = month_shift(as_of, 1) - timedelta(days=1)
        obligations, _ = scheduled_totals(db, user_id, as_of, next_end)
        capacity = money(h["baseline"]["average_monthly_income"] - max(h["baseline"]["average_monthly_expenses"], obligations))
        others = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id, SavingsGoal.status == "active", SavingsGoal.id != goal.id).all()
        for other in others:
            if other.current_saved is None:
                capacity = None
                limitations.append("Another active goal has unknown savings, so shared affordability cannot be assessed.")
                break
            other_months = max(1, (other.target_date.year - as_of.year) * 12 + other.target_date.month - as_of.month + 1)
            capacity -= (max(ZERO, other.target_amount - other.current_saved) / other_months).quantize(Decimal("0.01"), rounding=ROUND_UP)
    status = "unknown"
    if goal.status == "cancelled":
        status = "cancelled"
    elif remaining == 0:
        status = "completed"
    elif goal.target_date < as_of:
        status = "overdue"
    elif monthly is not None and capacity is not None:
        status = "appears_feasible" if capacity >= monthly else "at_risk"
    if remaining is None:
        limitations.append("Current goal savings are unknown; report them explicitly to calculate contributions.")
    if not h["adequate"]:
        limitations.append("Three complete calendar months with observed records are needed to estimate affordability.")
    return {"goal_id": goal.id, "as_of_date": as_of, "remaining_amount": remaining,
            "required_weekly": weekly, "required_monthly": monthly, "estimated_monthly_capacity": capacity,
            "affordability": status, "assumptions": [
                "Saved amounts are user-reported and not reconciled with account balances.",
                "Contribution counts round up remaining weeks and include the target calendar month; cents round up.",
                "Historical surplus is an estimate; scheduled income is not guaranteed or added.",
                "Known current-month obligations and other active goals reduce the estimated capacity."],
            "limitations": limitations}


def nudges(db, user_id, as_of=None):
    as_of = as_of or today_dhaka()
    end = as_of + timedelta(days=30)
    items = []
    upcoming = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.user_id == user_id, ScheduledCashflowItem.kind == "expense",
        ScheduledCashflowItem.status == "scheduled", ScheduledCashflowItem.due_date >= as_of,
        ScheduledCashflowItem.due_date <= end,
    ).order_by(ScheduledCashflowItem.due_date, ScheduledCashflowItem.id).limit(20).all()
    for item in upcoming:
        items.append({"key": f"scheduled-expense:{item.id}:{item.due_date}", "type": "upcoming_expense",
                      "severity": "warning", "title": "Plan for an upcoming expense",
                      "evidence": {"scheduled_item_id": item.id, "title": item.title, "amount": str(item.amount), "record_type": "plan"},
                      "period_start": as_of, "period_end": item.due_date,
                      "expires_on": item.due_date + timedelta(days=1), "next_action": "Review the plan and reserve funds; it is not an actual transaction."})
    h = history(db, user_id, as_of)
    recs = recommendations(db, user_id, as_of, history_data=h)
    expiry = month_shift(as_of, 1)
    for rec in recs["recommendations"]:
        items.append({"key": rec["id"], "type": "savings_opportunity", "severity": "info", "title": rec["title"],
                      "evidence": {**rec["evidence"], "estimated_monthly_saving": str(rec["estimated_monthly_saving"])},
                      "period_start": month_shift(as_of, -1), "period_end": as_of.replace(day=1) - timedelta(days=1),
                      "expires_on": expiry, "next_action": "Review whether a small reduction is feasible; estimated savings are not guaranteed."})
    if h["adequate"]:
        current = totals(db, user_id, as_of.replace(day=1), as_of)
        ceiling = max(row["expenses"] for row in h["monthly"])
        if current["expenses"] is not None and ceiling > 0 and current["expenses"] > ceiling * Decimal("1.5"):
            items.append({"key": f"unusual-spending:{as_of:%Y-%m}", "type": "unusual_spending", "severity": "warning",
                          "title": "Recorded spending exceeds your recent range",
                          "evidence": {"current_expenses": str(current["expenses"]), "largest_prior_month": str(ceiling)},
                          "period_start": as_of.replace(day=1), "period_end": as_of, "expires_on": expiry,
                          "next_action": "Check imports and large purchases before changing your budget."})
        if h["baseline"]["average_monthly_net"] < 0:
            items.append({"key": f"estimated-deficit:{as_of:%Y-%m}", "type": "projected_shortfall", "severity": "warning",
                          "title": "Historical averages suggest a monthly deficit",
                          "evidence": {"estimated_monthly_net": str(h["baseline"]["average_monthly_net"]), "is_estimate": True},
                          "period_start": as_of, "period_end": expiry - timedelta(days=1), "expires_on": expiry,
                          "next_action": "Review the cashflow scenario using a confirmed balance; this is not a predicted bank balance."})
    for goal in db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id, SavingsGoal.status == "active").order_by(SavingsGoal.target_date, SavingsGoal.id).limit(20):
        plan = goal_plan(db, user_id, goal, as_of, history_data=h)
        items.append({"key": f"goal-progress:{goal.id}:{as_of:%Y-%m}", "type": "goal_progress",
                      "severity": "warning" if plan["affordability"] in {"at_risk", "overdue"} else "info",
                      "title": "Review your savings goal", "evidence": {"goal_id": goal.id, "name": goal.name,
                          "saved_source": "user_reported", "current_saved": str(goal.current_saved) if goal.current_saved is not None else None,
                          "affordability": plan["affordability"]},
                      "period_start": as_of, "period_end": goal.target_date, "expires_on": expiry,
                      "next_action": "Confirm savings progress and review the contribution plan."})
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    unique = {item["key"]: item for item in items if item["expires_on"] > as_of}
    return {"as_of_date": as_of, "insights": sorted(unique.values(), key=lambda item: (severity_order[item["severity"]], item["key"]))[:30],
            "limitations": LIMITATIONS + ["Insights are recomputed active observations with stable keys; they expire or disappear when evidence changes. Dismissal is not persisted."]}
