"""Google sign-in (OAuth authorization-code flow). Sign-in scopes only.

Gmail send, Calendar and YouTube scopes are requested later through incremental
consent, so users are not asked for sensitive scopes at login.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass
class GoogleIdentity:
    sub: str
    email: str
    name: str
    email_verified: bool


def authorization_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode(
        {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )


def fetch_identity(code: str) -> GoogleIdentity:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    claims = id_token.verify_oauth2_token(
        resp.json()["id_token"],
        google_requests.Request(),
        settings.GOOGLE_OAUTH_CLIENT_ID,
    )
    return GoogleIdentity(
        sub=claims["sub"],
        email=claims["email"].lower(),
        name=claims.get("name", ""),
        email_verified=bool(claims.get("email_verified")),
    )
