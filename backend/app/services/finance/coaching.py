"""Read-only recommendation rules over existing deterministic financial engines."""
from datetime import date, timedelta
from hashlib import sha256
from decimal import Decimal

from app.models.savings_goal import SavingsGoal
from app.schemas.coaching import CoachingRecommendation, FinancialCoaching
from app.services.finance.runway import financial_runway
from app.services.intelligence.categories import category_spending_facts, percentage_change
from app.services.intelligence.facts import scheduled_obligation_values, scheduled_totals
from app.services.intelligence.goals import goal_assessment
from app.services.intelligence.periods import Period, month_end, previous_complete_month_period, today_dhaka
from app.services.intelligence.signals import REDUCIBLE_CATEGORIES, INCREASE_FACTOR, UNUSUAL_FACTOR, stable_category_token
from app.services.intelligence.snapshot import monthly_history

ZERO = Decimal("0.00")
HORIZON_DAYS = 30
PREPARATION_DAYS = 7
LARGE_CASH_FRACTION = Decimal("0.50")
PRIORITY = {name: rank for rank, name in enumerate(("critical", "high", "medium", "low"))}
COPY = {
    "cash_risk": ("Prepare for a possible cash shortfall", "The existing cashflow scenario reaches or crosses your safety threshold.", "Review upcoming commitments and postpone optional spending until the gap is covered."),
    "upcoming_obligations": ("Prepare for remaining commitments", "These obligations are due soon or are large relative to established account cash.", "Review the remaining amounts and due dates before reserving money or confirming a payment."),
    "spending_spike": ("Review a category spending increase", "Recorded spending rose by more than 50% between two complete months.", "Check the underlying transactions for one-off costs or categorization errors before changing spending."),
    "repeated_spending": ("Review a repeated category increase", "Spending in a potentially reducible category exceeded the same earlier baseline in two complete months.", "Review optional costs in this category; protect essential needs and choose a reduction only if feasible."),
    "savings_opportunity": ("Consider an unassigned savings reserve", "Three complete months show positive recorded net cashflow and established cash remains after commitments.", "Consider reserving up to the indicated amount once; review essential spending and cash needs first."),
    "goal_risk": ("Review a savings goal at risk", "The existing goal planner flags an overdue target or an estimated contribution shortfall.", "Review the target date or contribution plan before allocating more cash."),
}
CAVEATS = {
    "cash": "Account balances may be stale or incomplete; a derived balance is not a live bank balance.",
    "income": "Scheduled income is uncertain and is excluded from available cash and recommendation amounts.",
    "history": "Recorded history may be incomplete; complete-month coverage does not prove all transactions were imported.",
    "forecast": "Runway values are scenario estimates, not bank guarantees; monthly forecasts cannot establish an exact depletion day.",
    "allocations": "Confirmed allocations are payment metadata, not additional transactions; suggestions have no accounting effect.",
    "classification": "Reducible categories are review candidates, not proof that every purchase is discretionary or excessive.",
    "savings": "This is one optional reserve, not additional money for every goal; no transfer or payment is performed.",
    "goals": "Goal savings are user-reported; contribution history is unavailable and is not inferred.",
    "transfers": "Only explicitly classified transfers are excluded; unclassified transfers or duplicate imports may still distort history.",
    "missing": "Account cash or three complete months of usable history are unavailable; absent alerts do not establish financial safety.",
    "goal_date": "A goal has no target date; no deadline or contribution has been invented.",
    "active_goals": "Additional unassigned savings are not suggested while active goals may claim the same cash.",
}


def recommendation(kind, key, as_of, valid_until, *, priority, source, evidence,
                   quality="estimated", amount=None, subject=None, assumptions=(), limitations=()):
    title, description, action = COPY[kind]
    identity = f"{kind}:{key}"
    # Large obligation sets must remain valid persistence keys without truncation.
    if len(identity) > 300:
        identity = f"{kind}:sha256:{sha256(str(key).encode()).hexdigest()}"
    return CoachingRecommendation(
        id=identity, type=kind, priority=priority, title=title, description=description,
        recommended_action=action, amount=amount, as_of_date=as_of, valid_until=valid_until,
        subject=subject, evidence_quality=quality, source=source, source_id=str(key),
        evidence=evidence, assumptions=list(assumptions), limitations=list(limitations))


