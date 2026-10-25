"""Offline, database-backed coach contracts and adversarial ownership checks."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.api.auth import create_access_token
from app.core.database import SessionLocal
from app.core.config import settings
from app.main import app
from app.models import User, Transaction, Account, ScheduledCashflowItem, SavingsGoal
from app.schemas.coach import CoachCashflowRequest, CoachPurchaseRequest
from app.services.finance import coach
from app.services.finance import grounded_chat
from app.services.categorization.rules import match_rules
from app.services.ai import provider

TODAY = date(2026, 10, 25)
client = TestClient(app)


@pytest.fixture
def data(monkeypatch):
    import app.api.coach as api
    monkeypatch.setattr(coach, "today_dhaka", lambda: TODAY)
    monkeypatch.setattr(grounded_chat, "today_dhaka", lambda: TODAY)
    monkeypatch.setattr(api, "today_dhaka", lambda: TODAY)
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)
    db = SessionLocal()
    people = []
    try:
        for _ in range(2):
            person = User(email=f"coach-{uuid4().hex}@example.com", hashed_password="test")
            db.add(person)
            db.commit()
            db.refresh(person)
            people.append(person)
        headers = [{"Authorization": "Bearer " + create_access_token({"sub": u.email, "user_id": u.id})} for u in people]
        yield db, people, headers
    finally:
        db.rollback()
        for user in people:
            db.query(SavingsGoal).filter_by(user_id=user.id).delete()
            db.query(ScheduledCashflowItem).filter_by(user_id=user.id).delete()
            db.delete(user)
        db.commit()
        db.close()


def seed(db, user):
    for month in (7, 8, 9):
        for amount, category in [(10000, "Salary"), (-2000 if month == 9 else -1000, "Food"), (-1000 if month == 9 else -500, "Shopping"), (-2000, "Bills")]:
            db.add(Transaction(user_id=user.id, date=date(2026, month, 5), amount=Decimal(amount), category=category, merchant=category + " merchant"))
    db.commit()


def plan(db, user, kind="expense", amount="3000", status="scheduled", due=None, title="Private bill"):
    item = ScheduledCashflowItem(user_id=user.id, title=title, kind=kind, amount=Decimal(amount), status=status, due_date=due or TODAY + timedelta(days=1))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def ask(headers, question, **kwargs):
    return client.post("/chat/ask", headers=headers, json={"question": question, **kwargs})


def goal(headers, **kwargs):
    response = client.post("/finance/goals", headers=headers, json={"name": "Emergency buffer", "target_amount": "12000", "target_date": "2026-12-25", **kwargs})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("method,path,payload", [
    ("get", "/finance/goals", None), ("post", "/finance/goals", {}),
    ("get", "/finance/goals/1", None), ("patch", "/finance/goals/1", {}),
    ("delete", "/finance/goals/1", None), ("get", "/finance/goals/1/plan", None),
    ("get", "/finance/savings/recommendations", None), ("get", "/insights/proactive", None),
    ("post", "/finance/coach/cashflow", {}), ("post", "/finance/coach/spending-decision", {}),
    ("post", "/transactions/categorize", {}), ("post", "/chat/ask", {"question": "spending"}),
])
def test_new_routes_require_auth(method, path, payload):
    assert client.request(method, path, json=payload).status_code == 401


def test_chat_exact_period_category_and_user_isolation(data):
    db, people, headers = data
    seed(db, people[0])
    db.add(Transaction(user_id=people[1].id, date=date(2026, 9, 5), amount=Decimal("-999999"), category="Food", merchant="SECRET OTHER USER"))
    db.commit()
    response = ask(headers[0], "How much did I spend last month?")
    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["calculation"]["expenses"]) == 5000
    assert body["date_range"] == {"start_date": "2026-09-01", "end_date": "2026-09-30"}
    assert body["coverage"]["transaction_count"] == 4
    assert "SECRET" not in response.text
    body = ask(headers[0], "How much did I spend on food last month?").json()
    assert Decimal(body["calculation"]["expenses"]) == 2000
    body = ask(headers[0], "Largest expense categories last month").json()
    assert len(body["calculation"]["items"]) == 3
    response = ask(headers[0], "Top merchants last month")
    assert response.status_code == 200
    assert "SECRET" not in response.text
    # Direct user identity fields are rejected by the request contract.
    assert ask(headers[0], "spending", user_id=people[1].id).status_code == 422


def test_chat_comparison_uses_matched_days(data):
    db, people, headers = data
    seed(db, people[0])
    db.add(Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-6000"), category="Food"))
    # Excluded from the matched prior period, despite lying in the prior month.
    db.add(Transaction(user_id=people[0].id, date=date(2026, 9, 29), amount=Decimal("-8000"), category="Food"))
    db.commit()
    body = ask(headers[0], "Compare my spending this month with last month").json()
    assert body["calculation"]["operation"] == "comparison"
    assert Decimal(body["calculation"]["expense_change"]) == 1000
    assert Decimal(body["calculation"]["expense_change_pct"]) == 20
    assert body["calculation"]["previous"]["coverage"]["end_date"] == "2026-09-25"


@pytest.mark.parametrize("question,fields", [
    ("spending last year", {}), ("spending 2024", {}), ("spending on Monday", {}),
    ("spending", {"start_date": "2026-09-01"}),
    ("spending", {"start_date": "2026-10-01", "end_date": "2026-09-01"}),
    ("spending", {"start_date": "2026-11-01", "end_date": "2026-11-02"}),
    ("spending from 2026-99-01 to 2026-10-01", {}),
    ("compare spending in July and August", {}),
    ("bills next week", {}), ("   ", {}),
])
def test_chat_rejects_ambiguous_or_invalid_periods(data, question, fields):
    _, _, headers = data
    assert ask(headers[0], question, **fields).status_code == 422


def test_chat_missing_data_not_zero_and_balance_not_inferred(data):
    _, _, headers = data
    body = ask(headers[0], "How much did I spend last month?").json()
    assert body["status"] == "insufficient_data"
    assert body["calculation"]["expenses"] is None
    for question in ("What is my balance?", "Can I afford a purchase?", "What drives my projected cashflow?"):
        assert ask(headers[0], question).json()["status"] == "insufficient_data"
    assert ask(headers[0], "Tell me a joke").json()["status"] == "unsupported"


def test_chat_upcoming_records_are_plans_and_private(data):
    db, people, headers = data
    item = plan(db, people[0])
    plan(db, people[0], status="paid", title="Already paid")
    plan(db, people[1], title="SECRET OTHER USER")
    response = ask(headers[0], "What bills are coming up?")
    body = response.json()
    assert body["calculation"]["total_items"] == 1
    assert body["calculation"]["items"][0]["record_type"] == "plan"
    assert "SECRET" not in response.text
    assert "Already paid" not in response.text
    assert db.query(Transaction).filter_by(user_id=people[0].id).count() == 0


def test_recommendation_ranking_arithmetic_stability_and_isolation(data):
    db, people, headers = data
    seed(db, people[0])
    first = client.get("/finance/savings/recommendations", headers=headers[0]).json()
    again = client.get("/finance/savings/recommendations", headers=headers[0]).json()
    assert first == again
    rows = first["recommendations"]
    assert [r["category"] for r in rows] == ["Food", "Shopping"]
    assert Decimal(rows[0]["estimated_monthly_saving"]) == 200
    assert Decimal(rows[0]["estimated_annual_saving"]) == 2400
    assert len({r["id"] for r in rows}) == len(rows)
    assert client.get("/finance/savings/recommendations", headers=headers[1]).json()["recommendations"] == []


def test_goals_crud_null_savings_lifecycle_and_isolation(data):
    _, _, headers = data
    item = goal(headers[0])
    url = f"/finance/goals/{item['id']}"
    assert item["current_saved"] is None
    assert client.get(url + "/plan", headers=headers[0]).json()["required_monthly"] is None
    assert client.get("/finance/goals", headers=headers[1]).json()["total"] == 0
    for method, path, payload in [("get", url, None), ("get", url + "/plan", None), ("patch", url, {"current_saved": "12000"}), ("delete", url, None)]:
        assert client.request(method, path, headers=headers[1], json=payload).status_code == 404
    assert client.patch(url, headers=headers[0], json={"status": "completed"}).status_code == 409
    response = client.patch(url, headers=headers[0], json={"status": "completed", "current_saved": "12000"})
    assert response.status_code == 200
    assert client.patch(url, headers=headers[0], json={"status": "active"}).status_code == 409
    assert client.patch(url, headers=headers[0], json={"current_saved": None}).status_code == 409
    assert client.patch(url, headers=headers[0], json={"description": "Corrected"}).status_code == 200
    assert client.get(url + "/plan", headers=headers[0]).json()["affordability"] == "completed"
    assert client.delete(url, headers=headers[0]).status_code == 204
    assert client.get(url, headers=headers[0]).status_code == 404


@pytest.mark.parametrize("changes", [
    {"name": " "}, {"target_amount": "0"}, {"target_amount": "1.001"},
    {"current_saved": "-1"}, {"target_date": "2026-10-24"}, {"target_date": "bad"},
    {"user_id": 1}, {"status": "completed"}, {"current_saved": "NaN"},
])
def test_goal_create_validation(data, changes):
    _, _, headers = data
    response = client.post("/finance/goals", headers=headers[0], json={"name": "Goal", "target_amount": "1000", "target_date": "2026-12-25", **changes})
    assert response.status_code == 422


def test_goal_plan_arithmetic_affordability_and_shared_commitments(data):
    db, people, headers = data
    seed(db, people[0])
    item = goal(headers[0], current_saved="0")
    url = f"/finance/goals/{item['id']}"
    body = client.get(url + "/plan", headers=headers[0]).json()
    assert Decimal(body["required_monthly"]) == 4000
    assert Decimal(body["required_weekly"]) == Decimal("1333.34")
    assert Decimal(body["estimated_monthly_capacity"]) == 6000
    assert body["affordability"] == "appears_feasible"
    other = goal(headers[0])
    assert client.get(url + "/plan", headers=headers[0]).json()["affordability"] == "unknown"
    client.patch(f"/finance/goals/{other['id']}", headers=headers[0], json={"current_saved": "0"})
    assert client.get(url + "/plan", headers=headers[0]).json()["affordability"] == "at_risk"
    for changes in ({"name": None}, {"target_amount": None}, {"status": "invalid"}, {"target_date": None}, {"user_id": people[1].id}):
        assert client.patch(url, headers=headers[0], json=changes).status_code == 422
    client.patch(url, headers=headers[0], json={"status": "cancelled"})
    assert client.get(url + "/plan", headers=headers[0]).json()["affordability"] == "cancelled"


def test_goal_sparse_and_overdue_states(data):
    db, people, headers = data
    item = goal(headers[0], current_saved="0")
    url = f"/finance/goals/{item['id']}/plan"
    assert client.get(url, headers=headers[0]).json()["affordability"] == "unknown"
    row = db.get(SavingsGoal, item["id"])
    row.target_date = TODAY - timedelta(days=1)
    db.commit()
    assert client.get(url, headers=headers[0]).json()["affordability"] == "overdue"


def test_obligation_scenarios_ignore_uncertain_income_and_paid_records(data):
    db, people, headers = data
    seed(db, people[0])
    plan(db, people[0])
    plan(db, people[0], kind="income", amount="500000")
    plan(db, people[0], amount="999999", status="paid")
    plan(db, people[0], amount="999999", status="cancelled")
    plan(db, people[1], amount="999999")
    before = db.query(Transaction).filter_by(user_id=people[0].id).count()
    response = client.post("/finance/coach/cashflow", headers=headers[0], json={"starting_balance": "5000", "months_ahead": 2})
    assert response.status_code == 200, response.text
    first = response.json()["months"][0]
    assert Decimal(first["scheduled_expenses"]) == 3000
    assert Decimal(first["uncertain_scheduled_income"]) == 500000
    assert Decimal(first["balance_without_future_income"]) == 2000
    assert Decimal(first["projected_balance"]) == Decimal("4258.06")
    response = client.post("/finance/coach/spending-decision", headers=headers[0], json={"purchase_amount": "2500", "starting_balance": "5000", "safety_buffer": "500"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "not_recommended"
    assert Decimal(response.json()["remaining_after_purchase_and_reserve"]) == -500
    chat = ask(headers[0], "Can I afford a purchase?", purchase_amount="2500", starting_balance="5000", safety_buffer="500").json()
    assert chat["calculation"]["status"] == "not_recommended"
    assert ask(headers[0], "What assumptions drive projected cashflow?", starting_balance="5000").status_code == 200
    assert db.query(Transaction).filter_by(user_id=people[0].id).count() == before
    missing = client.post("/finance/coach/cashflow", headers=headers[1], json={"starting_balance": "5000"}).json()
    assert missing["months"][0]["projected_balance"] is None


def test_insights_dedup_expiry_sparse_history_and_user_isolation(data):
    db, people, headers = data
    item = plan(db, people[0])
    other = plan(db, people[1], title="SECRET OTHER USER")
    first = client.get("/insights/proactive", headers=headers[0])
    assert first.status_code == 200, first.text
    assert "SECRET" not in first.text
    rows = first.json()["insights"]
    assert len(rows) == 1 and rows[0]["type"] == "upcoming_expense"
    assert rows[0]["evidence"]["record_type"] == "plan"
    assert first.json() == client.get("/insights/proactive", headers=headers[0]).json()
    item.status = "paid"
    db.commit()
    assert client.get("/insights/proactive", headers=headers[0]).json()["insights"] == []
    item.status = "scheduled"
    db.commit()
    future = coach.nudges(db, people[0].id, TODAY + timedelta(days=2))
    assert not any(n["type"] == "upcoming_expense" for n in future["insights"])
    seed(db, people[0])
    db.add(Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-10000"), category="Shopping"))
    db.commit()
    rows = client.get("/insights/proactive", headers=headers[0]).json()["insights"]
    assert any(row["type"] == "unusual_spending" for row in rows)
    assert len({row["key"] for row in rows}) == len(rows)


def test_batch_preserves_manual_categories_and_checks_all_ids_first(data):
    db, people, headers = data
    rows = [Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-100"), merchant="Chaldal"),
            Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-100"), merchant="Uber", category="Education", category_method="user"),
            Transaction(user_id=people[1].id, date=TODAY, amount=Decimal("-100"), merchant="SECRET")]
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    assert client.post("/transactions/categorize", headers=headers[0], json={"transaction_ids": ids}).status_code == 404
    db.expire_all()
    assert rows[0].category is None
    response = client.post("/transactions/categorize", headers=headers[0], json={"transaction_ids": ids[:2]})
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["category"] == "Groceries"
    assert response.json()["items"][1]["category"] == "Education"
    assert response.json()["items"][1]["preserved"] is True
    assert client.post("/transactions/categorize", headers=headers[0], json={"transaction_ids": ids[:2]}).json()["items"][0]["preserved"] is True
    for payload in ({"transaction_ids": []}, {"transaction_ids": [1] * 101}, {"transaction_ids": [1, 1]}, {"transaction_ids": [1], "user_id": people[1].id}):
        assert client.post("/transactions/categorize", headers=headers[0], json=payload).status_code == 422


@pytest.mark.parametrize("text,category", [("\u099a\u09be\u09b2\u09a1\u09be\u09b2 \u09ac\u09be\u099c\u09be\u09b0", "Groceries"), ("\u09ac\u09bf\u09a6\u09cd\u09af\u09c1\u09ce \u09ac\u09bf\u09b2", "Bills"), ("\u09ac\u09c7\u09a4\u09a8", "Salary"), ("\u09b8\u09cd\u0995\u09c1\u09b2 \u09ab\u09bf", "Education"), ("Uber ride", "Transport"), ("\u09ab\u09c1\u09a1\u09aa\u09be\u09a8\u09cd\u09a1\u09be \u0996\u09be\u09ac\u09be\u09b0", "Food")])
def test_bangla_and_mixed_rules(text, category):
    assert match_rules(description=text)["category"] == category


def test_optional_provider_failure_malformed_and_disabled(monkeypatch):
    from app.schemas.categorization import LLMCategorization
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_KEY", "fake-key")
    model = Mock()
    monkeypatch.setattr(provider, "build_chat_model", lambda: model)
    model.with_structured_output.return_value.invoke.side_effect = TimeoutError("SECRET PROMPT")
    assert provider.structured_optional(LLMCategorization, "system", "payload") is None
    model.with_structured_output.return_value.invoke.side_effect = None
    model.with_structured_output.return_value.invoke.return_value = {"category": "invented", "confidence": 2}
    assert provider.structured_optional(LLMCategorization, "system", "payload") is None
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", False)
    model.reset_mock()
    assert provider.structured_optional(LLMCategorization, "system", "payload") is None
    model.assert_not_called()


def test_transaction_creation_checks_account_ownership_and_offline_classification(data):
    db, people, headers = data
    account = Account(user_id=people[1].id, name="Private")
    db.add(account)
    db.commit()
    response = client.post("/transactions", headers=headers[0], json={"date": str(TODAY), "amount": "-100", "account_id": account.id, "merchant": "Chaldal"})
    assert response.status_code == 404
    response = client.post("/transactions", headers=headers[0], json={"date": str(TODAY), "amount": "-100", "merchant": "Chaldal"})
    assert response.status_code == 201
    assert response.json()["category"] == "Groceries"


def test_retrieval_defensively_filters_foreign_metadata(monkeypatch):
    from app.services.rag import retrieval
    docs = [SimpleNamespace(page_content="mine", metadata={"user_id": 7}),
            SimpleNamespace(page_content="SECRET", metadata={"user_id": 8}),
            SimpleNamespace(page_content="unscoped", metadata={})]
    monkeypatch.setattr(retrieval, "search_transactions", lambda **kwargs: docs)
    assert [r.content for r in retrieval.retrieve_transactions("query", 7)] == ["mine"]


def test_legacy_ai_routes_work_without_key(data, monkeypatch):
    db, people, headers = data
    seed(db, people[0])
    monkeypatch.setattr(settings, "OPENAI_KEY", None)
    assert client.get("/insights/ai", headers=headers[0]).status_code == 200
    response = client.post("/planner/savings/coach", headers=headers[0], json={"goal_amount": "1000", "current_saved": "0", "target_date": "2099-12-31"})
    assert response.status_code == 200, response.text
    assert response.json()["actions"]


def test_batch_provider_budget_and_safe_failure_reasons(data, monkeypatch, caplog):
    from app.services.categorization import service
    db, people, headers = data
    rows = [Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-1"), description=f"Ambiguous code {i}") for i in range(8)]
    db.add_all(rows)
    db.commit()
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise service.CategorizationLLMError("SECRET TOKEN AND PROMPT")
    monkeypatch.setattr(service, "categorize_with_llm", fail)
    response = client.post("/transactions/categorize", headers=headers[0], json={"transaction_ids": [r.id for r in rows]})
    assert response.status_code == 200
    assert len(calls) == 5
    assert "SECRET" not in response.text
    assert "SECRET" not in caplog.text
    assert all(row["category"] == "Uncategorized" for row in response.json()["items"])


@pytest.mark.parametrize("path,payload", [
    ("/finance/coach/cashflow", {"starting_balance": "-1"}),
    ("/finance/coach/cashflow", {"starting_balance": "1.001"}),
    ("/finance/coach/cashflow", {"starting_balance": "100", "months_ahead": 13}),
    ("/finance/coach/cashflow", {"starting_balance": "100", "user_id": 1}),
    ("/finance/coach/spending-decision", {"starting_balance": "100", "purchase_amount": "0", "safety_buffer": "1"}),
    ("/finance/coach/spending-decision", {"starting_balance": "100", "purchase_amount": "10", "safety_buffer": "1", "horizon_days": 367}),
])
def test_coach_scenario_input_validation(data, path, payload):
    _, _, headers = data
    assert client.post(path, headers=headers[0], json=payload).status_code == 422


def test_provider_configuration_bounds_and_missing_key(monkeypatch):
    import langchain_openai
    monkeypatch.setattr(settings, "OPENAI_KEY", "fake-key")
    monkeypatch.setattr(settings, "AI_TIMEOUT_SECONDS", 1000)
    monkeypatch.setattr(settings, "AI_MAX_OUTPUT_TOKENS", 100000)
    factory = Mock()
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", factory)
    provider.build_chat_model()
    assert factory.call_args.kwargs["timeout"] == 30
    assert factory.call_args.kwargs["max_tokens"] == 2000
    assert factory.call_args.kwargs["max_retries"] == 0
    monkeypatch.setattr(settings, "OPENAI_KEY", None)
    with pytest.raises(RuntimeError, match="not configured"):
        provider.build_chat_model()


def test_configured_category_keyword_respects_taxonomy(monkeypatch):
    monkeypatch.setattr(settings, "CATEGORY_KEYWORD_RULES", {"custom shop": "Shopping", "bad keyword": "invented"})
    assert match_rules(description="custom shop order")["category"] == "Shopping"
    assert match_rules(description="bad keyword") is None


def test_nudge_estimated_deficit_and_goal_progress(data):
    db, people, headers = data
    for month in (7, 8, 9):
        db.add(Transaction(user_id=people[0].id, date=date(2026, month, 1), amount=Decimal("-100")))
    db.commit()
    goal(headers[0], current_saved="0")
    response = client.get("/insights/proactive", headers=headers[0])
    assert response.status_code == 200
    rows = response.json()["insights"]
    deficit = next(row for row in rows if row["type"] == "projected_shortfall")
    assert deficit["evidence"]["is_estimate"] is True
    assert any(row["type"] == "goal_progress" for row in rows)


def test_goal_same_day_rounding_and_known_zero_savings(data):
    _, _, headers = data
    item = goal(headers[0], target_amount="0.01", current_saved="0", target_date=str(TODAY))
    body = client.get(f"/finance/goals/{item['id']}/plan", headers=headers[0]).json()
    assert Decimal(body["required_weekly"]) == Decimal("0.01")
    assert Decimal(body["required_monthly"]) == Decimal("0.01")
    assert body["affordability"] == "unknown"


def test_non_bdt_and_foreign_account_records_are_excluded(data):
    db, people, headers = data
    accounts = [Account(user_id=people[0].id, name="USD", currency="USD"), Account(user_id=people[1].id, name="BDT", currency="BDT")]
    db.add_all(accounts)
    db.commit()
    for account in accounts:
        db.add(Transaction(user_id=people[0].id, account_id=account.id, date=date(2026, 9, 5), amount=Decimal("-9999")))
    db.add(Transaction(user_id=people[0].id, date=date(2026, 9, 5), amount=Decimal("-100")))
    db.commit()
    response = ask(headers[0], "spending last month")
    assert response.status_code == 200
    assert Decimal(response.json()["calculation"]["expenses"]) == 100


def test_app_imports_without_optional_ai_or_vector_packages():
    import subprocess
    import sys
    from pathlib import Path
    script = """
