"""Exercise merchant learning through the correction handler and real storage."""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.transactions import update_transaction_category
from app.core.database import Base
from app.models import MerchantCategoryPreference, Transaction, User
from app.schemas.categorization import LLMCategorization
from app.schemas.transactions import TransactionCategoryUpdate
from app.services.categorization import service


@pytest.fixture
def sessions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def users(sessions):
    with sessions() as db:
        users = [
            User(email=f"merchant-{name}@porer-hishab.local", hashed_password="test-password")
            for name in ("a", "b")
        ]
        db.add_all(users)
        db.commit()
        return tuple(user.id for user in users)


def correct_foodpanda(sessions, user_id):
    """Correct a distinct transaction, then close the request's DB session.

    Do not commit on behalf of the handler: learning must survive the same
    session cleanup as a real request.
    """
    with sessions() as db:
        transaction = Transaction(
            user_id=user_id,
            date=date(2026, 10, 10),
            merchant="Foodpanda",
            description="Food delivery",
            amount=Decimal("-850.00"),
            category="Food",
            category_method="rule",
            category_confidence=Decimal("0.980"),
        )
        db.add(transaction)
        db.commit()
        updated = update_transaction_category(
            transaction_id=transaction.id,
            payload=TransactionCategoryUpdate(category="Business"),
            current=db.get(User, user_id),
            db=db,
        )
        assert updated.category == "Business"


def test_correction_creates_merchant_preference(sessions, users):
    correct_foodpanda(sessions, users[0])

    with sessions() as db:
        preference = db.scalars(select(MerchantCategoryPreference)).one()
        assert preference.user_id == users[0]
        assert preference.normalized_merchant == "foodpanda"
        assert preference.category == "Business"
        assert preference.correction_count == 1


def test_repeated_corrections_update_one_preference(sessions, users):
    correct_foodpanda(sessions, users[0])
    with sessions() as db:
        original_id = db.scalars(select(MerchantCategoryPreference)).one().id

    # Two separate Food transactions corrected to Business, across requests.
    correct_foodpanda(sessions, users[0])

    with sessions() as db:
        preference = db.scalars(select(MerchantCategoryPreference)).one()
        assert preference.id == original_id
        assert preference.normalized_merchant == "foodpanda"
        assert preference.category == "Business"
        assert preference.correction_count == 2


def test_learned_preference_overrides_rules_without_calling_them(
    sessions, users, monkeypatch
):
    baseline = service.categorize_transaction({"merchant": "Foodpanda"})
    assert (baseline.category, baseline.method) == ("Food", "rule")
    correct_foodpanda(sessions, users[0])
    rules = Mock(side_effect=AssertionError("Preference must bypass rules"))
    llm = Mock(side_effect=AssertionError("Preference must bypass LLM"))
    monkeypatch.setattr(service, "match_rules", rules)
    monkeypatch.setattr(service, "categorize_with_llm", llm)

    with sessions() as db:
        result = service.categorize_transaction(
            {"merchant": "Foodpanda"}, db=db, user_id=users[0]
        )

    assert result.category == "Business"
    assert result.method == "user_preference"
    assert Decimal(str(result.confidence)) == Decimal("1.000")
    rules.assert_not_called()
    llm.assert_not_called()


def test_preferences_are_user_scoped(sessions, users):
    correct_foodpanda(sessions, users[0])

    with sessions() as db:
        personalized = service.categorize_transaction(
            {"merchant": "Foodpanda"}, db=db, user_id=users[0]
        )
        other_user = service.categorize_transaction(
            {"merchant": "Foodpanda"}, db=db, user_id=users[1]
        )
        assert (personalized.category, personalized.method) == (
            "Business", "user_preference"
        )
        assert (other_user.category, other_user.method) == ("Food", "rule")
        assert db.scalars(
            select(MerchantCategoryPreference).where(
                MerchantCategoryPreference.user_id == users[1]
            )
        ).all() == []


@pytest.mark.parametrize(
    ("merchant", "category", "method"),
    [("Netflix", "Subscription", "rule"), ("Zorblax", "Shopping", "llm")],
)
def test_merchant_without_preference_uses_existing_pipeline(
    sessions, users, monkeypatch, merchant, category, method
):
    correct_foodpanda(sessions, users[0])
    rules = Mock(wraps=service.match_rules)
    llm = Mock(return_value=LLMCategorization(
        category="Shopping", confidence=0.87, reason="Retail purchase"
    ))
    monkeypatch.setattr(service, "match_rules", rules)
    monkeypatch.setattr(service, "categorize_with_llm", llm)

    with sessions() as db:
        result = service.categorize_transaction(
            {"merchant": merchant}, db=db, user_id=users[0]
        )
        preferences = db.scalars(select(MerchantCategoryPreference)).all()
        assert len(preferences) == 1
        assert preferences[0].normalized_merchant == "foodpanda"

    assert (result.category, result.method) == (category, method)
    rules.assert_called_once_with(
        merchant=merchant, normalized_merchant=None, description=None
    )
    if method == "llm":
        llm.assert_called_once_with(
            merchant=merchant, normalized_merchant=None, description=None, amount=None
        )
        assert result.confidence == 0.87
    else:
        llm.assert_not_called()
