import os, datetime, bcrypt, time
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv
from datetime import timedelta
from pathlib import Path
from typing import Optional
from fastapi import HTTPException


# Resolve the repo-root .env explicitly so settings load identically no matter
# which directory the process was started from.
REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')
REFRESH_SECRET_KEY = os.getenv('REFRESH_SECRET_KEY', 'default_refresh_key')
PEPPER = os.getenv('PEPPER', '')
ALGORITHM = os.getenv('ALGORITHM', 'HS256')

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '30'))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS', '14'))


RATE_LIMIT_WINDOW_SECONDS = int(os.getenv('RATE_LIMIT_WINDOW_SECONDS', '300'))
RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv('RATE_LIMIT_MAX_ATTEMPTS', '5'))


MAX_BCRYPT_LENGTH = 72  # bcrypt ignores beyond 72B


def _peppered_bytes(password: str) -> bytes:
    return (PEPPER + password).encode('utf-8')[:MAX_BCRYPT_LENGTH]


def get_password_hash(plain_password: str) -> str:
    truncated = _peppered_bytes(plain_password)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(truncated, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = _peppered_bytes(plain_password)
    return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))



    #   JWT Helpers
def _create_token(data: dict, expires_delta: timedelta, key: str) -> str:
    to_encode = data.copy()
    exp = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    to_encode.update({"exp": exp})
    return jwt.encode(to_encode, key, algorithm=ALGORITHM)


def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    minutes = expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    return _create_token(data, timedelta(minutes=minutes), SECRET_KEY)


def create_refresh_token(data: dict, expires_days: Optional[int] = None) -> str:
    days = expires_days or REFRESH_TOKEN_EXPIRE_DAYS
    payload = {"typ": "refresh", **data}
    return _create_token(payload, timedelta(days=days), REFRESH_SECRET_KEY)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise ValueError("Invalid or expired token")


def decode_refresh_token(token: str) -> dict:
    try:
        data = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        if data.get("typ") != "refresh":
            raise ValueError("Not a refresh token")
        return data
    except JWTError:
        raise ValueError("Invalid or expired refresh token")


# ───────── Simple in-memory rate limiter ─────────
_failed_attempts: dict[str, list[float]] = {}

def _window_cutoff() -> float:
    return time.time() - RATE_LIMIT_WINDOW_SECONDS

def _prune_old(attempts: list[float]) -> list[float]:
    cutoff = _window_cutoff()
    return [t for t in attempts if t >= cutoff]

def rate_limit_guard(key: str):
    attempts = _failed_attempts.get(key, [])
    attempts = _prune_old(attempts)
    if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    _failed_attempts[key] = attempts

def record_failed_attempt(key: str):
    attempts = _failed_attempts.get(key, [])
    attempts = _prune_old(attempts)
    attempts.append(time.time())
    _failed_attempts[key] = attempts