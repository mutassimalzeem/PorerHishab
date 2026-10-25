"""Supported finance intents and exact date-scoped answers without a vector database."""
import re
from datetime import date, timedelta
from decimal import Decimal

from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.schemas.coach import CoachCashflowRequest, CoachPurchaseRequest
from app.services.finance.coach import (
    today_dhaka, month_shift, totals, grouped_expenses, recommendations, coach_cashflow, coach_purchase,
)


class AmbiguousQuestion(ValueError):
    pass


def parse_period(question, payload, today):
    if (payload.start_date is None) != (payload.end_date is None):
        raise AmbiguousQuestion("Supply both start_date and end_date.")
    if payload.start_date is not None:
        start, end = payload.start_date, payload.end_date
    else:
        dates = re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", question)
        if dates:
            if len(dates) != 2:
                raise AmbiguousQuestion("Use two ISO dates or explicit start_date and end_date fields.")
            try:
                start, end = map(date.fromisoformat, dates)
            except ValueError:
                raise AmbiguousQuestion("The requested dates are invalid.")
        elif "last month" in question:
            start = month_shift(today, -1)
            end = month_shift(today, 0) - timedelta(days=1)
        elif "this month" in question:
            start, end = month_shift(today, 0), today
        elif "last 30 days" in question:
            start, end = today - timedelta(days=29), today
        elif "last 7 days" in question:
            start, end = today - timedelta(days=6), today
        else:
            # Do not silently reinterpret unsupported time expressions as this month.
            without_iso = re.sub(r"\d{4}-\d{2}-\d{2}", "", question)
            if re.search(r"\b(last|next|previous|week|year|yesterday|since|between|quarter|january|february|march|april|may|june|july|august|september|october|november|december|\d{4})\b", without_iso):
                raise AmbiguousQuestion("Please provide an explicit start_date and end_date for that period.")
            start, end = month_shift(today, 0), today
    if start > end:
        raise AmbiguousQuestion("start_date must not exceed end_date.")
    if (end - start).days > 3660 or start.year < 1900 or end > today:
        raise AmbiguousQuestion("Historical queries require a past or present range of at most ten years.")
    return start, end