import sys
import importlib.abc
class NoOptionalAI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('langchain', 'chromadb', 'openai')):
            raise ImportError('Optional AI package intentionally unavailable')
sys.meta_path.insert(0, NoOptionalAI())
from app.main import app
assert '/chat/ask' in app.openapi()['paths']
assert '/finance/goals' in app.openapi()['paths']
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30, cwd=Path(__file__).resolve().parent)
    assert result.returncode == 0, result.stderr


def test_insight_provider_cannot_author_financial_claims(monkeypatch):
    from app.services.ai import financial_insights
    monkeypatch.setattr(provider, "structured_optional", lambda *args: SimpleNamespace(indices=[0, 0, 5]))
    result = financial_insights.generate_financial_insights({"monthly": [{"net": "-100"}]})
    assert len(result.insights) == 1
    assert result.insights[0].type == "cashflow_risk"
    assert result.insights[0].metric is None


def test_savings_wording_failure_uses_grounded_fallback(monkeypatch):
    from app.services.ai import savings_coach
    from backend.test_savings_coach import sample_plan
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_KEY", "fake-key")
    def failed(*args, **kwargs):
        raise TimeoutError("SECRET PROVIDER PAYLOAD")
    monkeypatch.setattr(provider, "build_chat_model", failed)
    actions = savings_coach.generate_savings_actions(sample_plan())
    assert actions and "SECRET" not in actions[0].reason


