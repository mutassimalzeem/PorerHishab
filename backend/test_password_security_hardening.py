import bcrypt
import pytest
from app.api import auth


@pytest.mark.parametrize("pepper", ["p" * 32, "p" * 64, "p" * 72, "à¦¨" * 40])
def test_full_password_depends_on_suffix(monkeypatch, pepper):
    monkeypatch.setattr(auth.settings, "PEPPER", pepper)
    password = "shared-prefix-" + "A" * 100
    hashed = auth.get_password_hash(password)
    assert auth.verify_password(password, hashed)
    assert not auth.verify_password("shared-prefix-" + "B" * 100, hashed)


@pytest.mark.parametrize("pepper", ["p" * 32, "p" * 64, "p" * 72])
def test_legacy_hash_requires_verified_recovery(monkeypatch, pepper):
    monkeypatch.setattr(auth.settings, "PEPPER", pepper)
    legacy = bcrypt.hashpw((pepper + "old-password").encode()[:72], bcrypt.gensalt()).decode()
    assert auth.verify_password_and_upgrade("old-password", legacy) == (False, False)
    assert not auth.verify_password("unrelated-password", legacy)


def test_limiter_reclaims_keys_and_preserves_bound(monkeypatch):
    auth._failed_attempts.clear()
    monkeypatch.setattr(auth, "MAX_RATE_LIMIT_KEYS", 3)
    for i in range(10):
        auth.rate_limit_guard(str(i))
        auth.record_failed_attempt(str(i))
    assert len(auth._failed_attempts) == 3
    monkeypatch.setattr(auth.time, "time", lambda: 10**12)
    auth.rate_limit_guard("9")
    assert auth._failed_attempts["9"] == []
    auth._failed_attempts.clear()

def test_limiter_is_bounded_under_concurrent_requests(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    auth._failed_attempts.clear()
    monkeypatch.setattr(auth, "MAX_RATE_LIMIT_KEYS", 10)
    def attempt(i):
        auth.rate_limit_guard(str(i))
        auth.record_failed_attempt(str(i))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(attempt, range(100)))
    assert len(auth._failed_attempts) <= 10
    auth._failed_attempts.clear()
