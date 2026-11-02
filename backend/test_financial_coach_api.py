"""Integration tests for financial coach FastAPI orchestration (AI-15S-G)."""

from datetime import date, datetime, timezone
from decimal import Decimal as D
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.auth import create_access_token
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models import Account, ScheduledCashflowItem, Transaction, User
from app.models.financial_coach import CoachConversation, CoachMessage
from app.schemas.financial_coach import CoachIntent

DAY = date(2026, 11, 1)
NOW = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def test_setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with Session(engine, expire_on_commit=False) as session:
        u1 = User(email="coach_api_u1@example.com", hashed_password="pw1")
        u2 = User(email="coach_api_u2@example.com", hashed_password="pw2")
        session.add_all([u1, u2])
        session.commit()
        session.refresh(u1)
        session.refresh(u2)

        # Seed u1 records
        session.add(
            Account(
                user_id=u1.id,
                name="Primary Account",
                currency="BDT",
                opening_balance=D("60000.00"),
                opening_balance_date=date(2026, 8, 1),
                current_balance=D("60000.00"),
                balance_as_of=NOW,
            )
        )
        session.add(
            Transaction(
                user_id=u1.id,
                date=DAY,
                amount=-D("2500.00"),
                category="Groceries",
            )
        )
        session.commit()

        token1 = create_access_token({"sub": u1.email, "user_id": u1.id})
        token2 = create_access_token({"sub": u2.email, "user_id": u2.id})
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        client = TestClient(app)

        yield {
            "client": client,
            "session": session,
            "u1": u1,
            "u2": u2,
            "headers1": headers1,
            "headers2": headers2,
        }

    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_unauthenticated_request_rejected(test_setup):
    client = test_setup["client"]
    res = client.post("/coach/ask", json={"message": "How much did I spend?"})
    assert res.status_code == 401


def test_empty_message_validation(test_setup):
    client = test_setup["client"]
    headers = test_setup["headers1"]
    res = client.post("/coach/ask", headers=headers, json={"message": "   "})
    assert res.status_code == 422


def test_successful_coach_ask_creates_conversation(test_setup):
    client = test_setup["client"]
    headers = test_setup["headers1"]

    res = client.post(
        "/coach/ask",
        headers=headers,
        json={"message": "How much did I spend this month?"},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["intent"] == "spending_analysis"
    assert "2500" in data["answer"]
    assert data["conversation_id"] is not None
    assert len(data["evidence"]) >= 1
    assert any(e["evidence_id"] == "ev_spending_total_expenses" for e in data["evidence"])

    # Verify conversation and messages were persisted
    conv_id = data["conversation_id"]
    conv_res = client.get(f"/coach/conversations/{conv_id}", headers=headers)
    assert conv_res.status_code == 200
    conv_data = conv_res.json()
    assert len(conv_data["messages"]) == 2
    assert conv_data["messages"][0]["role"] == "user"
    assert conv_data["messages"][1]["role"] == "assistant"


def test_conversation_continuation(test_setup):
    client = test_setup["client"]
    headers = test_setup["headers1"]

    # First turn
    turn1 = client.post(
        "/coach/ask",
        headers=headers,
        json={"message": "How much did I spend this month?"},
    ).json()
    conv_id = turn1["conversation_id"]

    # Second turn with conversation_id
    turn2 = client.post(
        "/coach/ask",
        headers=headers,
        json={"message": "What is my cashflow and projected balance?", "conversation_id": conv_id},
    ).json()

    assert turn2["conversation_id"] == conv_id
    assert turn2["intent"] == "cashflow"

    # Verify 4 messages in conversation
    conv_res = client.get(f"/coach/conversations/{conv_id}", headers=headers).json()
    assert len(conv_res["messages"]) == 4


def test_cross_user_conversation_denial(test_setup):
    client = test_setup["client"]
    headers1 = test_setup["headers1"]
    headers2 = test_setup["headers2"]

    # User 1 creates conversation
    turn1 = client.post(
        "/coach/ask",
        headers=headers1,
        json={"message": "How much did I spend this month?"},
    ).json()
    conv_id = turn1["conversation_id"]

    # User 2 attempts to continue User 1's conversation -> 404
    intrusion_res = client.post(
        "/coach/ask",
        headers=headers2,
        json={"message": "Spy question", "conversation_id": conv_id},
    )
    assert intrusion_res.status_code == 404

    # User 2 attempts to read User 1's conversation -> 404
    get_res = client.get(f"/coach/conversations/{conv_id}", headers=headers2)
    assert get_res.status_code == 404

    # User 2 attempts to delete User 1's conversation -> 404
    del_res = client.delete(f"/coach/conversations/{conv_id}", headers=headers2)
    assert del_res.status_code == 404


def test_unknown_intent_clarification_no_llm_call(test_setup):
    client = test_setup["client"]
    headers = test_setup["headers1"]

    with patch("app.services.ai.provider.build_chat_model") as mock_chat:
        res = client.post(
            "/coach/ask",
            headers=headers,
            json={"message": "What is the capital of France?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["intent"] == "unknown"
        assert len(data["warnings"]) >= 1
        assert not mock_chat.called


def test_conversations_listing_and_deletion(test_setup):
    client = test_setup["client"]
    headers = test_setup["headers1"]

    # Create 2 conversations
    c1 = client.post("/coach/ask", headers=headers, json={"message": "Spending question"}).json()["conversation_id"]
    c2 = client.post("/coach/ask", headers=headers, json={"message": "Cashflow question"}).json()["conversation_id"]

    list_res = client.get("/coach/conversations?limit=10", headers=headers)
    assert list_res.status_code == 200
    listing = list_res.json()
    assert listing["total"] == 2
    assert len(listing["items"]) == 2

    # Delete c1
    del_res = client.delete(f"/coach/conversations/{c1}", headers=headers)
    assert del_res.status_code == 204

    # Verify c1 is gone
    check_del = client.get(f"/coach/conversations/{c1}", headers=headers)
    assert check_del.status_code == 404
