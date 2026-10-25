"""Exercise real Alembic upgrade/downgrade in an isolated PostgreSQL schema."""
from uuid import uuid4
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from app.core.config import settings
from app.core.database import engine


def test_savings_goal_migration_roundtrip_preserves_existing_rows(monkeypatch):
    schema = "coach_migration_" + uuid4().hex
    # The generated schema is the only object removed by this test.
    assert schema.isidentifier() and schema.startswith("coach_migration_")
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = engine.url.set(query={**engine.url.query, "options": f"-csearch_path={schema}"})
    isolated = create_engine(isolated_url)
    monkeypatch.setattr(settings, "DATABASE_URL", isolated_url.render_as_string(hide_password=False))
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "ec735533a563")
        with isolated.begin() as connection:
            connection.execute(text("INSERT INTO users (email, hashed_password, created_at, updated_at) VALUES ('migration@example.com', 'test', now(), now())"))
        command.upgrade(config, "head")
        assert "savings_goals" in inspect(isolated).get_table_names()
        with isolated.begin() as connection:
            user_id = connection.execute(text("SELECT id FROM users")).scalar_one()
            connection.execute(text("INSERT INTO savings_goals (user_id, name, target_amount, target_date, status, created_at, updated_at) VALUES (:user, 'Goal', 100, '2099-01-01', 'active', now(), now())"), {"user": user_id})
            connection.execute(text("DELETE FROM users WHERE id = :user"), {"user": user_id})
            assert connection.execute(text("SELECT count(*) FROM savings_goals")).scalar_one() == 0
            connection.execute(text("INSERT INTO users (email, hashed_password, created_at, updated_at) VALUES ('preserved@example.com', 'test', now(), now())"))
        command.downgrade(config, "ec735533a563")
        assert "savings_goals" not in inspect(isolated).get_table_names()
        with isolated.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM users WHERE email = 'preserved@example.com'")).scalar_one() == 1
        command.upgrade(config, "head")
        assert "savings_goals" in inspect(isolated).get_table_names()
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
