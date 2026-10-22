from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.services.analytics import (
    get_user_budget_baseline,
    get_user_categories,
    get_user_monthly,
    get_user_summary,
    get_user_top_merchants,
)


def get_summary(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None) -> dict:
    
    return get_user_summary(
        db,
        user_id,
        start_date=start_date,
        end_date=end_date)


def get_categories(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None) -> dict:
    
    return get_user_categories(
        db,
        user_id,
        start_date=start_date,
        end_date=end_date,
    )


def get_monthly(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None) -> list[dict]:
    
    return get_user_monthly(
        db,
        user_id,
        start_date=start_date,
        end_date=end_date)


def get_top_merchants(
    db: Session,
    user_id: int,
    limit: int = 5,
    start_date: date | None = None,
    end_date: date | None = None) -> list[dict]:
    
    return get_user_top_merchants(
        db,
        user_id,
        limit=limit,
        start_date=start_date,
        end_date=end_date)


def get_budget_baseline(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None) -> dict:
    
    return get_user_budget_baseline(
        db,
        user_id,
        start_date=start_date,
        end_date=end_date,
    )