"""Shared FastAPI dependencies.

Keeping the authenticated-user dependency in its own module lets routers
(``app.api.transactions``, ``app.api.insights``) depend on it without
importing ``app.main`` (which would create an import cycle).
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.auth import decode_access_token
from app.core.database import get_db
from app.models.user import User

security = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token.

    The session is intentionally **not** closed here: it is the very same
    session that the endpoint dependency yields, and closing it would break
    the request-scoped unit of work.
    """
    token = creds.credentials

    try:
        data = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = data.get("user_id")
    email = data.get("sub")

    if user_id is None or not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id, User.email == email).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
