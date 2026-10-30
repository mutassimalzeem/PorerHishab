"""Computed chronological read model over actuals, obligation metadata and AI-15D.

Never sum actual_history impacts onto starting cash: AI-15A already includes them.
Only future_projection impacts belong to the historical runway scenario.
"""
from datetime import timedelta
from decimal import Decimal

from app.models.account import Account
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.repositories.transaction_repository import list_transactions_in_range
from app.repositories.obligation_reconciliation import allocations
from app.schemas.timeline import FinancialTimeline, TimelineEvent
from app.services.finance.obligations import obligation_amounts_for_items
from app.services.finance.runway import cash_position, financial_runway
from app.services.intelligence.facts import scheduled_obligation_values
from app.services.intelligence.periods import Period, today_dhaka

ZERO = Decimal("0.00")
PRIORITY = {name: priority for priority, name in enumerate((
    "transaction", "obligation_payment", "obligation", "forecast_expense", "forecast_income", "runway_checkpoint"))}


def timeline_event(*, event_type, source_id, balance_impact=ZERO, impact_scope="context", **kw):
    return TimelineEvent(id=f"{event_type}:{source_id}", event_type=event_type,
                         source_id=str(source_id), balance_impact=balance_impact,
                         impact_scope=impact_scope, cash_impacting=balance_impact != ZERO, **kw)


