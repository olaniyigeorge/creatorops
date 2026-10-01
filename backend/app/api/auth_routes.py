import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import UserOut
from app.auth import google
from app.auth.security import create_session_token
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "oauth_state"
_NEXT_COOKIE = "oauth_next"


def _safe_next(path: str | None) -> str:
    """Only same-site relative paths: anything else would be an open redirect."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path and len(path) <= 500:
        return path
    return "/"
_secure = settings.ENV.lower() == "production"


@router.get("/google/login")
def google_login(next: str | None = None):
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(google.authorization_url(state))
    resp.set_cookie(
        _NEXT_COOKIE, _safe_next(next), max_age=600, httponly=True, secure=_secure, samesite="lax"
    )
    resp.set_cookie(
        _STATE_COOKIE, state, max_age=600, httponly=True, secure=_secure, samesite="lax"
    )
    return resp


@router.get("/google/callback")
def google_callback(
    request: Request, code: str, state: str, db: Session = Depends(get_db)
):
    expected = request.cookies.get(_STATE_COOKIE)
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    identity = google.fetch_identity(code)
    if not identity.email_verified:
        raise HTTPException(status_code=400, detail="Google email is not verified")

    email = identity.email.lower()
    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user is None:
        # Link to an existing row by email (e.g. created from an invitation lookup).
        user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=identity.name, google_sub=identity.sub)
        db.add(user)
    else:
        user.google_sub = identity.sub
        user.name = user.name or identity.name
    db.commit()

    resp = RedirectResponse(settings.CLIENT_DOMAIN.rstrip("/") + _safe_next(request.cookies.get(_NEXT_COOKIE)))
    resp.delete_cookie(_STATE_COOKIE)
    resp.delete_cookie(_NEXT_COOKIE)
    # SameSite=Lax is the CSRF defence for cookie auth: the frontend proxies /api
    # through Next.js rewrites, so API calls are same-site.
    resp.set_cookie(
        settings.SESSION_COOKIE_NAME,
        create_session_token(user.id),
        max_age=settings.SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=_secure,
        samesite="lax",
    )
    return resp


class DevLogin(BaseModel):
    email: EmailStr
    name: str = ""


@router.post("/dev-login", status_code=204)
def dev_login(body: DevLogin, response: Response, db: Session = Depends(get_db)):
    """Local testing only. 404 unless DEV_LOGIN_ENABLED, and never in production."""
    if not settings.DEV_LOGIN_ENABLED or settings.ENV.lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=body.name or email.split("@")[0])
        db.add(user)
        db.commit()
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        create_session_token(user.id),
        max_age=settings.SESSION_TTL_HOURS * 3600,
        httponly=True,
        secure=False,
        samesite="lax",
    )


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(settings.SESSION_COOKIE_NAME)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
