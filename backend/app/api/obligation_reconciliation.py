from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.schemas.obligation_reconciliation import ConfirmAllocation, ObligationReconciliation, ReconciliationPage
from app.repositories.obligation_reconciliation import allocations, eligible_transactions
from app.services.finance.obligation_reconciliation import reconcile, confirm, revoke
router = APIRouter(prefix="/finance/scheduled-cashflow", tags=["finance"])

@router.get("/reconciliation", response_model=ReconciliationPage)
def overview(as_of: date | None = None, date_tolerance_days: int = Query(7, ge=0, le=90),
             amount_tolerance: Decimal = Query(Decimal("0.00"), ge=0, le=1000000, decimal_places=2),
             limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
             current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(ScheduledCashflowItem).filter_by(user_id=current.id)
    items = query.order_by(ScheduledCashflowItem.due_date, ScheduledCashflowItem.id).offset(offset).limit(limit).all()
    snapshot = (allocations(db, current.id, active=None), eligible_transactions(db, current.id))
    return dict(items=[reconcile(db, current.id, item.id, as_of=as_of, date_tolerance_days=date_tolerance_days,
                               amount_tolerance=amount_tolerance, snapshot=snapshot) for item in items], total=query.count(), limit=limit, offset=offset)

@router.get("/{item_id}/matches", response_model=ObligationReconciliation)
def matches(item_id: int, as_of: date | None = None, date_tolerance_days: int = Query(7, ge=0, le=90),
            amount_tolerance: Decimal = Query(Decimal("0.00"), ge=0, le=1000000, decimal_places=2),
            current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return reconcile(db, current.id, item_id, as_of=as_of, date_tolerance_days=date_tolerance_days, amount_tolerance=amount_tolerance)

@router.post("/{item_id}/matches/{transaction_id}/confirm", response_model=ObligationReconciliation)
def confirm_match(item_id: int, transaction_id: int, payload: ConfirmAllocation,
                  current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return confirm(db, current.id, item_id, transaction_id, payload.confirm_full_settlement)

@router.delete("/{item_id}/matches/{transaction_id}", response_model=ObligationReconciliation)
def remove_match(item_id: int, transaction_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return revoke(db, current.id, item_id, transaction_id)