def financial_timeline(db, user_id, *, start_date=None, end_date=None, include_estimates=True, as_of=None):
    """Date filters crop events, never rerun forecasts from the filter's first date."""
    as_of = as_of or today_dhaka()
    start = start_date or as_of - timedelta(days=30)
    end = end_date or as_of + timedelta(days=30)
    if user_id <= 0 or start > end or (end - start).days > 732 or (end - as_of).days > 366:
        raise ValueError("Timeline requires an ordered range of at most 732 days and at most 366 future days")
    period = Period(kind="timeline_window", start=start, end=end, is_complete=False, label="inclusive financial timeline")
    runway = financial_runway(db, user_id, as_of=as_of, horizon_days=(end - as_of).days) if end > as_of else None
    if runway is not None:
        starting, source = runway.starting_balance, runway.balance_source
    elif start <= as_of <= end:
        starting, _, _, source, _ = cash_position(db, user_id, as_of)
    else:
        starting, source = None, "unknown"
    events = []
    accounts = {a.id: a for a in db.query(Account).filter_by(user_id=user_id).all()}
    transactions = list_transactions_in_range(db, user_id, start, min(end, as_of)) if start <= as_of else []
    transactions = [tx for tx in transactions if tx.account_id is None or tx.account_id in accounts]
    tx_by_id = {tx.id: tx for tx in transactions}
    for tx in transactions:
        account = accounts.get(tx.account_id)
        events.append(timeline_event(
            date=tx.date, event_type="transaction", certainty="actual",
            direction="income" if tx.amount > ZERO else "expense" if tx.amount < ZERO else "neutral",
            amount=tx.amount, currency=account.currency if account else "BDT",
            title=tx.merchant or tx.description, description=tx.description,
            source="transaction", source_id=tx.id, balance_impact=tx.amount - tx.fee,
            impact_scope="actual_history", evidence=dict(transaction_id=tx.id,
                transaction_amount=tx.amount, fee=tx.fee, category=tx.category,
                account_id=account.id if account else None, account_name=account.name if account else None)))
    active = [a for a in allocations(db, user_id) if a.transaction_id in tx_by_id]
    item_ids = {a.item_id for a in active}
    items = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.user_id == user_id, ScheduledCashflowItem.id.in_(item_ids)).all() if item_ids else []
    amounts = obligation_amounts_for_items(db, user_id, items) if items else {}
    items = {item.id: item for item in items}
    for allocation in active:
        item = items.get(allocation.item_id)
        if item is None:
            continue
        tx, amount = tx_by_id[allocation.transaction_id], amounts[item.id]
        events.append(timeline_event(
            date=tx.date, event_type="obligation_payment", certainty="confirmed", direction=item.kind,
            amount=allocation.amount, currency="BDT", title=item.title, source="obligation_allocation",
            source_id=allocation.id, original_amount=amount.original_amount,
            allocated_amount=amount.allocated_amount, remaining_amount=amount.remaining_amount,
            reserved_amount=amount.reserved_amount, status=item.status,
            evidence=dict(transaction_id=tx.id, obligation_id=item.id, allocation_id=allocation.id,
                          transaction_amount=tx.amount, category=item.category)))
    for item, amount in scheduled_obligation_values(db, user_id, start, end):
        future_expense = item.due_date >= as_of and item.kind == "expense"
        events.append(timeline_event(
            date=item.due_date, event_type="obligation",
            certainty="uncertain" if item.kind == "income" else "scheduled", direction=item.kind,
            amount=amount.remaining_amount, currency="BDT", title=item.title, description=item.notes,
            source="scheduled_cashflow", source_id=item.id,
            balance_impact=-amount.reserved_amount if future_expense else ZERO,
            impact_scope="future_projection" if future_expense else "context",
            original_amount=amount.original_amount, allocated_amount=amount.allocated_amount,
            remaining_amount=amount.remaining_amount, reserved_amount=amount.reserved_amount,
            status="overdue" if item.due_date < as_of else item.status,
            evidence=dict(obligation_id=item.id, category=item.category)))
    if runway is not None and include_estimates:
        for checkpoint in runway.checkpoints:
            segment = Period(kind="forecast_segment", start=checkpoint.period_start,
                             end=checkpoint.date, is_complete=False, label="monthly historical estimate")
            source_id = f"historical:{segment.start}:{segment.end}"
            evidence = dict(period=segment.to_dict(), mode=runway.mode,
                            scheduled_expense_reserve=checkpoint.scheduled_expense_reserve,
                            expected_expense_reserve=checkpoint.expected_expense_reserve)
            # Attribute the already-computed reserve, without another max/forecast formula.
            # Scheduled expense events carry their portion; only the residual belongs here.
            residual = checkpoint.expected_expense_reserve - checkpoint.scheduled_expense_reserve
            if checkpoint.forecast_expense > ZERO:
                events.append(timeline_event(date=checkpoint.date, event_type="forecast_expense",
                    certainty="estimated", direction="expense", amount=checkpoint.forecast_expense,
                    currency="BDT", title=None, source="financial_runway", source_id=source_id,
                    balance_impact=-residual, impact_scope="future_projection", evidence=evidence))
            if checkpoint.forecast_income > ZERO:
                events.append(timeline_event(date=checkpoint.date, event_type="forecast_income",
                    certainty="estimated", direction="income", amount=checkpoint.forecast_income,
                    currency="BDT", title=None, source="financial_runway", source_id=source_id,
                    balance_impact=checkpoint.forecast_income, impact_scope="future_projection", evidence=evidence))
            events.append(timeline_event(date=checkpoint.date, event_type="runway_checkpoint",
                certainty="estimated", direction="neutral", amount=checkpoint.projected_balance,
                currency="BDT", title=None, source="financial_runway", source_id=source_id,
                evidence=dict(**evidence, projected_balance=checkpoint.projected_balance,
                              minimum_balance=checkpoint.minimum_balance)))
    events = [e for e in events if start <= e.date <= end]
    events.sort(key=lambda e: (e.date, PRIORITY[e.event_type],
                              int(e.source_id) if e.source_id.isdecimal() else e.source_id))
    counts = {certainty: sum(e.certainty == certainty for e in events)
              for certainty in ("actual", "confirmed", "scheduled", "estimated", "uncertain")}
    return FinancialTimeline(
        as_of_date=as_of, period=period.to_dict(), projection_period=runway.period if runway else None,
        starting_balance=starting, balance_source=source,
        ending_projected_balance=runway.projected_end_balance if runway else None,
        runway_status=runway.runway_status if runway else None, events=events, event_counts=counts,
        assumptions=[
            "Historical movements are already included in account cash; never sum actual_history onto starting_balance.",
            "Only future_projection balance impacts belong to the historical runway scenario; context events add no cash.",
            "Forecast expense amount is the full historical estimate; its balance impact is only reserve not already attributed to scheduled expenses.",
            "Date filters crop events; projection_period always anchors at as-of. Cropped events cannot reconstruct the entire scenario.",
        ], limitations=[
            "This is a deterministic read model, not a ledger or historical replay; active allocations and schedule statuses reflect current state.",
            "Future-dated transactions are excluded from actual history. Foreign-currency actuals retain currency but are excluded from BDT projections.",
            "Overdue schedules appear for review with zero future impact. Scheduled income remains uncertain and contributes no projected cash.",
            "Monthly estimates are dated at segment end for ordering, not a prediction of a receipt/payment day or exact depletion date.",
        ] + (runway.limitations if runway else []))
