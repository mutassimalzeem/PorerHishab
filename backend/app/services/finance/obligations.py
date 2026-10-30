"""Authoritative Decimal obligation values; allocations are metadata, not cashflow."""
from dataclasses import dataclass
from decimal import Decimal

from app.repositories.obligation_reconciliation import allocations, item_for_user

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ObligationAmounts:
    original_amount: Decimal
    allocated_amount: Decimal
    remaining_amount: Decimal
    reserved_amount: Decimal


def obligation_amounts(item, allocated_amount):
    """Preserve principal; manual paid/cancelled records reserve nothing."""
    remaining = max(item.amount - allocated_amount, ZERO)
    return ObligationAmounts(item.amount, allocated_amount, remaining,
                             remaining if item.status == "scheduled" else ZERO)


def remaining_obligation(db, user_id, item_id):
    from app.services.finance.obligation_reconciliation import allocated_total
    item = item_for_user(db, user_id, item_id)
    return obligation_amounts(item, allocated_total(db, user_id, item_id))


def obligation_amounts_for_items(db, user_id, items):
    """Batch the same scoped, active rows used by AI-15B allocated_total()."""
    if any(item.user_id != user_id for item in items):
        raise ValueError("Obligation does not belong to the user")
    totals = {}
    for row in allocations(db, user_id):
        totals[row.item_id] = totals.get(row.item_id, ZERO) + row.amount
    return {item.id: obligation_amounts(item, totals.get(item.id, ZERO)) for item in items}
