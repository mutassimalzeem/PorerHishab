"""Deterministic coaching presentation over the AI-13 intelligence engine.

Refactor note (AI-13): the shared aggregates — scoped queries, totals,
grouped expenses, scheduled totals, period helpers, the monthly-average
baseline and every signal rule — now live in
``app.services.intelligence``; the coach consumes the same engine the other
consumers do and only shapes product-facing responses (titles, status
codes, expiry dates, assumptions/limitations copy). Amounts, thresholds,
rounding and stable keys are unchanged from the AI-09..AI-12E behaviour:
the offline evaluation suites keep pinning them.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_UP
from types import SimpleNamespace

from app.schemas.spending_decision import SpendingDecisionRequest
from app.services.finance.spending_decision import assess_spending_decision
from app.services.intelligence.categories import comparison_expenses_by_category
from app.services.intelligence.facts import (
    LIMITATIONS,
    grouped_expenses,
    scheduled_totals,
    scoped,
    totals,
)
from app.services.intelligence.goals import goal_assessment
from app.services.intelligence.periods import (
    month_shift,
    money,
    previous_complete_month_period,
    today_dhaka,
)
from app.services.intelligence.signals import (
    REDUCIBLE_CATEGORIES,
    build_signals,
    savings_opportunity_signals,
)
from app.services.intelligence.snapshot import monthly_history

ZERO = Decimal("0.00")

INSUFFICIENT_HISTORY_NOTE = (
    "Three complete calendar months with observed records are required; missing months are unknown."
)

__all__ = [
    "LIMITATIONS", "money", "month_shift", "today_dhaka", "ZERO",
    "scoped", "totals", "grouped_expenses", "scheduled_totals",
    "history", "recommendations", "coach_cashflow", "coach_purchase",
    "goal_plan", "nudges", "REDUCIBLE_CATEGORIES",
]


def history(db, user_id, as_of=None):
    """Coach-shaped complete-month history, computed by the engine."""
    as_of = as_of or today_dhaka()
    payload = monthly_history(db, user_id, as_of)
    return {
        "monthly": payload.monthly,
        "adequate": payload.adequate,
        "baseline": payload.baseline,
        "coverage": payload.coverage,
    }


def recommendations(db, user_id, as_of=None, history_data=None):
    """Savings-opportunity products built from engine category signals."""
    as_of = as_of or today_dhaka()
    h = history_data or history(db, user_id, as_of)
    items = []
    if h["adequate"]:
        signals = savings_opportunity_signals(
            db, user_id, as_of,
            history_adequate=h["adequate"],
            comparison_basis=comparison_expenses_by_category(
                db, user_id, previous_complete_month_period(as_of, back=2)),
        )
        for signal in signals:
            evidence = signal.evidence
            items.append({
                "id": signal.stable_id,
                "category": evidence["category"],
                "title": f"Review increased {evidence['category']} spending",
                "evidence": {
                    "period_start": str(evidence["period_start"]),
                    "period_end": str(evidence["period_end"]),
                    "latest_expenses": str(evidence["latest_expenses"]),
                    "previous_expenses": str(evidence["previous_expenses"]),
                },
                "estimated_monthly_saving": evidence["estimated_monthly_saving"],
                "estimated_annual_saving": money(evidence["estimated_monthly_saving"] * 12),
                "confidence": "low",
                "assumptions": list(signal.assumptions),
            })
    return {
        "coverage": h["coverage"],
        "recommendations": items[:5],
        "limitations": LIMITATIONS
        + ([INSUFFICIENT_HISTORY_NOTE] if not h["adequate"] else []),
    }


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
    from app.services.finance.runway import financial_runway
    runway = financial_runway(db, user_id, as_of=as_of, horizon_days=request.horizon_days,
                             safety_threshold=request.safety_buffer,
                             starting_balance=request.starting_balance)
    reserve, uncertain = runway.scheduled_expense_reserve, runway.known_future_income
    remaining = money(runway.known_obligations_end_balance - request.purchase_amount)
    projected_minimum = runway.minimum_projected_balance
    status = "not_recommended" if remaining < ZERO or (projected_minimum is not None and projected_minimum - request.purchase_amount < ZERO) else None
    if status is None and (remaining < request.safety_buffer or (projected_minimum is not None and projected_minimum - request.purchase_amount <= request.safety_buffer)):
        status = "caution"
    base = assess_spending_decision(SpendingDecisionRequest(
        purchase_amount=request.purchase_amount, starting_balance=request.starting_balance,
        safety_buffer=request.safety_buffer + reserve))
    return {"status": status or base.status, "purchase_amount": request.purchase_amount,
            "scheduled_expense_reserve": reserve,
            "remaining_after_purchase_and_reserve": remaining,
            "runway": runway,
            "uncertain_scheduled_income": uncertain, "horizon_end": end,
            "assumptions": ["Caller confirms the available balance and safety buffer.",
                            "Scheduled expenses in the inclusive horizon are reserved; scheduled income is excluded.",
                            "The purchase is assumed additional to scheduled expenses."],
            "warnings": ["This checks known plans only; unrecorded expenses, overdue bills, and future purchases may make it unaffordable.",
                         "No income projection is treated as money available today."] + runway.limitations}


def goal_plan(db, user_id, goal, as_of=None, history_data=None):
    as_of = as_of or today_dhaka()
    h = history_data or history(db, user_id, as_of)
    assessment = goal_assessment(db, user_id, goal, as_of, h)
    remaining = assessment.remaining
    days = max(1, (goal.target_date - as_of).days)
    weeks = (days + 6) // 7
    weekly = (remaining / weeks).quantize(Decimal("0.01"), rounding=ROUND_UP) if remaining is not None else None
    limitations = list(LIMITATIONS) + list(assessment.limitations)
    return {"goal_id": goal.id, "as_of_date": as_of, "remaining_amount": remaining,
            "required_weekly": weekly, "required_monthly": assessment.required_monthly,
            "estimated_monthly_capacity": assessment.capacity,
            "affordability": assessment.affordability, "assumptions": [
                "Saved amounts are user-reported and not reconciled with account balances.",
                "Contribution counts round up remaining weeks and include the target calendar month; cents round up.",
                "Historical surplus is an estimate; scheduled income is not guaranteed or added.",
                "Known current-month obligations and other active goals reduce the estimated capacity."],
            "limitations": limitations}


def nudges(db, user_id, as_of=None):
    """Proactive insights built from engine signals (presentation only)."""
    as_of = as_of or today_dhaka()
    expiry = month_shift(as_of, 1)
    h = history(db, user_id, as_of)
    signals = build_signals(db, user_id, as_of, SimpleNamespace(
        adequate=h["adequate"], baseline=h["baseline"], monthly=h["monthly"]))
    items: list[dict] = []

    savings_count = 0
    for signal in signals:
        if signal.signal_type == "upcoming_expense":
            evidence = signal.evidence
            due_date = signal.observed_period.end
            items.append({
                "key": signal.stable_id,
                "type": "upcoming_expense",
                "severity": "warning",
                "title": "Plan for an upcoming expense",
                "evidence": {
                    "scheduled_item_id": evidence["scheduled_item_id"],
                    "title": evidence["title"],
                    "amount": str(evidence["amount"]),
                    "record_type": evidence["record_type"],
                },
                "period_start": as_of,
                "period_end": due_date,
                "expires_on": due_date + timedelta(days=1),
                "next_action": "Review the plan and reserve funds; it is not an actual transaction.",
            })
        elif signal.signal_type == "savings_opportunity":
            if savings_count >= 5:
                continue
            savings_count += 1
            evidence = signal.evidence
            items.append({
                "key": signal.stable_id,
                "type": "savings_opportunity",
                "severity": "info",
                "title": f"Review increased {evidence['category']} spending",
                "evidence": {
                    "period_start": str(evidence["period_start"]),
                    "period_end": str(evidence["period_end"]),
                    "latest_expenses": str(evidence["latest_expenses"]),
                    "previous_expenses": str(evidence["previous_expenses"]),
                    "estimated_monthly_saving": str(evidence["estimated_monthly_saving"]),
                },
                "period_start": month_shift(as_of, -1),
                "period_end": as_of.replace(day=1) - timedelta(days=1),
                "expires_on": expiry,
                "next_action": "Review whether a small reduction is feasible; estimated savings are not guaranteed.",
            })
        elif signal.signal_type == "unusual_spending":
            evidence = signal.evidence
            items.append({
                "key": signal.stable_id,
                "type": "unusual_spending",
                "severity": "warning",
                "title": "Recorded spending exceeds your recent range",
                "evidence": {
                    "current_expenses": str(evidence["current_expenses"]),
                    "largest_prior_month": str(evidence["largest_prior_month"]),
                },
                "period_start": signal.observed_period.start,
                "period_end": signal.observed_period.end,
                "expires_on": expiry,
                "next_action": "Check imports and large purchases before changing your budget.",
            })
        elif signal.signal_type == "projected_shortfall":
            evidence = signal.evidence
            items.append({
                "key": signal.stable_id,
                "type": "projected_shortfall",
                "severity": "warning",
                "title": "Historical averages suggest a monthly deficit",
                "evidence": {
                    "estimated_monthly_net": str(evidence["estimated_monthly_net"]),
                    "is_estimate": True,
                },
                "period_start": as_of,
                "period_end": expiry - timedelta(days=1),
                "expires_on": expiry,
                "next_action": "Review the cashflow scenario using a confirmed balance; this is not a predicted bank balance.",
            })
        elif signal.signal_type == "goal_progress":
            evidence = signal.evidence
            items.append({
                "key": signal.stable_id,
                "type": "goal_progress",
                "severity": signal.severity,
                "title": "Review your savings goal",
                "evidence": {
                    "goal_id": evidence["goal_id"],
                    "name": evidence["name"],
                    "saved_source": evidence["saved_source"],
                    "current_saved": str(evidence["current_saved"])
                    if evidence["current_saved"] is not None else None,
                    "affordability": evidence["affordability"],
                },
                "period_start": signal.observed_period.start,
                "period_end": signal.observed_period.end,
                "expires_on": expiry,
                "next_action": "Confirm savings progress and review the contribution plan.",
            })
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    unique = {item["key"]: item for item in items if item["expires_on"] > as_of}
    return {"as_of_date": as_of, "insights": sorted(unique.values(), key=lambda item: (severity_order[item["severity"]], item["key"]))[:30],
            "limitations": LIMITATIONS + ["Insights are recomputed active observations with stable keys; they expire or disappear when evidence changes. Dismissal is not persisted."]}
