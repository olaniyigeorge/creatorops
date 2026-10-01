import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from app.core.config import settings

_ALG = "HS256"


def create_session_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(hours=settings.SESSION_TTL_HOURS),
        },
        settings.SECRET_KEY,
        algorithm=_ALG,
    )


def decode_session_token(token: str) -> Optional[uuid.UUID]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALG])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def new_invitation_token() -> tuple[str, str]:
    """Returns (token to send, sha256 hash to store). The raw token is never persisted."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
