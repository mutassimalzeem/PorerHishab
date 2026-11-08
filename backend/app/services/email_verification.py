"""One-use, purpose-bound mailbox challenges. Raw tokens are never stored."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.email_verification import EmailVerificationToken
from app.models.user import User


def create_verification_token(db: Session, user: User, purpose="verify_email") -> str | None:
    now = datetime.now(timezone.utc)
    db.query(User).filter_by(id=user.id).with_for_update().one()
    recent = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.purpose == purpose,
        EmailVerificationToken.created_at > now - timedelta(seconds=60),
    ).first()
    if recent is not None:
        db.rollback()
        return None
    db.query(EmailVerificationToken).filter_by(user_id=user.id, purpose=purpose).delete()
    raw = secrets.token_urlsafe(32)
    db.add(EmailVerificationToken(
        user_id=user.id, purpose=purpose,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=now + timedelta(minutes=30),
    ))
    db.commit()
    return raw


def consume_verification_token(db: Session, raw: str, purpose: str, password: str | None = None) -> bool:
    now = datetime.now(timezone.utc)
    record = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == hashlib.sha256(raw.encode()).hexdigest(),
        EmailVerificationToken.purpose == purpose,
        EmailVerificationToken.used_at.is_(None),
        EmailVerificationToken.expires_at > now,
    ).first()
    if record is None:
        return False
    user = db.query(User).filter_by(id=record.user_id).with_for_update().first()
    if user is None:
        return False
    claimed = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.id == record.id,
        EmailVerificationToken.used_at.is_(None),
        EmailVerificationToken.expires_at > now,
    ).update({EmailVerificationToken.used_at: now}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        return False
    if purpose == "reset_password":
        if password is None:
            return False
        from app.api.auth import get_password_hash
        user.hashed_password = get_password_hash(password)
        user.token_version += 1
    user.email_verified = True
    user.email_verified_at = now
    db.commit()
    return True


def verify_email_token(db: Session, raw_token: str) -> bool:
    return consume_verification_token(db, raw_token, "verify_email")
