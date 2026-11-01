"""Deterministic account position and trusted BDT cash integration service.

Combines account metadata, reported balances, opening balances, and
authoritative AI-15A reconciliation to classify account usability and
calculate trusted BDT position aggregates without N+1 queries.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transactions import Transaction
from app.schemas.account_position import (
    AccountCreate,
    AccountOverviewResponse,
    AccountPositionItem,
    AccountPositionStatus,
    AccountReconciliationSummary,
    TrustedBdtPosition,
    TrustedPositionStatus,
)
from app.services.finance.account_reconciliation import reconcile_account_balance

ZERO = Decimal("0.00")
BDT_CURRENCY = "BDT"


def classify_account_position(
    account: Account,
    recon: dict,
) -> tuple[AccountPositionStatus, bool]:
    """Deterministically classify an account's position status and BDT aggregation eligibility."""
    if account.currency != BDT_CURRENCY:
        return "unsupported_currency", False

    recon_status = recon["status"]
    diff = recon["difference"]

    # Reconciled: both reported and derived exist and match exactly
    if recon_status == "reconciled" and (diff is None or diff == ZERO):
        return "trusted", True

    # Mismatch: reported balance differs from derived balance
    if recon_status == "mismatch" or (diff is not None and diff != ZERO):
        return "unreconciled", False

    # Reported only: user provided balance, but no transactions or opening balance to verify
    if recon_status == "reported_only":
        return "reported", False

    # Derived: transactions/opening balance exist, but user hasn't reported a balance to verify
    if recon_status in ("derived_from_opening", "transaction_snapshot", "derived"):
        return "derived", False

    # Insufficient data: no balance information available at all
    return "insufficient_data", False


def get_account_overview(
    db: Session,
    user_id: int,
    *, as_of: date | None = None,
) -> AccountOverviewResponse:
    """Load all accounts for the authenticated user and compute position and trusted BDT total."""
    accounts = (
        db.query(Account)
        .filter(Account.user_id == user_id)
        .order_by(Account.id.asc())
        .all()
    )

    if not accounts:
        return AccountOverviewResponse(
            items=[],
            trusted_bdt_position=TrustedBdtPosition(
                total=None,
                eligible_accounts_count=0,
                review_accounts_count=0,
                excluded_accounts_count=0,
                status="unavailable",
                currency="BDT",
                message="No accounts yet. Add an account or import account-linked transactions to start tracking your position.",
                contributing_account_names=[],
            ),
        )

    # Batch query transactions for all accounts to avoid N+1 queries
    account_ids = [a.id for a in accounts]
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.account_id.in_(account_ids),
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    tx_by_account: dict[int, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        tx_by_account[tx.account_id].append(tx)

    items: list[AccountPositionItem] = []
    eligible_accounts: list[Account] = []
    review_accounts: list[Account] = []
    excluded_accounts: list[Account] = []

    for acc in accounts:
        recon = reconcile_account_balance(
            db,
            account=acc,
            user_id=user_id,
            transactions=tx_by_account[acc.id],
            as_of=as_of,
        )

        pos_status, is_eligible = classify_account_position(acc, recon)

        if is_eligible:
            eligible_accounts.append(acc)
        elif pos_status in ("unreconciled", "reported", "derived"):
            review_accounts.append(acc)
        else:
            excluded_accounts.append(acc)

        recon_summary = AccountReconciliationSummary(
            status=recon["status"],
            confidence=recon["confidence"],
            derived_balance=recon["derived_balance"],
            difference=recon["difference"],
            message=recon["message"],
            transaction_count=recon["transaction_count"],
            latest_transaction_date=recon["latest_transaction_date"],
        )

        items.append(
            AccountPositionItem(
                id=acc.id,
                name=acc.name,
                source=acc.source,
                account_type=acc.account_type,
                currency=acc.currency,
                current_balance=acc.current_balance,
                balance_source=acc.balance_source,
                balance_as_of=acc.balance_as_of,
                opening_balance=acc.opening_balance,
                opening_balance_date=acc.opening_balance_date,
                position_status=pos_status,
                is_eligible_for_bdt_aggregate=is_eligible,
                reconciliation=recon_summary,
            )
        )

    # Compute trusted BDT position aggregate
    if eligible_accounts:
        total_balance = sum((a.current_balance for a in eligible_accounts if a.current_balance is not None), ZERO)
        if review_accounts:
            status: TrustedPositionStatus = "partially_trusted"
            msg = (
                f"Based on {len(eligible_accounts)} account{'s' if len(eligible_accounts) != 1 else ''}; "
                f"{len(review_accounts)} account{'s' if len(review_accounts) != 1 else ''} need{'s' if len(review_accounts) == 1 else ''} review"
            )
        else:
            status = "trusted"
            msg = f"Based on {len(eligible_accounts)} reconciled BDT account{'s' if len(eligible_accounts) != 1 else ''}"

        trusted_pos = TrustedBdtPosition(
            total=total_balance,
            eligible_accounts_count=len(eligible_accounts),
            review_accounts_count=len(review_accounts),
            excluded_accounts_count=len(excluded_accounts),
            status=status,
            currency="BDT",
            message=msg,
            contributing_account_names=[a.name for a in eligible_accounts],
        )
    else:
        trusted_pos = TrustedBdtPosition(
            total=None,
            eligible_accounts_count=0,
            review_accounts_count=len(review_accounts),
            excluded_accounts_count=len(excluded_accounts),
            status="unavailable",
            currency="BDT",
            message="Add or confirm a balance for at least one BDT account.",
            contributing_account_names=[],
        )

    return AccountOverviewResponse(
        items=items,
        trusted_bdt_position=trusted_pos,
    )


def create_account(
    db: Session,
    user_id: int,
    payload: AccountCreate,
) -> AccountPositionItem:
    """Create a new account scoped to the authenticated user."""
    account = Account(
        user_id=user_id,
        name=payload.name,
        source=payload.source,
        account_type=payload.account_type,
        currency=payload.currency.upper(),
        current_balance=payload.current_balance,
        balance_source=payload.balance_source,
        balance_as_of=payload.balance_as_of,
        opening_balance=payload.opening_balance,
        opening_balance_date=payload.opening_balance_date,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    recon = reconcile_account_balance(db, account=account, user_id=user_id)
    pos_status, is_eligible = classify_account_position(account, recon)

    recon_summary = AccountReconciliationSummary(
        status=recon["status"],
        confidence=recon["confidence"],
        derived_balance=recon["derived_balance"],
        difference=recon["difference"],
        message=recon["message"],
        transaction_count=recon["transaction_count"],
        latest_transaction_date=recon["latest_transaction_date"],
    )

    return AccountPositionItem(
        id=account.id,
        name=account.name,
        source=account.source,
        account_type=account.account_type,
        currency=account.currency,
        current_balance=account.current_balance,
        balance_source=account.balance_source,
        balance_as_of=account.balance_as_of,
        opening_balance=account.opening_balance,
        opening_balance_date=account.opening_balance_date,
        position_status=pos_status,
        is_eligible_for_bdt_aggregate=is_eligible,
        reconciliation=recon_summary,
    )
