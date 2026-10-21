"""Thin compatibility shim so legacy imports (``from auth import ...``)
keep working after the auth helpers moved into ``app.api.auth``.
"""

from app.api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
    RATE_LIMIT_MAX_ATTEMPTS,
    RATE_LIMIT_WINDOW_SECONDS,
    SECRET_KEY,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    rate_limit_guard,
    record_failed_attempt,
    verify_password,
)

__all__ = [
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "ALGORITHM",
    "REFRESH_SECRET_KEY",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "RATE_LIMIT_MAX_ATTEMPTS",
    "RATE_LIMIT_WINDOW_SECONDS",
    "SECRET_KEY",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "get_password_hash",
    "rate_limit_guard",
    "record_failed_attempt",
    "verify_password",
]
