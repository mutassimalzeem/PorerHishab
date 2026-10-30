"""Authenticated CRUD endpoints for planned income and expenses."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.user import User
from app.schemas.scheduled_cashflow import (
    CashflowKind, CashflowStatus, ScheduledCashflowCreate,
    ScheduledCashflowPage, ScheduledCashflowRead, ScheduledCashflowUpdate,
)

from app.repositories.obligation_reconciliation import allocations, lock_owner
from app.services.finance.obligation_reconciliation import allocated_total

router = APIRouter(prefix="/finance", tags=["finance"])


def get_item_for_user(db: Session, item_id: int, user_id: int) -> ScheduledCashflowItem:
    item = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.id == item_id,
        ScheduledCashflowItem.user_id == user_id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Scheduled cashflow item not found")
    return item


@router.post("/scheduled-cashflow", response_model=ScheduledCashflowRead, status_code=201)
def create_item(payload: ScheduledCashflowCreate,
                current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = ScheduledCashflowItem(user_id=current.id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/scheduled-cashflow", response_model=ScheduledCashflowPage)
def list_items(kind: CashflowKind | None = None, status: CashflowStatus | None = None,
               due_date_from: date | None = None, due_date_to: date | None = None,
               limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if due_date_from and due_date_to and due_date_from > due_date_to:
        raise HTTPException(status_code=422, detail="due_date_from must not exceed due_date_to")
    query = db.query(ScheduledCashflowItem).filter(ScheduledCashflowItem.user_id == current.id)
    if kind is not None:
        query = query.filter(ScheduledCashflowItem.kind == kind)
    if status is not None:
        query = query.filter(ScheduledCashflowItem.status == status)
    if due_date_from is not None:
        query = query.filter(ScheduledCashflowItem.due_date >= due_date_from)
    if due_date_to is not None:
        query = query.filter(ScheduledCashflowItem.due_date <= due_date_to)
    total = query.count()
    items = query.order_by(ScheduledCashflowItem.due_date, ScheduledCashflowItem.id).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/scheduled-cashflow/{item_id}", response_model=ScheduledCashflowRead)
def read_item(item_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_item_for_user(db, item_id, current.id)


@router.patch("/scheduled-cashflow/{item_id}", response_model=ScheduledCashflowRead)
def update_item(item_id: int, payload: ScheduledCashflowUpdate,
                current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_owner(db, current.id)
    # Serialize concurrent transitions so a terminal status cannot be overwritten.
    item = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.id == item_id, ScheduledCashflowItem.user_id == current.id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Scheduled cashflow item not found")
    changes = payload.model_dump(exclude_unset=True)
    if item.status != "scheduled" and changes.get("status", item.status) != item.status:
        raise HTTPException(status_code=409, detail="Paid or cancelled items cannot change status")
    history = allocations(db, current.id, item_id, active=None)
    if history and any(field in changes and changes[field] != getattr(item, field) for field in ("amount", "kind", "due_date")):
        raise HTTPException(409, "Reconciled obligation terms are immutable")
    if history and changes.get("status") == "cancelled":
        raise HTTPException(409, "Reconciled obligations cannot be cancelled")
    if history and changes.get("status") == "paid" and allocated_total(db, current.id, item_id) != item.amount:
        raise HTTPException(409, "Allocations do not fully settle this obligation")
    for field, value in changes.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/scheduled-cashflow/{item_id}", status_code=204)
def delete_item(item_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_owner(db, current.id)
    item = get_item_for_user(db, item_id, current.id)
    if allocations(db, current.id, item_id, active=None):
        raise HTTPException(409, "Reconciled obligation history cannot be deleted")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
