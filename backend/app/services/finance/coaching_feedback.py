"""Visibility overlay; the deterministic generator remains read-only."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingFeedbackRecord
from app.services.finance.coaching import financial_coaching


def evidence_key(item):
    # Store only a digest, never the financial payload. Changed evidence resurfaces advice.
    value = dict(type=item.type, priority=item.priority, amount=str(item.amount),
                 evidence=item.evidence.model_dump(mode="json"))
    if item.type == "upcoming_obligations":
        value["evidence"].pop("period", None)  # Rolling read date is not a new obligation.
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def records(db, user_id, generated):
    current = {item.id: item for item in generated.recommendations if item.valid_until >= generated.as_of_date}
    result = []
    for row in db.query(CoachingFeedback).filter_by(user_id=user_id).order_by(CoachingFeedback.updated_at.desc()).all():
        item = current.get(row.recommendation_id)
        valid = item is not None and evidence_key(item) == row.evidence_key
        hidden = valid and (row.status != "snoozed" or row.snoozed_until > generated.as_of_date)
        result.append(CoachingFeedbackRecord.model_validate(dict(
            recommendation_id=row.recommendation_id, status=row.status, snoozed_until=row.snoozed_until,
            created_at=row.created_at, updated_at=row.updated_at, is_current=valid, is_hidden=hidden)))
    return result


def visible_coaching(db, user_id, *, priority=None, **kwargs):
    generated = financial_coaching(db, user_id, **kwargs)
    generated.feedback = records(db, user_id, generated)
    hidden = {row.recommendation_id for row in generated.feedback if row.is_hidden}
    generated.recommendations = [item for item in generated.recommendations
        if item.valid_until >= generated.as_of_date and item.id not in hidden
        and (priority is None or item.priority == priority)]
    return generated


def submit(db, user_id, recommendation_id, payload, **kwargs):
    generated = financial_coaching(db, user_id, **kwargs)
    item = next((item for item in generated.recommendations
                 if item.id == recommendation_id and item.valid_until >= generated.as_of_date), None)
    if item is None:
        raise HTTPException(404, "Recommendation is no longer current")
    now = datetime.now(timezone.utc)
    values = dict(user_id=user_id, recommendation_id=item.id, evidence_key=evidence_key(item),
                  status=payload.status, snoozed_until=payload.snoozed_until, created_at=now, updated_at=now)
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    statement = insert(CoachingFeedback).values(**values)
    statement = statement.on_conflict_do_update(index_elements=["user_id", "recommendation_id"],
        set_={key: value for key, value in values.items() if key not in {"user_id", "recommendation_id", "created_at"}})
    try:
        db.execute(statement)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return next(row for row in records(db, user_id, generated) if row.recommendation_id == item.id)


def restore(db, user_id, recommendation_id):
    # Stale feedback may be removed too; deleting never turns stale advice into current advice.
    db.query(CoachingFeedback).filter_by(user_id=user_id, recommendation_id=recommendation_id).delete()
    db.commit()
