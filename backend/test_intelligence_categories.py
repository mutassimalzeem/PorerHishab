"""AI-13 tests: category facts, comparisons and coach-behaviour regressions.

The coach is now a thin presentation layer over the engine, so these tests
lock the migrated calculations to their pre-refactor values.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (register ORM models)
from app.core.database import Base
from app.models.transactions import Transaction
from app.models.user import User
from app.services.finance.coach import (
    history,
    nudges,
    recommendations,
)
from app.services.intelligence.categories import (
    category_spending_facts,
    percentage_change,
)
from app.services.intelligence.periods import (
    latest_complete_month_period,
    previous_complete_month_period,
)

AS_OF = date(2026, 10, 25)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _new_user(db, key):
    user = User(email=f"{key}@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    return user


def _seed_month(db, user, month, rows):
    entries = []
    for day, amount, category in rows:
        entries.append((date(2026, month, day), amount, category))
    for day, amount, category in entries:
        db.add(Transaction(user_id=user.id, date=day, amount=Decimal(amount),
                           category=category))
    db.commit()
    return entries


def test_percentage_change_rules_out_fabricated_baselines():
    assert percentage_change(Decimal("9000"), Decimal("5000")) == Decimal("80.00")
    assert percentage_change(Decimal("4000"), Decimal("5000")) == Decimal("-20.00")
    assert percentage_change(Decimal("3000"), None) is None
    assert percentage_change(Decimal("3000"), Decimal("0")) is None


def test_category_facts_are_observed_with_optional_comparison(db):
    user = _new_user(db, "categories")
    # August is the comparison month; September is the observed month.
    _seed_month(db, user, 8, ((10, "-4000", "Food"), (12, "-3000", "Transport")))
    _seed_month(db, user, 9, ((10, "-5500", "Food"), (12, "-3000", "Transport")))

    facts = category_spending_facts(
        db, user.id,
        observed_period=latest_complete_month_period(AS_OF),
        comparison_period=previous_complete_month_period(AS_OF, back=2),
    )
    by_category = {fact.category: fact for fact in facts}
    assert set(by_category) == {"Food", "Transport"}

    food = by_category["Food"]
    assert food.observed_expenses == Decimal("5500.00")
    assert food.observed_transactions == 1
    assert food.comparison_expenses == Decimal("4000.00")
    assert food.delta == Decimal("1500.00")
    assert food.percentage_change == Decimal("37.50")

    transport = by_category["Transport"]
    assert transport.comparison_expenses == Decimal("3000.00")
    assert transport.delta == Decimal("0.00")
    assert transport.observed_period.start == date(2026, 9, 1)
    assert transport.observed_period.end == date(2026, 9, 30)


def test_categories_missing_from_the_comparison_month_stay_unknown(db):
    user = _new_user(db, "new_category")
    _seed_month(db, user, 8, ((10, "-4000", "Food"),))
    _seed_month(db, user, 9, ((10, "-4000", "Food"), (12, "-1500", "Transport")))

    facts = category_spending_facts(
        db, user.id,
        observed_period=latest_complete_month_period(AS_OF),
        comparison_period=previous_complete_month_period(AS_OF, back=2),
    )
    by_category = {fact.category: fact for fact in facts}
    assert set(by_category) == {"Food", "Transport"}
    # No zero is fabricated for an August baseline that never existed.
    transport = by_category["Transport"]
    assert transport.comparison_expenses is None
    assert transport.delta is None
    assert transport.percentage_change is None


def test_uncategorized_transactions_keep_their_own_label(db):
    user = _new_user(db, "uncat")
    db.add(Transaction(user_id=user.id, date=date(2026, 9, 10),
                       amount=Decimal("-700"), category=None))
    db.commit()
    facts = category_spending_facts(
        db, user.id,
        observed_period=latest_complete_month_period(AS_OF))
    assert [fact.category for fact in facts] == ["Uncategorized"]
    assert facts[0].observed_expenses == Decimal("700.00")


# -- coach migration regressions ------------------------------------------------


def _migration_world(db):
    user = _new_user(db, "migration")
    for month, food in ((7, "4000"), (8, "5000"), (9, "9000")):
        db.add(Transaction(user_id=user.id, date=date(2026, month, 5),
                           amount=Decimal("30000"), category="Salary"))
        db.add(Transaction(user_id=user.id, date=date(2026, month, 10),
                           amount=Decimal(f"-{food}"), category="Food"))
    db.commit()
    return user


def test_coach_history_matches_pre_refactor_shape_and_values(db):
    user = _migration_world(db)
    h = history(db, user.id, AS_OF)
    assert h["adequate"] is True
    assert [row["expenses"] for row in h["monthly"]] == [
        Decimal("4000.00"), Decimal("5000.00"), Decimal("9000.00")]
    assert h["coverage"]["transaction_count"] == 6
    assert h["baseline"]["average_monthly_income"] == Decimal("30000.00")
    assert h["baseline"]["average_monthly_expenses"] == Decimal("6000.00")


def test_coach_recommendations_values_are_unchanged(db):
    user = _migration_world(db)
    payload = recommendations(db, user.id, AS_OF)
    assert len(payload["recommendations"]) == 1
    recommendation = payload["recommendations"][0]
    assert recommendation["category"] == "Food"
    assert recommendation["evidence"]["latest_expenses"] == "9000.00"
    assert recommendation["evidence"]["previous_expenses"] == "5000.00"
    assert recommendation["evidence"]["period_start"] == "2026-09-01"
    assert recommendation["evidence"]["period_end"] == "2026-09-30"
    assert recommendation["estimated_monthly_saving"] == Decimal("900.00")
    assert recommendation["estimated_annual_saving"] == Decimal("10800.00")
    assert recommendation["id"].startswith("review-category:2026-09:")


def test_coach_nudges_values_and_keys_are_unchanged(db):
    user = _migration_world(db)
    payload = nudges(db, user.id, AS_OF)
    types = {item["type"] for item in payload["insights"]}
    assert "savings_opportunity" in types
    savings = [item for item in payload["insights"]
               if item["type"] == "savings_opportunity"][0]
    assert savings["evidence"]["estimated_monthly_saving"] == "900.00"
    assert savings["period_start"] == date(2026, 9, 1)
    assert savings["period_end"] == date(2026, 9, 30)
    assert savings["expires_on"] == date(2026, 11, 1)
    assert len({item["key"] for item in payload["insights"]}) == \
        len(payload["insights"])


def test_coach_nudges_stay_silent_with_sparse_history(db):
    user = _new_user(db, "sparse")
    for month, food in ((8, "4000"), (9, "9000")):
        db.add(Transaction(user_id=user.id, date=date(2026, month, 5),
                           amount=Decimal("30000"), category="Salary"))
        db.add(Transaction(user_id=user.id, date=date(2026, month, 10),
                           amount=Decimal(f"-{food}"), category="Food"))
    db.commit()
    payload = nudges(db, user.id, AS_OF)
    assert payload["insights"] == []
    # Recommendations likewise carry the insufficiency limitation verbatim.
    recs = recommendations(db, user.id, AS_OF)
    assert recs["recommendations"] == []
    assert any("Three complete calendar months" in line
               for line in recs["limitations"])