def test_legacy_savings_missing_history_is_explicit(data):
    _, _, headers = data
    response = client.post("/planner/savings", headers=headers[0], json={"goal_amount": "1000", "current_saved": "0", "target_date": "2099-12-31"})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
    assert response.json()["estimated_monthly_income"] is None
    assert response.json()["estimated_monthly_spending"] is None
    assert response.json()["historical_transaction_count"] == 0


@pytest.mark.parametrize("metric,change_key,expected_change,expected_pct", [
    ("expenses", "expense_change", "1000.00", "20.00"),
    ("income", "income_change", "5000.00", "50.00"),
])
def test_chat_comparison_metric_regression(data, metric, change_key, expected_change, expected_pct):
    db, people, headers = data
    seed(db, people[0])
    db.add_all([
        Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("15000"), category="Salary"),
        Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-6000"), category="Food"),
        Transaction(user_id=people[1].id, date=TODAY, amount=Decimal("999999"), category="Salary"),
    ])
    db.commit()
    response = ask(headers[0], f"Compare my {metric} this month with last month")
    assert response.status_code == 200, response.text
    body = response.json()
    result = body["calculation"]
    assert result["metric"] == metric
    assert Decimal(result["change"]) == Decimal(expected_change)
    assert Decimal(result["change_pct"]) == Decimal(expected_pct)
    assert Decimal(result[change_key]) == Decimal(expected_change)
    assert Decimal(result[change_key + "_pct"]) == Decimal(expected_pct)
    assert f"Recorded {metric} changed by BDT {expected_change}" in body["answer"]
    other_key = "expense_change" if metric == "income" else "income_change"
    assert other_key not in result


