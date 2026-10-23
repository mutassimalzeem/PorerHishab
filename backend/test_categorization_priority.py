"""Tests for the user-preference step of the categorization pipeline.

User preference must take priority over the rule engine: a merchant the
user previously corrected is categorized with ``method='user_preference'``
and full confidence, even when a rule would also match it.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import User
from app.models.merchant_preference import MerchantCategoryPreference
from app.services.categorization.service import (
    categorize_transaction,
    get_user_preference_result,
)


def _memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_user_preference_result_is_built_from_stored_preference():
    db = _memory_db()

    user = User(
        email="preference-priority@zyra.local",
        hashed_password="test-password",
        full_name="Preference Test User",
    )
    db.add(user)
    db.flush()

    db.add(
        MerchantCategoryPreference(
            user_id=user.id,
            normalized_merchant="foodpanda",
            category="Groceries",
        )
    )
    db.commit()

    result = get_user_preference_result(
        db,
        user_id=user.id,
        merchant="Foodpanda",
        normalized_merchant=None,
    )

    assert result is not None
    assert result.category == "Groceries"
    assert result.confidence == 1.0
    assert result.method == "user_preference"
    assert result.reason == "Matched your previous preference for 'foodpanda'."


def test_user_preference_result_is_none_without_preference_or_context():
    db = _memory_db()

    # No db / user_id given.
    assert get_user_preference_result(
        None, user_id=None, merchant="Foodpanda", normalized_merchant=None
    ) is None

    # No preference stored.
    assert get_user_preference_result(
        db, user_id=1, merchant="Foodpanda", normalized_merchant=None
    ) is None

    # No merchant text to look up.
    assert get_user_preference_result(
        db, user_id=1, merchant=None, normalized_merchant=None
    ) is None


def test_user_preference_beats_rules():
    """A rule also matches 'Foodpanda', but the user's preference wins."""
    db = _memory_db()

    user = User(
        email="preference-priority-rules@zyra.local",
        hashed_password="test-password",
        full_name="Preference Priority User",
    )
    db.add(user)
    db.flush()

    db.add(
        MerchantCategoryPreference(
            user_id=user.id,
            normalized_merchant="foodpanda",
            category="Groceries",
        )
    )
    db.commit()

    result = categorize_transaction(
        {
            "description": "Lunch",
            "merchant": "Foodpanda",
            "normalized_merchant": "foodpanda",
            "amount": "-850.00",
        },
        db=db,
        user_id=user.id,
    )

    assert result.category == "Groceries"
    assert result.method == "user_preference"
    assert result.confidence == 1.0


def test_categorize_without_db_still_uses_rules():
    """No preference context -> behaviour is unchanged (rules next)."""
    result = categorize_transaction(
        {
            "merchant": "Foodpanda",
            "normalized_merchant": "foodpanda",
            "description": "Lunch",
        }
    )

    assert result.category == "Food"
    assert result.method == "rule"
