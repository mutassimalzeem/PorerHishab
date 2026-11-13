"""Opt-in token row-lock tests; only a dedicated isolated ai18c2_tokens DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import User
from app.models.email_verification import EmailVerificationToken
from app.services.email_verification import create_verification_token, consume_verification_token

URL = os.environ.get("AI18C2_DISPOSABLE_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Dedicated isolated PostgreSQL fixture not supplied")


@pytest.fixture
def database():
    parsed = make_url(URL)
    assert parsed.host == "127.0.0.1" and parsed.database == "ai18c2_tokens" and parsed.username == "ai18c2"
    schema = "ai18c2_" + uuid4().hex
    control = create_engine(URL, connect_args={"connect_timeout": 2})
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={"connect_timeout": 2, "options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory() as db:
            user = User(email="postgres-synthetic@example.com", hashed_password="unused")
            db.add(user)
            db.commit()
            owner = user.id
        yield factory, owner
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def test_concurrent_requests_create_only_one_challenge(database):
    factory, owner = database
    barrier = Barrier(2, timeout=5)
    def attempt():
        with factory() as db:
            user = db.get(User, owner)
            barrier.wait()
            return create_verification_token(db, user, "verify_email")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(value is not None for value in results) == 1
    with factory() as db:
        assert db.query(EmailVerificationToken).count() == 1


@pytest.mark.parametrize("purpose", ["verify_email", "reset_password"])
def test_concurrent_consumers_claim_token_once(database, purpose):
    from app.api.auth import verify_password
    factory, owner = database
    with factory() as db:
        raw = create_verification_token(db, db.get(User, owner), purpose)
    barrier = Barrier(2, timeout=5)
    def attempt(index):
        with factory() as db:
            barrier.wait()
            return consume_verification_token(db, raw, purpose, "synthetic-password-" + str(index))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == [False, True]
    with factory() as db:
        user = db.get(User, owner)
        assert user.email_verified
        assert db.query(EmailVerificationToken).one().used_at is not None
        if purpose == "reset_password":
            assert user.token_version == 1
            assert sum(verify_password("synthetic-password-" + str(i), user.hashed_password) for i in range(2)) == 1