@pytest.mark.parametrize("phrase", [
    "from 2026-09-01 to 2026-09-30",
    "between 2026-09-01 and 2026-09-30",
])
def test_chat_explicit_date_phrase_regression(data, phrase):
    db, people, headers = data
    seed(db, people[0])
    db.add_all([
        Transaction(user_id=people[0].id, date=date(2026, 9, 1), amount=Decimal("-25")),
        Transaction(user_id=people[0].id, date=date(2026, 9, 30), amount=Decimal("-75")),
        Transaction(user_id=people[0].id, date=date(2026, 10, 1), amount=Decimal("-999")),
    ])
    db.commit()
    response = ask(headers[0], f"How much did I spend {phrase}?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "answered"
    assert body["date_range"] == {"start_date": "2026-09-01", "end_date": "2026-09-30"}
    assert Decimal(body["calculation"]["expenses"]) == Decimal("5100.00")
    assert body["coverage"]["transaction_count"] == 6


@pytest.mark.parametrize("question", [
    "How much did I spend from Foodpanda from 2026-09-01 to 2026-09-30?",
    "How much did I spend at Foodpanda between 2026-09-01 and 2026-09-30?",
])
def test_date_phrase_does_not_bypass_unsupported_merchant_filter(data, question):
    _, _, headers = data
    assert ask(headers[0], question).status_code == 422


def test_custom_category_correction_survives_preference_reuse(data):
    from app.models.merchant_preference import MerchantCategoryPreference
    from app.services.categorization.categories import ALLOWED_CATEGORIES
    db, people, headers = data
    payload = {"date": str(TODAY), "amount": "-100", "merchant": "Foodpanda", "description": "Dinner"}
    original = client.post("/transactions", headers=headers[0], json=payload)
    assert original.status_code == 201, original.text
    correction = client.patch(f"/transactions/{original.json()['id']}/category", headers=headers[0], json={"category": "Family support"})
    assert correction.status_code == 200, correction.text
    preference = db.query(MerchantCategoryPreference).filter_by(user_id=people[0].id, normalized_merchant="foodpanda").one()
    assert preference.category == "Family support"
    repeated = client.post("/transactions", headers=headers[0], json=payload)
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["category"] == "Family support"
    assert repeated.json()["category_method"] == "user_preference"
    assert Decimal(repeated.json()["category_confidence"]) == 1
    assert "Family support" not in ALLOWED_CATEGORIES
    # Another user's rules and preferences remain independent.
    foreign = client.post("/transactions", headers=headers[1], json=payload)
    assert foreign.status_code == 201
    assert foreign.json()["category"] == "Food"
    ambiguous = Transaction(user_id=people[0].id, date=TODAY, amount=Decimal("-100"), merchant="Foodpanda")
    db.add(ambiguous)
    db.commit()
    batch = client.post("/transactions/categorize", headers=headers[0], json={"transaction_ids": [ambiguous.id]})
    assert batch.status_code == 200, batch.text
    assert batch.json()["items"][0]["category"] == "Family support"
