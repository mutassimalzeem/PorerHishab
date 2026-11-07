"""SQLAlchemy models for financial coach conversations and messages (AI-15S-F / AI-15S-K)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _gen_conversation_id() -> str:
    return f"conv_{uuid.uuid4().hex[:16]}"


class CoachConversation(Base):
    """A financial coaching conversation thread belonging to an authenticated user."""

    __tablename__ = "coach_conversations"

    __table_args__ = (
        Index("ix_coach_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=_gen_conversation_id,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Financial Coaching",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    messages = relationship(
        "CoachMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="CoachMessage.created_at",
    )


class CoachMessage(Base):
    """An individual message turn within a financial coach conversation."""

    __tablename__ = "coach_messages"

    __table_args__ = (
        Index("ix_coach_messages_conversation_created", "conversation_id", "created_at"),
        UniqueConstraint("user_id", "request_id", "role", name="uq_coach_message_request_role"),
    )

    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("coach_conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),  # "user" or "assistant"
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    intent: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    claims_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    actions_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    evidence_ids_json: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    evidence_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    warnings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    limitations_json: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    conversation = relationship(
        "CoachConversation",
        back_populates="messages",
    )


class CoachTurn(Base):
    """Durable request receipt, lease and canonical completion; no financial writes."""

    __tablename__ = "coach_turns"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_coach_turn_owner_request"),
        CheckConstraint("state IN ('processing', 'failed', 'completed')", name="ck_coach_turn_state"),
        Index("ix_coach_turn_conversation", "conversation_id", "id"),
        Index("uq_coach_turn_processing", "conversation_id", unique=True,
              postgresql_where=text("state = 'processing'"),
              sqlite_where=text("state = 'processing'")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("coach_conversations.id", ondelete="CASCADE"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    schedules_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
