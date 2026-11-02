"""Unit tests for financial coach conversation and message persistence (AI-15S-F)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import User
from app.models.financial_coach import CoachConversation, CoachMessage
from app.schemas.financial_coach import (
    CoachAction,
    CoachClaim,
    CoachEvidence,
    CoachIntent,
    CoachResponse,
    EvidenceType,
)
from app.services.finance.financial_coach_persistence import (
    append_assistant_message,
    append_user_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    get_recent_history_context,
    list_conversations,
)

DAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def users(db_session):
    u1 = User(email="user1@example.com", hashed_password="pw1")
    u2 = User(email="user2@example.com", hashed_password="pw2")
    db_session.add_all([u1, u2])
    db_session.commit()
    return u1, u2


def test_create_and_get_conversation(db_session, users):
    u1, _ = users
    conv = create_conversation(db_session, u1.id, title="October Spending Review")
    assert conv.id.startswith("conv_")
    assert conv.user_id == u1.id
    assert conv.title == "October Spending Review"

    fetched = get_conversation(db_session, u1.id, conv.id)
    assert fetched is not None
    assert fetched.id == conv.id


def test_cross_user_conversation_isolation(db_session, users):
    u1, u2 = users
    conv_u1 = create_conversation(db_session, u1.id, title="User 1 Thread")

    # u2 cannot access u1's conversation
    assert get_conversation(db_session, u2.id, conv_u1.id) is None
    assert delete_conversation(db_session, u2.id, conv_u1.id) is False

    # u2 appending message to u1's conversation raises ValueError
    with pytest.raises(ValueError):
        append_user_message(db_session, u2.id, conv_u1.id, "Attempted intrusion")


def test_list_conversations_ordering_and_pagination(db_session, users):
    u1, _ = users
    c1 = create_conversation(db_session, u1.id, title="Thread 1")
    c2 = create_conversation(db_session, u1.id, title="Thread 2")
    c2.updated_at = c1.updated_at + timedelta(seconds=5)
    db_session.commit()

    items, total = list_conversations(db_session, u1.id, limit=10)
    assert total == 2
    assert len(items) == 2
    assert items[0].id == c2.id  # most recent first


def test_append_messages_and_retrieval(db_session, users):
    u1, _ = users
    conv = create_conversation(db_session, u1.id, title="Cashflow Advice")

    user_msg = append_user_message(db_session, u1.id, conv.id, "Can I afford 15000 BDT?")
    assert user_msg.role == "user"
    assert user_msg.content == "Can I afford 15000 BDT?"

    coach_resp = CoachResponse(
        conversation_id=conv.id,
        intent=CoachIntent.AFFORDABILITY,
        answer="Yes, after reserving scheduled expenses, 22,000 BDT remains.",
        summary="Recommended purchase.",
        claims=[
            CoachClaim(
                claim_id="cl_1",
                text="Remaining balance is 22,000 BDT.",
                evidence_ids=["ev_affordability_remaining_balance"],
            )
        ],
        evidence=[
            CoachEvidence(
                evidence_id="ev_affordability_remaining_balance",
                evidence_type=EvidenceType.DERIVED_FACT,
                source="finance.coach_purchase",
                label="Remaining",
                value=D("22000.00"),
                unit="BDT",
            )
        ],
        actions=[
            CoachAction(
                action_id="act_1",
                title="Review bills",
                description="Check pending bills.",
                priority=1,
                evidence_ids=["ev_affordability_remaining_balance"],
            )
        ],
    )

    asst_msg = append_assistant_message(db_session, u1.id, conv.id, coach_resp)
    assert asst_msg.role == "assistant"
    assert asst_msg.intent == "affordability"
    assert asst_msg.evidence_ids_json == ["ev_affordability_remaining_balance"]

    messages = get_conversation_messages(db_session, u1.id, conv.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"


def test_get_recent_history_context(db_session, users):
    u1, _ = users
    conv = create_conversation(db_session, u1.id, title="Multi-turn conversation")

    for i in range(5):
        append_user_message(db_session, u1.id, conv.id, f"Question {i}")

    # Limit to 3
    context = get_recent_history_context(db_session, u1.id, conv.id, limit=3)
    assert len(context) == 3
    # Check chronological ordering
    assert context[0]["content"] == "Question 2"
    assert context[1]["content"] == "Question 3"
    assert context[2]["content"] == "Question 4"


def test_delete_conversation_cascades(db_session, users):
    u1, _ = users
    conv = create_conversation(db_session, u1.id, title="Thread to Delete")
    append_user_message(db_session, u1.id, conv.id, "Will this be deleted?")

    assert delete_conversation(db_session, u1.id, conv.id) is True
    assert get_conversation(db_session, u1.id, conv.id) is None
    # Messages should be deleted
    assert len(get_conversation_messages(db_session, u1.id, conv.id)) == 0

