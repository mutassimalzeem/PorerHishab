"""Conversation and message persistence service for the financial coach (AI-15S-F / AI-15S-K).

Manages user-scoped coaching conversations and message histories.
Strictly enforces single-tenant isolation: queries and mutations must verify ownership.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.financial_coach import CoachConversation, CoachMessage
from app.schemas.financial_coach import CoachResponse

logger = logging.getLogger(__name__)


def _make_json_safe(obj: Any) -> Any:
    """Recursively convert Decimals, dates, and non-primitive objects to JSON-serializable types."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(x) for x in obj]
    return obj


def create_conversation(
    db: Session,
    user_id: int,
    title: str | None = None,
) -> CoachConversation:
    """Create a new financial coach conversation for the user."""
    conv = CoachConversation(
        user_id=user_id,
        title=title or "Financial Coaching",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(
    db: Session,
    user_id: int,
    conversation_id: str,
) -> CoachConversation | None:
    """Retrieve a conversation if owned by the user."""
    return (
        db.query(CoachConversation)
        .filter(
            CoachConversation.id == conversation_id,
            CoachConversation.user_id == user_id,
        )
        .first()
    )


def list_conversations(
    db: Session,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CoachConversation], int]:
    """List conversations belonging to the user ordered by recent activity."""
    query = db.query(CoachConversation).filter(CoachConversation.user_id == user_id)
    total = query.count()
    items = (
        query.order_by(CoachConversation.updated_at.desc(), CoachConversation.id.desc())
        .offset(offset)
        .limit(min(max(1, limit), 100))
        .all()
    )
    return items, total


def delete_conversation(
    db: Session,
    user_id: int,
    conversation_id: str,
) -> bool:
    """Delete a conversation and all its messages."""
    conv = get_conversation(db, user_id, conversation_id)
    if not conv:
        return False

    # Explicitly delete all associated messages for strict cleanup
    db.query(CoachMessage).filter(
        CoachMessage.conversation_id == conversation_id,
        CoachMessage.user_id == user_id,
    ).delete(synchronize_session=False)

    db.delete(conv)
    db.commit()
    return True


def append_user_message(
    db: Session,
    user_id: int,
    conversation_id: str,
    content: str,
) -> CoachMessage:
    """Append a user question to the conversation.

    If the previous message in this conversation was an uncompleted turn
    with the exact same question (e.g. following a failed request), reuses
    that turn rather than creating duplicate persisted messages.
    """
    conv = get_conversation(db, user_id, conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found or access denied.")

    clean_content = content.strip()
    now = datetime.now(timezone.utc)
    conv.updated_at = now

    # Check for uncompleted user message retry
    last_msg = (
        db.query(CoachMessage)
        .filter(
            CoachMessage.conversation_id == conversation_id,
            CoachMessage.user_id == user_id,
        )
        .order_by(CoachMessage.id.desc())
        .first()
    )
    if last_msg and last_msg.role == "user" and last_msg.content == clean_content:
        # Re-use existing user turn from uncompleted attempt
        return last_msg

    msg = CoachMessage(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=clean_content,
        created_at=now,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def append_assistant_message(
    db: Session,
    user_id: int,
    conversation_id: str,
    response: CoachResponse,
) -> CoachMessage:
    """Append the coach's structured answer and evidence to the conversation."""
    conv = get_conversation(db, user_id, conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found or access denied.")

    now = datetime.now(timezone.utc)
    conv.updated_at = now

    # Extract safe metadata without sensitive records
    claims_data = [c.model_dump(mode="json") for c in response.claims]
    actions_data = [a.model_dump(mode="json") for a in response.actions]
    evidence_ids = [e.evidence_id for e in response.evidence]
    evidence_data = [
        {
            "evidence_id": e.evidence_id,
            "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
            "source": e.source,
            "label": e.label,
            "value": _make_json_safe(e.value),
            "unit": e.unit,
            "as_of_date": str(e.as_of_date) if e.as_of_date else None,
        }
        for e in response.evidence
    ]
    warnings_data = [w.model_dump(mode="json") for w in response.warnings]

    msg = CoachMessage(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=response.answer,
        intent=response.intent.value if response.intent else None,
        summary=response.summary,
        claims_json=claims_data,
        actions_json=actions_data,
        evidence_ids_json=evidence_ids,
        evidence_json=evidence_data,
        warnings_json=warnings_data,
        limitations_json=response.limitations,
        created_at=now,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_conversation_messages(
    db: Session,
    user_id: int,
    conversation_id: str,
    limit: int = 50,
) -> list[CoachMessage]:
    """Retrieve chronological messages for an owned conversation."""
    conv = get_conversation(db, user_id, conversation_id)
    if not conv:
        return []

    return (
        db.query(CoachMessage)
        .filter(
            CoachMessage.conversation_id == conversation_id,
            CoachMessage.user_id == user_id,
        )
        .order_by(CoachMessage.created_at.asc(), CoachMessage.id.asc())
        .limit(min(max(1, limit), 200))
        .all()
    )


def get_recent_history_context(
    db: Session,
    user_id: int,
    conversation_id: str,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Retrieve bounded recent message exchanges for LLM context."""
    conv = get_conversation(db, user_id, conversation_id)
    if not conv:
        return []

    # Get recent messages
    recent_msgs = (
        db.query(CoachMessage)
        .filter(
            CoachMessage.conversation_id == conversation_id,
            CoachMessage.user_id == user_id,
        )
        .order_by(CoachMessage.created_at.desc(), CoachMessage.id.desc())
        .limit(min(max(1, limit), 20))
        .all()
    )

    # Reverse back to chronological order
    recent_msgs.reverse()

    return [
        {"role": m.role, "content": m.content}
        for m in recent_msgs
    ]
