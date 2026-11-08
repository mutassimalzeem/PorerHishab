"""Hermetic test bootstrap: disposable data, synthetic credentials and no dotenv reads."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent

for path in (str(BACKEND_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import os
import tempfile
os.chdir(REPO_ROOT)
import pytest

# Explicit dedicated PostgreSQL URLs are opt-in; otherwise use a disposable SQLite file.
_TEST_DIR = tempfile.TemporaryDirectory(prefix="porerhishab-tests-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "PORERHISHAB_TEST_DATABASE_URL", "sqlite:///" + str(Path(_TEST_DIR.name) / "tests.sqlite")
)
os.environ["SECRET_KEY"] = "test-access-key-never-for-deployment"
os.environ["REFRESH_SECRET_KEY"] = "test-refresh-key-never-for-deployment"
os.environ["PEPPER"] = "test-password-pepper-never-for-deployment"
os.environ["AI_EXTERNAL_ENABLED"] = "false"
os.environ["EMAIL_BACKEND"] = "test"
os.environ["NOTIFICATION_DELIVERY_ENABLED"] = "true"
for _name in ("OPENAI_KEY", "OPENAI_API_KEY", "SMTP_USERNAME", "SMTP_PASSWORD", "RUN_LIVE_AI_TESTS"):
    os.environ.pop(_name, None)


@pytest.fixture(scope="session", autouse=True)
def disposable_schema():
    from app.core.database import Base, engine
    import app.models
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    yield
    engine.dispose()
    _TEST_DIR.cleanup()

@pytest.fixture(autouse=True)
def clean_sqlite_database(disposable_schema):
    from app.core.database import Base, engine
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    yield
