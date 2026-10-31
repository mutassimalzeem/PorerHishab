"""Authoritative Decimal obligation values; allocations are metadata, not cashflow."""
from dataclasses import dataclass
from datetime import datetime, timezone
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


def obligation_amounts_for_items(db, user_id, items, *, as_of: datetime | None = None):
    """Batch authoritative amounts, optionally replaying allocation timestamps.

    Without ``as_of``, preserve AI-15B current active-allocation semantics.
    Historical reads use current principal; principal edits are not versioned.
    """
    if any(item.user_id != user_id for item in items):
        raise ValueError("Obligation does not belong to the user")
    totals = {}
    # Historical reads include revoked allocations while they were still active.
    # Keep all settlement arithmetic in this authoritative service.
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    cutoff = utc(as_of) if as_of is not None else None
    rows = allocations(db, user_id, active=None if as_of is not None else True)
    for row in rows:
        if cutoff is not None:
            if utc(row.confirmed_at) > cutoff:
                continue
            if row.revoked_at is not None and utc(row.revoked_at) <= cutoff:
                continue
            if not row.active and row.revoked_at is None:
                continue
        totals[row.item_id] = totals.get(row.item_id, ZERO) + row.amount
    return {item.id: obligation_amounts(item, totals.get(item.id, ZERO)) for item in items}
