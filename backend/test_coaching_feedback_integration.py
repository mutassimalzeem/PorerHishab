"""Real PostgreSQL concurrent upsert and Alembic roundtrip."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from app.models import User, Account, ScheduledCashflowItem
from app.models.coaching_feedback import CoachingFeedback
from app.schemas.coaching import CoachingFeedbackInput
from app.services.finance.coaching import financial_coaching
from app.services.finance.coaching_feedback import submit
from app.services.intelligence.periods import today_dhaka
from backend.test_obligation_reconciliation import store  # noqa: F401


def test_feedback_migration_and_concurrent_upsert(store):
    factory, engine = store
    with factory() as db:
        user = User(email="feedback-concurrent@example.test", hashed_password="x")
        db.add(user); db.flush()
        user_id = user.id
        db.add(Account(user_id=user_id, name="Cash", currency="BDT", opening_balance=1000, opening_balance_date=today_dhaka()))
        db.add(ScheduledCashflowItem(user_id=user_id, title="Rent", kind="expense", amount=2000, due_date=today_dhaka(), status="scheduled"))
        db.commit()
        key = financial_coaching(db, user_id).recommendations[0].id
    barrier = Barrier(2)
    def update(status):
        with factory() as db:
            barrier.wait(timeout=15)
            return submit(db, user_id, key, CoachingFeedbackInput(status=status)).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, status) for status in ("dismissed", "acted_on")]
        assert {future.result(timeout=30) for future in futures} <= {"dismissed", "acted_on"}
    with factory() as db:
        assert db.query(CoachingFeedback).filter_by(user_id=user_id, recommendation_id=key).count() == 1
    schema = inspect(engine)
    assert {tuple(c["column_names"]) for c in schema.get_unique_constraints("coaching_feedback")} == {("user_id", "recommendation_id")}
    assert schema.get_foreign_keys("coaching_feedback")[0]["options"]["ondelete"] == "CASCADE"
    assert {tuple(i["column_names"]) for i in schema.get_indexes("coaching_feedback")} >= {("user_id",), ("user_id", "status")}
    config = Config("alembic.ini")
    command.downgrade(config, "f15b00000001")
    assert "coaching_feedback" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users WHERE id=:id"), {"id":user_id}).scalar_one() == 1
    command.upgrade(config, "head")
    assert "coaching_feedback" in inspect(engine).get_table_names()
    with factory() as db:
        submit(db, user_id, key, CoachingFeedbackInput(status="not_relevant"))
        db.execute(text("DELETE FROM scheduled_cashflow_items WHERE user_id=:id"), {"id":user_id})
        db.execute(text("DELETE FROM accounts WHERE user_id=:id"), {"id":user_id})
        db.execute(text("DELETE FROM users WHERE id=:id"), {"id":user_id})
        db.commit()
        assert db.query(CoachingFeedback).filter_by(user_id=user_id).count() == 0
