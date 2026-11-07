"""Offline runtime-chain, authenticated isolation and read-only regressions."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Account, SavingsGoal
from app.services.finance import financial_review as review
from app.services.finance.financial_planner import build_financial_plan
from app.services.finance.financial_prioritization import prioritize_financial_plan
from app.services.finance.financial_execution import build_financial_execution_plan
from test_goal_planning import data, seed, DAY  # noqa: F401

STAMP = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from app.services.finance.financial_coach_generator import FinancialCoachGenerator
    def forbidden(*args, **kwargs):
        pytest.fail("Review attempted external generation")
    monkeypatch.setattr(FinancialCoachGenerator, "_call_llm", forbidden)


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


def test_actual_chain_and_stage_arguments(data, monkeypatch):
    db, users = data
    seed(db, users[0])
    calls = []
    for name, implementation in [("build_financial_plan", build_financial_plan),
                                 ("prioritize_financial_plan", prioritize_financial_plan),
                                 ("build_financial_execution_plan", build_financial_execution_plan)]:
        def spy(*args, _name=name, _implementation=implementation, **kwargs):
            output = _implementation(*args, **kwargs)
            calls.append((_name, args, kwargs, output))
            return output
        monkeypatch.setattr(review, name, spy)
    result = review.financial_review(db, users[0].id, as_of=DAY,
                                    schedules_confirmed=True, observed_at=STAMP)
    assert [c[0] for c in calls] == ["build_financial_plan", "prioritize_financial_plan", "build_financial_execution_plan"]
    assert calls[1][1][0] is calls[0][3]
    assert calls[2][1][0] is calls[1][3]
    assert calls[0][1][0].as_of_date == DAY
    assert calls[0][2]["goal_planning"].capacity.as_of_date == DAY
    assert calls[0][2]["financial_health"].as_of_date == DAY
    assert result.plan == calls[0][3]
    assert result.decisions == prioritize_financial_plan(result.plan)
    assert result.execution_plan == build_financial_execution_plan(result.decisions)
    assert result.execution_plan.steps
    assert [s.priority_id for s in result.execution_plan.steps] == [p.priority_id for p in result.decisions.priorities]
    assert result.execution_plan.evidence == result.decisions.evidence
    assert result.execution_plan.warnings == result.decisions.warnings
    for step, priority in zip(result.execution_plan.steps, result.decisions.priorities):
        assert step.blocking_priority_ids == priority.blocking_priority_ids
        assert step.blocking_factors == priority.blocking_factors
        assert step.assumptions == priority.assumptions
        assert step.requires_user_confirmation is True
    assert result.model_dump_json() == review.financial_review(
        db, users[0].id, as_of=DAY, schedules_confirmed=True, observed_at=STAMP).model_dump_json()


@pytest.mark.parametrize("case", ["empty", "unconfirmed", "missing_cash", "zero_cash", "missing_progress"])
def test_missing_inputs_and_real_zero(data, case):
    db, users = data
    if case != "empty":
        seed(db, users[0], cash="0" if case == "zero_cash" else "100000",
             saved=None if case == "missing_progress" else "0")
    if case == "missing_cash":
        db.query(Account).filter_by(user_id=users[0].id).delete()
        db.commit()
    result = review.financial_review(db, users[0].id, as_of=DAY,
                                    schedules_confirmed=case != "unconfirmed", observed_at=STAMP)
    capacity = result.plan.goal_planning.capacity
    if case == "zero_cash":
        assert capacity.trusted_cash == Decimal("0")
        assert capacity.conservative_monthly_capacity == Decimal("0")
        assert capacity.status == "sufficient"
    else:
        assert capacity.conservative_monthly_capacity is None
        assert capacity.status == "insufficient_data"
        assert any(w.code == "UNKNOWN_PLANNING_CAPACITY" for w in result.plan.warnings)
    if case in {"empty", "missing_cash"}:
        assert capacity.trusted_cash is None
    if case != "empty":
        assert any(s.state == "blocked" for s in result.execution_plan.steps)
    assert result.status == "review_only"


def test_default_shared_date(data, monkeypatch):
    db, users = data
    monkeypatch.setattr(review, "today_dhaka", lambda: DAY)
    result = review.financial_review(db, users[0].id, observed_at=STAMP)
    assert result.plan.as_of_date == result.decisions.as_of_date == result.execution_plan.as_of_date == DAY


def test_api_tenant_isolation_and_no_writes(data, client):
    db, users = data
    first = seed(db, users[0], target="10000.01")
    other = seed(db, users[1], target="987654.32")
    other.name = "OTHER OWNER SECRET"
    db.commit()
    def snapshot():
        return {t.name: [tuple(r) for r in db.execute(select(t)).all()] for t in Base.metadata.sorted_tables}
    before = snapshot()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        response = client.get(f"/finance/review?as_of={DAY}&schedules_confirmed=true&user_id={users[1].id}")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [g["goal_id"] for g in body["plan"]["goal_planning"]["goals"]] == [first.id]
    assert "OTHER OWNER SECRET" not in response.text
    assert "987654.32" not in response.text
    assert snapshot() == before
    assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements)
    app.dependency_overrides[get_current_user] = lambda: users[1]
    second = client.get(f"/finance/review?as_of={DAY}").json()
    assert [g["goal_id"] for g in second["plan"]["goal_planning"]["goals"]] == [other.id]
    assert client.post("/finance/review").status_code == 405


def test_authentication_required(client):
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/finance/review").status_code == 401
    assert client.get("/finance/review", headers={"Authorization": "Bearer invalid"}).status_code == 401


@pytest.mark.parametrize("query", ["as_of=invalid", "as_of=1899-12-31", "as_of=9999-12-31", "schedules_confirmed=maybe"])
def test_parameter_validation(client, query):
    assert client.get("/finance/review?" + query).status_code == 422


def test_internal_failure_is_sanitized(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private database connection and owner secret")
    monkeypatch.setattr("app.api.financial_review.financial_review", fail)
    response = client.get("/finance/review")
    assert response.status_code == 500
    assert response.json() == {"detail": "Financial review is temporarily unavailable"}


def test_registered_contract():
    spec = app.openapi()
    operation = spec["paths"]["/finance/review"]["get"]
    assert operation["security"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/FinancialReview")
    assert {p["name"] for p in operation["parameters"]} == {"as_of", "schedules_confirmed"}
    assert set(spec["components"]["schemas"]["FinancialReview"]["properties"]) == {
        "status", "requires_user_confirmation", "schedules_confirmed", "plan", "decisions", "execution_plan"}


@pytest.mark.parametrize("user_id", [0, -1])
def test_invalid_service_scope(data, user_id):
    with pytest.raises(ValueError, match="scope"):
        review.financial_review(data[0], user_id, as_of=DAY)


def test_feedback_visible_inputs_are_preserved(data):
    from app.services.finance.coaching_feedback import submit
    from app.schemas.coaching import CoachingFeedbackInput
    db, users = data
    seed(db, users[0], cash="0")
    before = review.financial_review(db, users[0].id, as_of=DAY, observed_at=STAMP)
    coaching = review.visible_coaching(db, users[0].id, as_of=DAY)
    assert coaching.recommendations
    hidden = coaching.recommendations[0].id
    submit(db, users[0].id, hidden, CoachingFeedbackInput(status="dismissed"), as_of=DAY)
    after = review.financial_review(db, users[0].id, as_of=DAY, observed_at=STAMP)
    assert hidden in {a.recommendation_id for a in before.plan.actions}
    assert hidden not in {a.recommendation_id for a in after.plan.actions}
    assert all(hidden not in p.source_action_ids for p in after.decisions.priorities)
    assert after.decisions.warnings == after.plan.warnings
    assert set(after.plan.limitations) <= set(after.decisions.limitations)
    assert set(after.decisions.limitations) <= set(after.execution_plan.limitations)


def test_financial_review_recommendation_to_reported_outcome(
    data, client, monkeypatch
):
    """A review-linked coaching recommendation can be reported and observed."""
    from app.services.finance.coaching import financial_coaching

    db, users = data
    user = users[0]

    # Keep all services on the same deterministic Dhaka date.
    monkeypatch.setattr(
        "app.services.finance.coaching.today_dhaka", lambda: DAY
    )
    monkeypatch.setattr(
        "app.services.finance.action_outcome.today_dhaka", lambda: DAY
    )

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            dt = datetime(DAY.year, DAY.month, DAY.day, 12, tzinfo=timezone.utc)
            return dt if tz is not None else dt.replace(tzinfo=None)

    monkeypatch.setattr(
        "app.services.finance.coaching_feedback.datetime", FrozenDatetime
    )

    seed(db, user, cash="0")

    # Fetch the real financial review through the authenticated API.
    review_response = client.get(
        f"/finance/review?as_of={DAY}&schedules_confirmed=true"
    )
    assert review_response.status_code == 200, review_response.text
    review_body = review_response.json()

    review_source_ids = {
        source_id
        for step in review_body["execution_plan"]["steps"]
        for source_id in step["source_action_ids"]
    }
    assert review_source_ids

    # Only IDs that also exist as current coaching recommendations are valid
    # feedback targets. This excludes synthetic plan:* identifiers.
    current_recommendation_ids = {
        rec.id
        for rec in financial_coaching(db, user.id, as_of=DAY).recommendations
    }
    valid_review_recommendation_ids = review_source_ids & current_recommendation_ids
    assert valid_review_recommendation_ids, (
        f"Expected review execution steps to contain a valid current coaching "
        f"recommendation ID, got review_source_ids={review_source_ids} and "
        f"current_recommendation_ids={current_recommendation_ids}"
    )

    # Synthetic plan identifiers must never be accepted as feedback targets.
    for synthetic_id in [s for s in review_source_ids if s.startswith("plan:")]:
        rejected = client.put(
            f"/finance/coaching/{synthetic_id}/feedback",
            json={"status": "acted_on"},
        )
        assert rejected.status_code == 404

    target_id = next(iter(valid_review_recommendation_ids))

    # Before feedback, this recommendation has no reported outcome.
    before = client.get(
        f"/finance/action-outcomes?recommendation_id={target_id}"
    )
    assert before.status_code == 404

    # The authenticated user explicitly reports acting on the recommendation.
    feedback = client.put(
        f"/finance/coaching/{target_id}/feedback",
        json={"status": "acted_on"},
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["status"] == "acted_on"
    assert feedback.json()["recommendation_id"] == target_id

    # The report is now visible through the existing feedback endpoint.
    history = client.get("/finance/coaching/feedback")
    assert history.status_code == 200
    assert any(
        row["recommendation_id"] == target_id
        and row["status"] == "acted_on"
        for row in history.json()
    )

    # The outcome endpoint derives an observation from recorded evidence.
    response = client.get(
        f"/finance/action-outcomes?recommendation_id={target_id}"
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["summary"]["tracked"] == 1
    assert len(report["items"]) == 1

    outcome = report["items"][0]
    assert outcome["recommendation_id"] == target_id
    assert outcome["causal_claim"] is False
    assert outcome["status"] in {
        "pending",
        "insufficient_data",
        "improved",
        "unchanged",
        "worsened",
    }
