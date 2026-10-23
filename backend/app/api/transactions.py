"""Transaction CRUD endpoints.

Uses the shared :func:`app.core.dependencies.get_current_user` dependency, so
every row written or read here is bound to the authenticated user.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.transactions import Transaction
from app.models.user import User
from app.repositories.transaction_repository import (
    count_transactions,
    create_transactions,
    search_transactions,
    get_transaction_for_user
)
from app.schemas.transactions import (
    TransactionCreate,
    TransactionPage,
    TransactionRead,
    TransactionCategoryUpdate
)

from app.models.category_correction import TransactionCategoryCorrection
from app.models.transactions import Transaction

from app.services.categorization.categorizer import categorize_text

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionPage)
def list_transactions(
    q: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    category: list[str] | None = Query(
        None, description="Filter by categories, e.g. ?category=Food&category=Utilities"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("desc", pattern="^(asc|desc)$"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated, filterable list of the authenticated user's transactions."""
    items = search_transactions(
        db=db,
        user_id=current.id,
        q=q,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        categories=category,
        limit=limit,
        offset=offset,
        sort=sort,
    )

    total = count_transactions(
        db=db,
        user_id=current.id,
        q=q,
        start_date=start_date,
        end_date=end_date,
        min_amount=min_amount,
        max_amount=max_amount,
        categories=category,
    )

    return TransactionPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.post("", response_model=TransactionRead, status_code=201)
def create_transaction(
    payload: TransactionCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a single transaction for the authenticated user.

    When ``category`` is omitted, the rule-based categorizer derives one from
    the merchant/description text.  ``transaction_type`` defaults to
    ``expense``/``income`` based on the amount's sign.
    """
    category = payload.category

    if not category:
        text = " ".join(
            value
            for value in [payload.merchant, payload.description]
            if value
        )
        category = categorize_text(text) or None

    transaction_type = payload.transaction_type

    if not transaction_type:
        transaction_type = "expense" if payload.amount < 0 else "income"

    transaction = Transaction(
        user_id=current.id,
        account_id=payload.account_id,
        trx_id=payload.trx_id,
        date=payload.date,
        description=payload.description,
        merchant=payload.merchant,
        amount=payload.amount,
        fee=payload.fee,
        balance=payload.balance,
        transaction_type=transaction_type,
        category=category,
        subcategory=payload.subcategory,
        source=payload.source or "manual",
        is_recurring=payload.is_recurring,
        raw_data=payload.raw_data,
    )

    try:
        create_transactions(db, [transaction])
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A transaction with this trx_id already exists for the user",
        )

    return transaction



@router.patch("/{transaction_id}/category",response_model=TransactionRead)
def update_transaction_category(
    transaction_id: int,
    payload: TransactionCategoryUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allow the authenticated user to manually correct a transaction category."""

    transaction = get_transaction_for_user(
        db=db,
        transaction_id=transaction_id,
        user_id=current.id,
    )

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    old_category = transaction.category
    old_method = transaction.category_method

    if old_category == payload.category:
        return transaction

    correction = TransactionCategoryCorrection(
        user_id=current.id,
        transaction_id=transaction.id,
        old_category=old_category,
        new_category=payload.category,
        old_method=old_method,
    )

    transaction.category = payload.category
    transaction.category_confidence = 1.000
    transaction.category_method = "user"
    transaction.category_reason = (
        f"User changed category from "
        f"'{old_category}' to '{payload.category}'."
    )

    try:
        db.add(correction)
        db.commit()
        db.refresh(transaction)

    except Exception:
        db.rollback()
        raise

    return transaction