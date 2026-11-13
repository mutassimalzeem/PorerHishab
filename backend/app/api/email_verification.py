"""Mailbox ownership and recovery endpoints; challenge values never enter API responses."""
from html import escape
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from app.api.auth import rate_limit_guard, record_failed_attempt
from app.core.config import settings
from app.core.password_policy import NewPassword
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.email_verification import create_verification_token, consume_verification_token
from app.services.notifications.email_sender import EmailMessage, get_identity_email_sender

router = APIRouter(prefix="/auth", tags=["account recovery"])


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


class PasswordReset(TokenRequest):
    password: NewPassword


class ChallengeStatus(BaseModel):
    message: str


def throttle(request: Request, suffix: str):
    ip = request.client.host if request.client else "unknown"
    key = "mailbox:" + ip + ":" + suffix
    rate_limit_guard(key)
    record_failed_attempt(key)


def send_challenge(db: Session, user: User, purpose: str):
    if not settings.SECURITY_EMAIL_DELIVERY_ENABLED:
        return
    recipient, owner_id = user.email, user.id
    raw = create_verification_token(db, user, purpose)
    if raw is None:
        return
    path = "reset-password" if purpose == "reset_password" else "verify-email"
    link = settings.FRONTEND_BASE_URL.rstrip("/") + "/" + path + "#token=" + raw
    subject = "Reset your PorerHishab password" if purpose == "reset_password" else "Verify your PorerHishab email"
    body = subject + ". This link expires in 30 minutes.\n\n" + link
    # This is a requested identity challenge, never a financial notification.
    try:
        result = get_identity_email_sender().send(EmailMessage(
            recipient, subject, body,
            "<p>" + escape(subject) + '.</p><p><a href="' + escape(link, quote=True) + '">Continue</a></p><p>This link expires in 30 minutes.</p>',
        ))
        delivered = result.success
    except (ValueError, OSError):
        # Configuration/transport failures keep the same privacy-safe API response.
        delivered = False
    if not delivered:
        # Invalidate exactly this challenge while retaining its resend timestamp.
        # A failed old attempt must not delete a newer concurrent challenge.
        from app.models.email_verification import EmailVerificationToken
        db.query(EmailVerificationToken).filter_by(
            user_id=owner_id, purpose=purpose,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        ).update({EmailVerificationToken.used_at: datetime.now(timezone.utc)}, synchronize_session=False)
        db.commit()


@router.post("/email-verification/request", response_model=ChallengeStatus, status_code=202)
def request_verification(request: Request, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    throttle(request, "verify")
    if not current.email_verified:
        send_challenge(db, current, "verify_email")
    return {"message": "If verification is needed, a link will be sent to your registered email."}


@router.post("/email-verification/confirm", response_model=ChallengeStatus)
def confirm_verification(payload: TokenRequest, request: Request, db: Session = Depends(get_db)):
    throttle(request, "confirm")
    if not consume_verification_token(db, payload.token, "verify_email"):
        raise HTTPException(400, "Invalid or expired verification link")
    return {"message": "Email verified. You can now enable email notifications."}


@router.post("/password-reset/request", response_model=ChallengeStatus, status_code=202)
def request_reset(payload: EmailRequest, request: Request, db: Session = Depends(get_db)):
    throttle(request, "reset")
    user = db.query(User).filter_by(email=str(payload.email)).first()
    if user is not None:
        send_challenge(db, user, "reset_password")
    return {"message": "If the account exists, a recovery link will be sent to its registered email."}


@router.post("/password-reset/confirm", response_model=ChallengeStatus)
def confirm_reset(payload: PasswordReset, request: Request, db: Session = Depends(get_db)):
    throttle(request, "confirm-reset")
    if not consume_verification_token(db, payload.token, "reset_password", payload.password):
        raise HTTPException(400, "Invalid or expired recovery link")
    return {"message": "Password updated. Sign in with your new password."}
