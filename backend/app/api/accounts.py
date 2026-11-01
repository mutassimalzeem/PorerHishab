"""Authenticated accounts overview and management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.account import Account
from app.models.user import User
from app.schemas.account_position import (
    AccountCreate,
    AccountOverviewResponse,
    AccountPositionItem,
    AccountReconciliationSummary,
    TrustedBdtPosition,
)
from app.services.finance.account_position import (
    classify_account_position,
    create_account,
    get_account_overview,
)
from app.services.finance.account_reconciliation import reconcile_account_balance

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=AccountOverviewResponse)
@router.get("/", response_model=AccountOverviewResponse, include_in_schema=False)
def list_accounts_overview(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOverviewResponse:
    """Return all accounts for the authenticated user with position status and trusted BDT total."""
    return get_account_overview(db, user_id=current.id)


@router.post("", response_model=AccountPositionItem, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=AccountPositionItem, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def add_account(
    payload: AccountCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountPositionItem:
    """Create a new account scoped to the authenticated user."""
    return create_account(db, user_id=current.id, payload=payload)


@router.get("/position", response_model=TrustedBdtPosition)
def get_trusted_position(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrustedBdtPosition:
    """Return the aggregated trusted BDT position for the authenticated user."""
    overview = get_account_overview(db, user_id=current.id)
    return overview.trusted_bdt_position


@router.get("/{account_id}", response_model=AccountPositionItem)
def get_account_item(
    account_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountPositionItem:
    """Return a single account with reconciliation and position status."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == current.id)
        .first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    recon = reconcile_account_balance(db, account=account, user_id=current.id)
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
