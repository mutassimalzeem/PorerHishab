"""Deterministic suggestions. Only explicit user actions can allocate money."""
from datetime import datetime, timezone
from app.services.intelligence.periods import today_dhaka
from decimal import Decimal
import re
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.models.obligation_allocation import ObligationAllocation
from app.repositories.obligation_reconciliation import allocations, item_for_user, lock_owner, transaction_for_user, eligible_transactions, is_bdt_transaction

from app.services.finance.obligations import obligation_amounts

ZERO = Decimal("0.00")
LIMITATIONS = ["Suggestions are not proof of payment; review the original transaction.",
               "Transaction principal is used; separately recorded fees are excluded.",
               "Only owned BDT accounts and unlinked transactions assumed BDT are eligible.",
               "Confirmation is a user assertion and may select transactions outside the suggestion window."]

def allocated_total(db, user_id, item_id):
    return sum((a.amount for a in allocations(db, user_id, item_id)), ZERO)

def direction_matches(item, transaction):
    return transaction.amount > 0 if item.kind == "income" else transaction.amount < 0

def reconcile(db, user_id, item_id, *, as_of=None, date_tolerance_days=7, amount_tolerance=ZERO, snapshot=None):
    if not 0 <= date_tolerance_days <= 90 or not ZERO <= amount_tolerance <= Decimal("1000000"):
        raise ValueError("Invalid matching tolerances")
    item = item_for_user(db, user_id, item_id)
    as_of = as_of or today_dhaka()
    all_allocations, transactions = snapshot or (allocations(db, user_id, active=None), eligible_transactions(db, user_id))
    history = [a for a in all_allocations if a.item_id == item_id]
    total = sum((a.amount for a in history if a.active), ZERO)
    remaining = obligation_amounts(item, total).remaining_amount
    used = {a.transaction_id for a in all_allocations if a.active}
    candidates = []
    if item.status == "scheduled" and remaining > ZERO:
        for tx in transactions:
            distance = abs((tx.date - item.due_date).days)
            amount = abs(tx.amount)
            difference = abs(amount - remaining)
            if tx.id in used or not direction_matches(item, tx) or distance > date_tolerance_days:
                continue
            # Partial principal is eligible; an oversized transaction is only a suggestion
            # within tolerance and can never be confirmed as an over-allocation.
            if amount > remaining + amount_tolerance:
                continue
            category = bool(item.category and tx.category and item.category.casefold() == tx.category.casefold())
            words = set(re.findall(r"\w+", (item.title + " " + (item.notes or "")).casefold()))
            overlap = bool(words & set(re.findall(r"\w+", ((tx.merchant or "") + " " + (tx.description or "")).casefold())))
            signal = "exact" if difference == ZERO else "within_tolerance" if difference <= amount_tolerance else "partial"
            candidates.append(dict(transaction_id=tx.id, date=tx.date, amount=amount, description=tx.description,
                merchant=tx.merchant, category=tx.category, amount_difference=difference,
                date_distance_days=distance, amount_signal=signal, category_match=category, text_overlap=overlap,
                confidence="medium" if signal == "exact" and (category or overlap) else "low",
                limitations=LIMITATIONS + (["Amount exceeds remaining principal; confirmation is unavailable."] if amount > remaining else [])))
    candidates.sort(key=lambda c: (c["amount_difference"], c["date_distance_days"], c["transaction_id"]))
    timing = "overdue" if item.due_date < as_of else "not_due" if item.due_date > as_of else "due"
    status = item.status if item.status != "scheduled" else (
        "partial" if total else "review_required" if candidates else "insufficient_data" if not transactions
        else "overdue" if timing == "overdue" else "not_due" if timing == "not_due" else "unmatched")
    return dict(item_id=item.id, original_amount=item.amount, allocated_amount=total, remaining_amount=remaining,
        status=status, timing=timing, ambiguous=len(candidates) > 1, candidates=candidates, allocations=history,
        date_tolerance_days=date_tolerance_days, amount_tolerance=amount_tolerance, limitations=LIMITATIONS)

def confirm(db, user_id, item_id, transaction_id, full=False):
    lock_owner(db, user_id)
    item = item_for_user(db, user_id, item_id)
    tx = transaction_for_user(db, user_id, transaction_id)
    existing = next((a for a in allocations(db, user_id) if a.transaction_id == transaction_id), None)
    if existing:
        if existing.item_id != item_id:
            raise HTTPException(409, "Transaction is already allocated")
        if full:
            if allocated_total(db, user_id, item_id) != item.amount:
                raise HTTPException(422, "Full settlement requires the exact remaining amount")
            if item.status == "scheduled":
                item.status = "paid"
        db.commit()
        return reconcile(db, user_id, item_id)
    if item.status != "scheduled":
        raise HTTPException(409, "Only scheduled items accept allocations")
    if not is_bdt_transaction(db, user_id, tx):
        raise HTTPException(422, "Only BDT transactions can settle obligations")
    if not direction_matches(item, tx) or tx.amount == ZERO:
        raise HTTPException(422, "Transaction direction does not match obligation")
    remaining = obligation_amounts(item, allocated_total(db, user_id, item_id)).remaining_amount
    amount = abs(tx.amount)
    if amount > remaining:
        raise HTTPException(422, "Transaction exceeds remaining amount")
    if full and amount != remaining:
        raise HTTPException(422, "Full settlement requires the exact remaining amount")
    db.add(ObligationAllocation(user_id=user_id, item_id=item_id, transaction_id=transaction_id, amount=amount))
    if full:
        item.status = "paid"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Transaction allocation conflict")
    return reconcile(db, user_id, item_id)

def revoke(db, user_id, item_id, transaction_id):
    lock_owner(db, user_id)
    item = item_for_user(db, user_id, item_id)
    transaction_for_user(db, user_id, transaction_id)
    row = next((a for a in allocations(db, user_id, item_id) if a.transaction_id == transaction_id), None)
    if row:
        row.active = False
        row.revoked_at = datetime.now(timezone.utc)
        if item.status == "paid":
            item.status = "scheduled"
        db.commit()
    return reconcile(db, user_id, item_id)
