import datetime, bcrypt, time, hashlib, hmac
import jwt
from jwt import InvalidTokenError
from datetime import timedelta
from typing import Optional
from fastapi import HTTPException
from app.core.config import settings
from collections import OrderedDict
from threading import Lock


SECRET_KEY = settings.SECRET_KEY
REFRESH_SECRET_KEY = settings.REFRESH_SECRET_KEY
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS


RATE_LIMIT_WINDOW_SECONDS = settings.RATE_LIMIT_WINDOW_SECONDS
RATE_LIMIT_MAX_ATTEMPTS = settings.RATE_LIMIT_MAX_ATTEMPTS
MAX_RATE_LIMIT_KEYS = 10_000

MAX_BCRYPT_LENGTH = 72  # bcrypt ignores beyond 72B


_failed_attempts: OrderedDict[str, list[float]] = OrderedDict()
_attempts_lock = Lock()


def _prune_old(attempts: list[float]) -> list[float]:
    cutoff = time.time() - RATE_LIMIT_WINDOW_SECONDS
    return [timestamp for timestamp in attempts if timestamp >= cutoff]


def _get_attempts(key: str) -> list[float]:
    attempts = _prune_old(_failed_attempts.get(key, []))

    if key in _failed_attempts:
        _failed_attempts.move_to_end(key)

    if not attempts:
        _failed_attempts.pop(key, None)

    return attempts


def _store_attempts(key: str, attempts: list[float]) -> None:
    _failed_attempts[key] = attempts
    _failed_attempts.move_to_end(key)

    while len(_failed_attempts) > MAX_RATE_LIMIT_KEYS:
        _failed_attempts.popitem(last=False)


def rate_limit_guard(key: str):
    with _attempts_lock:
        attempts = _get_attempts(key)

        if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Try again later.",
            )

        _store_attempts(key, attempts)


def record_failed_attempt(key: str):
    with _attempts_lock:
        attempts = _get_attempts(key)
        attempts.append(time.time())
        _store_attempts(key, attempts)


def _new_password_bytes(password: str) -> bytes:
    """Derive a fixed-length bcrypt input using HMAC-SHA256"""
    return hmac.new(
        settings.PEPPER.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256
    ).digest()

def get_password_hash(plain_password: str) -> str:
    password_bytes = _new_password_bytes(plain_password)

    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password_and_upgrade(plain_password: str, hashed_password: str) -> tuple[bool, bool]:
    """Only accept the full-password HMAC scheme.

    Lossy legacy bcrypt inputs cannot prove knowledge of the complete password.
    Their owners must use mailbox-verified password recovery.
    """
    if not isinstance(hashed_password, str) or not hashed_password:
        return False, False
    try:
        return bcrypt.checkpw(
            _new_password_bytes(plain_password), hashed_password.encode("utf-8")
        ), False
    except (ValueError, TypeError):
        return False, False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return verify_password_and_upgrade(plain_password, hashed_password)[0]


# JWT helpers
def _create_token(data: dict, expires_delta: timedelta, key: str) -> str:
    to_encode = {"ver": 0, **data}
    exp = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    to_encode.update({"exp": exp})
    return jwt.encode(to_encode, key, algorithm=ALGORITHM)


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    minutes = expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    return _create_token(data, timedelta(minutes=minutes), SECRET_KEY)


def create_refresh_token(data: dict, expires_days: Optional[int] = None) -> str:
    days = expires_days or REFRESH_TOKEN_EXPIRE_DAYS
    payload = {**data, "typ": "refresh"}
    return _create_token(payload, timedelta(days=days), REFRESH_SECRET_KEY)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "user_id", "ver"]})
    except InvalidTokenError:
        raise ValueError("Invalid or expired token")


def decode_refresh_token(token: str) -> dict:
    try:
        data = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "user_id", "ver"]})
        if data.get("typ") != "refresh":
            raise ValueError("Not a refresh token")
        return data
    except InvalidTokenError:
        raise ValueError("Invalid or expired refresh token")