def goal_recommendation(db, user_id, goal, as_of, history):
    # The persisted model requires a date; tolerate incomplete legacy/domain inputs.
    if goal.target_date is None:
        return None
    assessment = goal_assessment(db, user_id, goal, as_of,
                                 {"adequate": history.adequate, "baseline": history.baseline})
    if not assessment.is_concerning:
        return None
    period = Period(kind="goal_review", start=min(as_of, goal.target_date),
                    end=max(as_of, goal.target_date), is_complete=False, label="goal target review")
    return recommendation("goal_risk", f"{goal.id}:{as_of:%Y-%m}", as_of,
        min(as_of + timedelta(days=HORIZON_DAYS), max(as_of, goal.target_date)),
        priority="high" if goal.target_date <= as_of else "medium", source="goal_assessment",
        subject=goal.name, amount=None, quality="estimated" if assessment.capacity is not None else "limited",
        evidence=dict(period=period.to_dict(), goal_id=goal.id, goal_name=goal.name,
                      current_saved=goal.current_saved, target_amount=goal.target_amount,
                      target_date=goal.target_date, remaining_amount=assessment.remaining,
                      required_monthly=assessment.required_monthly, estimated_monthly_capacity=assessment.capacity,
                      affordability=assessment.affordability), limitations=[CAVEATS["goals"], CAVEATS["history"]])


def spending_recommendations(db, user_id, as_of, history):
    """Complete periods only; use shared aggregates and existing product thresholds."""
    if not history.adequate:
        return []
    periods = [previous_complete_month_period(as_of, back=n) for n in (3, 2, 1)]
    rows = [{fact.category: fact for fact in category_spending_facts(
        db, user_id, period, exclude_transfers=True)} for period in periods]
    result = []
    for category, latest in sorted(rows[2].items()):
        first, previous = rows[0].get(category), rows[1].get(category)
        if previous is None or previous.observed_expenses <= ZERO:
            continue
        repeated = (category in REDUCIBLE_CATEGORIES and first is not None and first.observed_expenses > ZERO
                    and previous.observed_expenses > first.observed_expenses * INCREASE_FACTOR
                    and latest.observed_expenses > first.observed_expenses * INCREASE_FACTOR)
        spike = latest.observed_expenses > previous.observed_expenses * UNUSUAL_FACTOR
        if not (repeated or spike):
            continue
        reference = first if repeated else previous
        kind = "repeated_spending" if repeated else "spending_spike"
        key = f"{stable_category_token(category)}:{periods[2].start:%Y-%m}"
        result.append(recommendation(kind, key, as_of, month_end(as_of), priority="medium",
            source="category_spending", subject=category, quality="recorded",
            evidence=dict(period=periods[2].to_dict(), comparison_period=reference.observed_period.to_dict(),
                category=category, observed_value=latest.observed_expenses, reference_value=reference.observed_expenses,
                percentage_change=percentage_change(latest.observed_expenses, reference.observed_expenses),
                monthly_values=[dict(period=p.to_dict(), amount=row[category].observed_expenses)
                                for p, row in zip(periods, rows) if category in row]),
            assumptions=["Category reviews compare complete calendar months and never extrapolate the current partial month."],
            limitations=[CAVEATS["history"], CAVEATS["classification"], CAVEATS["transfers"]]))
    return result


