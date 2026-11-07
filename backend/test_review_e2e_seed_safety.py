"""The destructive-test boundary must fail closed before opening a connection."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "review_e2e_seed", Path(__file__).resolve().parents[1] / "scripts/seed_financial_review_e2e.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)

URL = "postgresql+psycopg2://review_e2e:password@127.0.0.1:55439/porerhishab_review_e2e"


@pytest.mark.parametrize("url", [
    URL.replace("127.0.0.1", "production.example.com"),
    URL.replace("porerhishab_review_e2e", "porerhishab"),
    URL.replace("review_e2e:password", "admin:password"),
    "sqlite:///:memory:",
])
def test_refuse_non_disposable_targets(monkeypatch, url):
    monkeypatch.setenv("REVIEW_E2E_DISPOSABLE", "1")
    with pytest.raises(ValueError, match="Refusing seed"):
        seed.validate_database(url)


def test_explicit_opt_in_required(monkeypatch):
    monkeypatch.delenv("REVIEW_E2E_DISPOSABLE", raising=False)
    with pytest.raises(ValueError, match="Refusing seed"):
        seed.validate_database(URL)
    monkeypatch.setenv("REVIEW_E2E_DISPOSABLE", "1")
    seed.validate_database(URL)
