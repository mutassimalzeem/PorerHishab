"""AI-17C review explanations: canonical evidence, hostile output and read-only safety."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, ScheduledCashflowItem
from app.schemas.financial_coach import CoachAction, CoachClaim, CoachResponse
from app.services.finance.financial_coach_generator import FinancialCoachGenerator
from app.services.finance.financial_review import financial_review
from test_goal_planning import data, seed, DAY  # noqa: F401

STAMP = datetime(2026, 11, 1, tzinfo=timezone.utc)
REVIEW_QUESTION = "Explain my financial review"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)

    def forbidden(*args, **kwargs):
        pytest.fail("Review explanation attempted external generation")

    monkeypatch.setattr(FinancialCoachGenerator, "_call_llm", forbidden)
    monkeypatch.setattr(
        "app.services.finance.financial_coach_evidence.today_dhaka", lambda: DAY
    )


@pytest.fixture
def client(data):
    db, users = data
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: users[0]
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def _canonical(db, user, *, schedules_confirmed=True):
    return financial_review(
        db, user.id, as_of=DAY, schedules_confirmed=schedules_confirmed, observed_at=STAMP
    )


def _ask(client, **extra):
    return client.post("/coach/ask", json={"message": REVIEW_QUESTION, **extra})


def test_review_fallback_is_canonical_and_read_only(data, client):
    db, users = data
    seed(db, users[0])
    canonical = _canonical(db, users[0])

    response = _ask(client, schedules_confirmed=True)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["intent"] == "financial_review"
    assert [action["action_id"] for action in body["actions"]] == [
        f"act_{step.step_id}" for step in canonical.execution_plan.steps
    ]
    assert [action["title"] for action in body["actions"]] == [
        step.title for step in canonical.execution_plan.steps
    ]
    assert [action["evidence_ids"] for action in body["actions"]] == [
        step.evidence_ids for step in canonical.execution_plan.steps
    ]
    for action, step in zip(body["actions"], canonical.execution_plan.steps):
        if step.state == "blocked":
            assert "Currently blocked" in action["description"]
        else:
            assert "ready for your review" in action["description"]

    positions = [body["answer"].find(p.title) for p in canonical.decisions.priorities]
    assert positions and all(position >= 0 for position in positions)
    assert positions == sorted(positions)
    for step in canonical.execution_plan.steps:
        assert step.title in body["answer"]

    assert "does not execute or authorize" in body["answer"]
    assert "paid" not in body["answer"].lower()
    assert any(
        item["evidence_id"] == "ev_review_execution_steps" for item in body["evidence"]
    )


def test_review_uses_existing_schedules_confirmation_only_as_completeness(data, client):
    db, users = data
    seed(db, users[0])

    unconfirmed = _ask(client, schedules_confirmed=False).json()
    confirmed = _ask(client, schedules_confirmed=True).json()

    assert unconfirmed["intent"] == confirmed["intent"] == "financial_review"
    assert any(
        item["evidence_id"] == "ev_review_capacity_status"
        for item in unconfirmed["evidence"]
    )
    assert "unavailable" in unconfirmed["answer"].lower()
    assert "capacity is 0" not in unconfirmed["answer"].lower()
    assert "trusted cash is 0" not in unconfirmed["answer"].lower()
    assert any(
        item["evidence_id"] in {
            "ev_review_conservative_monthly_capacity",
            "ev_review_capacity_status",
        }
        for item in confirmed["evidence"]
    )


def test_missing_capacity_is_never_zero(data, client):
    db, users = data
    seed(db, users[0])
    db.query(Account).filter_by(user_id=users[0].id).delete()
    db.commit()

    body = _ask(client, schedules_confirmed=True).json()
    assert body["intent"] == "financial_review"
    assert "not treated as zero" in body["answer"]
    assert "capacity is 0" not in body["answer"].lower()
    assert "trusted cash is 0" not in body["answer"].lower()
    assert any(
        item["evidence_id"] == "ev_review_capacity_status" for item in body["evidence"]
    )
    assert any(
        item["evidence_id"] == "ev_review_trusted_cash_status"
        for item in body["evidence"]
    )


@pytest.mark.parametrize(
    "answer",
    [
        "Your available capacity is 999999 BDT.",
        "I have paid the bill and authorized the transfer.",
        "I have scheduled the allocation and updated the goal.",
        "priority:does_not_exist is ready for review.",
        "step_999_missing is blocked.",
    ],
)
def test_hostile_review_text_is_replaced(data, client, monkeypatch, answer):
    db, users = data
    seed(db, users[0])

    def hostile(self, package, question, **kwargs):
        return CoachResponse(
            intent=package.intent,
            answer=answer,
            claims=[CoachClaim(claim_id="hostile", text=answer, evidence_ids=[])],
            actions=[],
        )

    monkeypatch.setattr(FinancialCoachGenerator, "generate_response", hostile)
    body = _ask(client, schedules_confirmed=True).json()

    assert body["intent"] == "financial_review"
    assert answer not in body["answer"]
    assert "999999" not in body["answer"]
    assert "does not execute or authorize" in body["answer"]


def test_reordered_priorities_and_false_states_are_replaced(data, client, monkeypatch):
    db, users = data
    seed(db, users[0])
    db.add(
        ScheduledCashflowItem(
            user_id=users[0].id,
            title="Rent",
            kind="expense",
            amount=D("5000"),
            due_date=DAY + timedelta(days=2),
            status="scheduled",
        )
    )
    db.commit()
    canonical = _canonical(db, users[0])
    priorities = canonical.decisions.priorities
    steps = canonical.execution_plan.steps
    assert len(priorities) >= 2
    assert len({p.title for p in priorities}) == len(priorities)

    reversed_order = "; ".join(p.title for p in reversed(priorities))
    hostile_answer = f"The priority order is: {reversed_order}."

    def hostile(self, package, question, **kwargs):
        return CoachResponse(intent=package.intent, answer=hostile_answer)

    monkeypatch.setattr(FinancialCoachGenerator, "generate_response", hostile)
    body = _ask(client, schedules_confirmed=True).json()
    assert hostile_answer not in body["answer"]

    step = steps[0]
    wrong_state = "blocked" if step.state == "ready" else "ready"
    false_state = f"{step.title} is {wrong_state}."
    monkeypatch.setattr(
        FinancialCoachGenerator,
        "generate_response",
        lambda self, package, question, **kwargs: CoachResponse(
            intent=package.intent, answer=false_state
        ),
    )
    body = _ask(client, schedules_confirmed=True).json()
    assert false_state not in body["answer"]


def test_llm_actions_cannot_override_canonical_steps(data, client, monkeypatch):
    db, users = data
    seed(db, users[0])
    canonical = _canonical(db, users[0])

    def hostile(self, package, question, **kwargs):
        return CoachResponse(
            intent=package.intent,
            answer="A read-only review is shown.",
            actions=[
                CoachAction(
                    action_id="act_pay_now",
                    title="Pay now",
                    description="Transfer the full balance immediately.",
                    priority=1,
                    evidence_ids=["ev_review_plan"],
                )
            ],
        )

    monkeypatch.setattr(FinancialCoachGenerator, "generate_response", hostile)
    body = _ask(client, schedules_confirmed=True).json()
    assert [action["action_id"] for action in body["actions"]] == [
        f"act_{step.step_id}" for step in canonical.execution_plan.steps
    ]
    assert "Pay now" not in str(body["actions"])


def test_review_scope_is_authenticated_and_ignores_client_context(data, client):
    db, users = data
    seed(db, users[0], target="10000.01")
    other = seed(db, users[1], target="987654.32")
    other.name = "OTHER OWNER SECRET"
    db.commit()

    response = client.post(
        "/coach/ask",
        json={
            "message": REVIEW_QUESTION,
            "schedules_confirmed": True,
            "user_id": users[1].id,
            "as_of": "1900-01-01",
            "priorities": [{"priority_id": "priority:injected"}],
            "execution": [{"action": "pay"}],
        },
    )
    assert response.status_code == 200, response.text
    assert "OTHER OWNER SECRET" not in response.text
    assert "987654.32" not in response.text
    horizon = next(
        item for item in response.json()["evidence"] if item["evidence_id"] == "ev_review_horizon"
    )
    assert horizon["value"]["start"] == str(DAY)


def test_review_explanation_does_not_write_financial_tables(data, client):
    db, users = data
    seed(db, users[0])
    financial_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in {"coach_conversations", "coach_messages", "coach_turns"}
    ]

    def snapshot():
        return {
            table.name: [tuple(row) for row in db.execute(select(table)).all()]
            for table in financial_tables
        }

    before = snapshot()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        body = _ask(client, schedules_confirmed=True).json()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)

    assert body["intent"] == "financial_review"
    assert snapshot() == before
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
        if "coach_" not in statement
    )


def test_review_requires_authentication(client):
    app.dependency_overrides.pop(get_current_user)
    assert client.post("/coach/ask", json={"message": REVIEW_QUESTION}).status_code == 401


def test_existing_coach_intents_are_preserved(data, client):
    db, users = data
    seed(db, users[0])
    for question, intent in [
        ("How much did I spend this month?", "spending_analysis"),
        ("What is my cashflow and projected balance?", "cashflow"),
        ("How are my savings goals doing?", "goal_planning"),
    ]:
        response = client.post("/coach/ask", json={"message": question})
        assert response.status_code == 200, response.text
        assert response.json()["intent"] == intent


@pytest.mark.parametrize("cash_only", [False, True])
def test_review_without_goals(data, client, cash_only):
    db, users = data
    if cash_only:
        from app.models import SavingsGoal
        seed(db, users[0])
        db.query(SavingsGoal).filter_by(user_id=users[0].id).delete()
        db.commit()
    response = _ask(client)
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "financial_review"
    assert "does not execute or authorize" in body["answer"]
    assert body["answer"]


def test_mismatched_review_date_is_not_explained(data, client, monkeypatch):
    db, users = data
    seed(db, users[0])
    stale = financial_review(db, users[0].id, as_of=DAY - timedelta(days=1))
    monkeypatch.setattr("app.services.finance.financial_review.financial_review", lambda *a, **k: stale)
    response = _ask(client)
    assert response.status_code == 500
    assert "Laptop" not in response.text


def test_review_stays_deterministic_with_provider_enabled(data, client, monkeypatch):
    db, users = data
    seed(db, users[0])
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)
    response = _ask(client)
    assert response.status_code == 200
    assert "does not execute or authorize" in response.json()["answer"]


def test_bengali_review_explanation(data, client):
    response = client.post("/coach/ask?language=bn", json={"message": REVIEW_QUESTION})
    assert response.status_code == 200
    assert response.json()["intent"] == "financial_review"
    assert "পর্যালোচনা" in response.json()["answer"]