def financial_coaching(db, user_id, *, as_of=None, priority=None, safety_threshold=ZERO):
    if user_id <= 0 or (priority is not None and priority not in PRIORITY):
        raise ValueError("Invalid coaching scope")
    as_of = as_of or today_dhaka()
    end = as_of + timedelta(days=HORIZON_DAYS)
    period = Period(kind="coaching_horizon", start=as_of, end=end, is_complete=False, label="next 30 days inclusive")
    history = monthly_history(db, user_id, as_of, exclude_transfers=True)
    runway = financial_runway(db, user_id, as_of=as_of, history=history, safety_threshold=safety_threshold)
    items, result = scheduled_obligation_values(db, user_id, as_of, end, kind="expense"), []
    risk = runway if runway.runway_status in {"cash_shortfall", "at_risk"} else None
    if runway.known_obligations_end_balance is not None and runway.known_obligations_end_balance <= safety_threshold:
        known = financial_runway(db, user_id, as_of=as_of, mode="known_obligations", safety_threshold=safety_threshold)
        if risk is None or known.runway_status == "cash_shortfall":
            risk = known
    if risk is not None:
        result.append(recommendation("cash_risk", f"{as_of}:{end}", as_of, end,
            priority="critical" if risk.runway_status == "cash_shortfall" else "high", source="financial_runway",
            quality="estimated" if risk.mode == "historical" else "limited",
            assumptions=["Safety thresholds are caller-selected floors, not personalized recommendations."],
            evidence=dict(period=risk.period, starting_balance=risk.starting_balance, balance_source=risk.balance_source,
                scheduled_expense_reserve=risk.scheduled_expense_reserve, uncertain_income=risk.known_future_income,
                minimum_projected_balance=risk.minimum_projected_balance, projected_end_balance=risk.projected_end_balance,
                cash_after_known_obligations=risk.known_obligations_end_balance, safety_threshold=risk.safety_threshold,
                runway_status=risk.runway_status, runway_mode=risk.mode,
                first_shortfall_date=risk.first_shortfall_date, first_shortfall_period=risk.first_shortfall_period),
            limitations=[CAVEATS["income"], CAVEATS["forecast"]]))
    soon_end = as_of + timedelta(days=PREPARATION_DAYS)
    soon = [(item, amounts) for item, amounts in items if item.due_date <= soon_end]
    groups = [soon] if soon else []
    groups.extend([[(item, amounts)] for item, amounts in items if item.due_date > soon_end
                   and runway.starting_balance is not None and runway.starting_balance > ZERO
                   and amounts.remaining_amount >= runway.starting_balance * LARGE_CASH_FRACTION])
    for group in groups:
        due = min(item.due_date for item, _ in group)
        evidence_items = [dict(item_id=item.id, title=item.title, due_date=item.due_date,
                               original_amount=amounts.original_amount, allocated_amount=amounts.allocated_amount,
                               remaining_amount=amounts.remaining_amount, timeline_event_id=f"obligation:{item.id}")
                          for item, amounts in group]
        amount = scheduled_totals(db, user_id, as_of, soon_end)[0] if group is soon else group[0][1].remaining_amount
        urgent = due <= as_of + timedelta(days=1) or (runway.starting_balance is not None and amount >= runway.starting_balance)
        result.append(recommendation("upcoming_obligations", ",".join(str(item.id) for item, _ in group), as_of, due,
            priority="high" if urgent else "medium", source="scheduled_cashflow", quality="recorded", amount=amount,
            evidence=dict(period=period.to_dict(), starting_balance=runway.starting_balance,
                          scheduled_expense_reserve=amount, obligations=evidence_items),
            limitations=[CAVEATS["allocations"], CAVEATS["income"]]))
    result.extend(spending_recommendations(db, user_id, as_of, history))
    goals = db.query(SavingsGoal).filter_by(user_id=user_id, status="active").order_by(SavingsGoal.target_date, SavingsGoal.id).all()
    limitations = [CAVEATS["cash"], CAVEATS["history"], CAVEATS["income"], CAVEATS["transfers"]]
    for goal in goals:
        if goal.target_date is None:
            limitations.append(CAVEATS["goal_date"])
            continue
        item = goal_recommendation(db, user_id, goal, as_of, history)
        if item is not None:
            result.append(item)
    # One unassigned reserve only. Existing active goals may already claim cash.
    if goals:
        limitations.append(CAVEATS["active_goals"])
    if (not goals and risk is None and history.adequate and runway.runway_status == "positive"
            and runway.balance_source in {"reconciled", "derived"}
            and all(row["net"] is not None and row["net"] > ZERO and row["expenses"] is not None and row["expenses"] > ZERO for row in history.monthly)):
        cap = min(runway.known_obligations_end_balance - safety_threshold,
                  runway.minimum_projected_balance - safety_threshold,
                  min(row["net"] for row in history.monthly))
        if cap > ZERO:
            result.append(recommendation("savings_opportunity", f"unassigned:{as_of:%Y-%m}", as_of, end,
                priority="low", source="financial_runway", amount=cap,
                evidence=dict(period=period.to_dict(), starting_balance=runway.starting_balance,
                    balance_source=runway.balance_source, scheduled_expense_reserve=runway.scheduled_expense_reserve,
                    uncertain_income=runway.known_future_income, minimum_projected_balance=runway.minimum_projected_balance,
                    cash_after_known_obligations=runway.known_obligations_end_balance, safety_threshold=safety_threshold,
                    monthly_values=[dict(period=Period(kind="complete_month", start=date.fromisoformat(row["coverage"]["start_date"]),
                        end=date.fromisoformat(row["coverage"]["end_date"]), is_complete=True, label="recorded monthly net").to_dict(),
                        amount=row["net"]) for row in history.monthly]),
                assumptions=["The suggested cap is no larger than cash after commitments, the projected low-watermark, and the weakest positive observed monthly net."],
                limitations=[CAVEATS["savings"], CAVEATS["history"], CAVEATS["income"], CAVEATS["forecast"]]))
    complete = runway.starting_balance is not None and history.adequate and runway.runway_status != "insufficient_data"
    status = "sufficient" if complete else "partial" if (runway.starting_balance is not None or history.adequate or result) else "insufficient_data"
    if not complete:
        limitations.append(CAVEATS["missing"])
    # One financial risk, one category review per category, one cluster per obligation set, one reserve.
    unique = {item.id: item for item in result}
    ordered = sorted(unique.values(), key=lambda item: (PRIORITY[item.priority], item.valid_until, item.id))
    if priority is not None:
        ordered = [item for item in ordered if item.priority == priority]
    return FinancialCoaching(as_of_date=as_of, period=period.to_dict(), data_status=status,
                             recommendations=ordered, limitations=limitations)