def answer_question(db, user_id, payload, as_of=None):
    today = as_of or today_dhaka()
    question = payload.question.strip().lower()
    result = {"answer": "", "intent": "analytics", "sources": [], "calculation": {},
              "date_range": None, "coverage": None, "assumptions": ["BDT amounts use signed imported transactions; expenses are negative in storage."],
              "limitations": [], "status": "answered"}

    def insufficient(text):
        result.update(answer=text, status="insufficient_data")
        return result

    if any(word in question for word in ("afford", "purchase", "buy ")):
        if payload.purchase_amount is None or payload.starting_balance is None or payload.safety_buffer is None:
            return insufficient("Please supply purchase_amount, a confirmed starting_balance, and safety_buffer. I cannot infer your available balance.")
        decision = coach_purchase(db, user_id, CoachPurchaseRequest(
            purchase_amount=payload.purchase_amount, starting_balance=payload.starting_balance,
            safety_buffer=payload.safety_buffer), today)
        result["calculation"] = {"operation": "purchase", **decision}
        result["date_range"] = {"start_date": str(today), "end_date": str(decision["horizon_end"])}
        result["answer"] = f"After this purchase and known scheduled expenses, BDT {decision['remaining_after_purchase_and_reserve']:.2f} would remain. Assessment: {decision['status']}. Unrecorded bills may change this."
        result["limitations"] = decision["warnings"]
        result["assumptions"] = decision["assumptions"]
        return result
    if any(word in question for word in ("projected", "forecast", "cashflow assumptions")):
        if payload.starting_balance is None:
            return insufficient("Provide a confirmed starting_balance to view a cashflow scenario and its assumptions.")
        forecast = coach_cashflow(db, user_id, CoachCashflowRequest(starting_balance=payload.starting_balance), today)
        result["calculation"] = {"operation": "cashflow_scenario", **forecast}
        result["date_range"] = {"start_date": str(today), "end_date": str(month_shift(today, 3) - timedelta(days=1))}
        result["answer"] = "The scenario uses historical monthly averages and reserves known scheduled expenses. Scheduled income is uncertain and is excluded from projected balances. See the calculation for the monthly scenarios and assumptions."
        result["coverage"] = forecast["coverage"]
        result["assumptions"] = forecast["assumptions"]
        result["limitations"] = forecast["limitations"]
        return result
    if any(word in question for word in ("coming up", "upcoming", "bills", "scheduled")):
        start, end = today, today + timedelta(days=30)
        if payload.start_date is not None or payload.end_date is not None:
            if payload.start_date is None or payload.end_date is None or payload.start_date > payload.end_date:
                raise AmbiguousQuestion("Supply an ordered start_date and end_date.")
            start, end = payload.start_date, payload.end_date
            if start < today or (end - start).days > 366:
                raise AmbiguousQuestion("Upcoming plans need a future range of at most one year.")
        elif any(word in question for word in ("last", "week", "year", "month", "tomorrow", "yesterday")) or re.search(r"\d", question):
            raise AmbiguousQuestion("Supply explicit dates for a custom upcoming-bill period.")
        query = db.query(ScheduledCashflowItem).filter(
            ScheduledCashflowItem.user_id == user_id, ScheduledCashflowItem.status == "scheduled",
            ScheduledCashflowItem.kind == "expense", ScheduledCashflowItem.due_date >= start,
            ScheduledCashflowItem.due_date <= end,
        ).order_by(ScheduledCashflowItem.due_date, ScheduledCashflowItem.id)
        count = query.count()
        items = [{"title": row.title, "due_date": str(row.due_date), "amount": str(row.amount), "record_type": "plan"} for row in query.limit(payload.k).all()]
        result["date_range"] = {"start_date": str(start), "end_date": str(end)}
        result["calculation"] = {"operation": "upcoming_expenses", "items": items, "total_items": count}
        result["answer"] = f"You have {count} scheduled expenses in this period. These are plans, not proof of money already spent." if count else "No scheduled expenses are recorded in this period; unrecorded bills are unknown."
        result["limitations"] = ["Only scheduled expense records are included; the list may be incomplete."]
        return result
    if any(word in question for word in ("reasonably save", "save more", "saving opportun", "how can i save")):
        data = recommendations(db, user_id, today)
        result["calculation"] = {"operation": "savings_recommendations", **data}
        result["coverage"] = data["coverage"]
        result["date_range"] = {"start_date": data["coverage"]["start_date"], "end_date": data["coverage"]["end_date"]}
        result["limitations"] = data["limitations"]
        if not data["recommendations"]:
            return insufficient("There is not enough evidence for a specific discretionary saving recommendation. This does not mean you cannot save.")
        result["answer"] = "Review the listed category increases. Each potential saving is an optional estimate, not a guaranteed or necessarily feasible reduction."
        return result
    if any(word in question for word in ("balance", "money do i have", "money do i have left")):
        return insufficient("I cannot establish your current available balance from imported transactions. Supply a confirmed balance for a purchase or cashflow scenario.")
    if not any(word in question for word in ("spent", "spend", "spending", "expense", "income", "earned", "categor", "merchant", "compare")):
        result.update(intent="unknown", status="unsupported", answer="I can answer spending, income, category, merchant, comparison, upcoming-bill, savings-opportunity and purchase questions. For a custom period, supply explicit dates.")
        return result
    compare = "compare" in question or "compared" in question
    if compare and ("this month" not in question or "last month" not in question or payload.start_date is not None):
        raise AmbiguousQuestion("Supported comparisons are this month versus last month. Supply a single date range for other aggregate questions.")
    if question.count("last month") + question.count("this month") > 1 and not compare:
        raise AmbiguousQuestion("Ask about one period, or explicitly compare this month with last month.")
    start, end = (month_shift(today, 0), today) if compare else parse_period(question, payload, today)
    category = payload.category
    if category is None:
        aliases = {"food": "Food", "dining": "Food", "groceries": "Groceries", "transport": "Transport", "housing": "Housing", "utilities": "Bills", "shopping": "Shopping", "subscriptions": "Subscription", "healthcare": "Healthcare", "education": "Education"}
        matches = {name for alias, name in aliases.items() if re.search(r"\b" + alias + r"\b", question)}
        if len(matches) > 1:
            raise AmbiguousQuestion("Please ask about one category or all categories.")
        category = next(iter(matches), None)
        # Remove only the temporal phrase already validated by parse_period.
        # Other "from"/"at"/"on" clauses must still be checked as filters.
        period_phrase = (
            rf"\b(?:from\s+{re.escape(str(start))}\s+to\s+{re.escape(str(end))}"
            rf"|between\s+{re.escape(str(start))}\s+and\s+{re.escape(str(end))})\b"
        )
        filter_question = re.sub(period_phrase, "", question)
        if re.search(r"\b(on|at|from)\s+", filter_question) and category is None:
            raise AmbiguousQuestion("Specify a category field for category filtering. Merchant-specific filtering is not supported; ask for top merchants instead.")
    data = totals(db, user_id, start, end, category)

    result["coverage"] = data["coverage"]
    result["date_range"] = {"start_date": str(start), "end_date": str(end)}
    result["limitations"] = data["coverage"]["limitations"]
    result["sources"] = [{"kind": "sql_aggregate", "start_date": str(start), "end_date": str(end)}]

    if data["expenses"] is None:
        result["calculation"] = {"operation": "summary", "category": category, **data}
        return insufficient("No matching actual transactions are recorded for this period. Missing records do not establish zero spending or income.")

    if compare:
        previous_start = month_shift(today, -1)
        # Compare equal elapsed days, capped to the prior calendar month's length.
        previous_end = min(previous_start + timedelta(days=today.day - 1), month_shift(today, 0) - timedelta(days=1))
        previous = totals(db, user_id, previous_start, previous_end, category)
        metric = "income" if re.search(r"\b(income|earned)\b", question) else "expenses"
        current_value, previous_value = data[metric], previous[metric]
        change = current_value - previous_value if previous_value is not None else None
        change_pct = (
            (change / previous_value * 100).quantize(Decimal("0.01"))
            if change is not None and previous_value else None
        )
        change_key = "income_change" if metric == "income" else "expense_change"
        result["calculation"] = {"operation": "comparison", "current": data, "previous": previous,
                                  "metric": metric, "change": change, "change_pct": change_pct,
                                  change_key: change, change_key + "_pct": change_pct,
                                  "category": category}
        result["assumptions"].append("Comparison uses equal elapsed calendar days where the prior month permits, not a full month versus a partial month.")
        result["answer"] = f"Recorded {metric} changed by BDT {change:.2f} in the matched periods. See the exact ranges and coverage in the calculation." if change is not None else "The previous comparison period has no matching records, so a change cannot be calculated."
        if change is None:
            result["status"] = "insufficient_data"
    elif "categor" in question or "merchant" in question or "contributed most" in question:
        if category is not None:
            raise AmbiguousQuestion("For ranked category or merchant totals, ask without a category filter.")
        group = "merchant" if "merchant" in question else "category"
        items = grouped_expenses(db, user_id, start, end, group, payload.k)
        result["calculation"] = {"operation": "ranked_expenses", "group": group, "items": items}
        result["answer"] = "; ".join(f"{row[group]}: BDT {row['expenses']:.2f}" for row in items) or "No expense transactions are recorded in this period."
    else:
        metric = "income" if "income" in question or "earned" in question else "expenses"
        result["calculation"] = {"operation": "summary", "category": category, **data}
        result["answer"] = f"Recorded {metric} from {start} to {end}: BDT {data[metric]:.2f}. This reflects imported records only."
    return result
