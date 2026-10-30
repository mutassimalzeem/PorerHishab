from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.account import Account
from app.models.user import User
from app.schemas.account_reconciliation import (
    AccountBalanceReconciliation,
    AccountBalanceUpdate,
    OpeningBalanceUpdate,
)
from app.services.finance.account_reconciliation import (
    reconcile_account_balance,
)


router = APIRouter(
    prefix="/accounts",
    tags=["account reconciliation"],
)


@router.get(
    "/{account_id}/balance/reconciliation",
    response_model=AccountBalanceReconciliation,
)
def get_balance_reconciliation(
    account_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.user_id == current.id,
        )
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found",
        )

    return reconcile_account_balance(
        db,
        account=account,
        user_id=current.id,
    )


@router.patch(
    "/{account_id}/balance",
    response_model=AccountBalanceReconciliation,
)
def update_account_balance(
    account_id: int,
    payload: AccountBalanceUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.user_id == current.id,
        )
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found",
        )

    account.current_balance = payload.current_balance
    account.balance_source = payload.balance_source
    account.balance_as_of = payload.balance_as_of

    db.commit()
    db.refresh(account)

    return reconcile_account_balance(
        db,
        account=account,
        user_id=current.id,
    )


@router.patch(
    "/{account_id}/balance/opening",
    response_model=AccountBalanceReconciliation,
)
def update_opening_balance(
    account_id: int,
    payload: OpeningBalanceUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.user_id == current.id,
        )
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found",
        )

    account.opening_balance = payload.opening_balance
    account.opening_balance_date = payload.opening_balance_date

    db.commit()
    db.refresh(account)

    return reconcile_account_balance(
        db,
        account=account,
        user_id=current.id,
    )