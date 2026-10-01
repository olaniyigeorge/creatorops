from app.auth import google
from app.auth.google import GoogleIdentity
from app.core.config import settings
from tests.conftest import login, make_user


def _patch_identity(monkeypatch, **kw):
    ident = GoogleIdentity(
        **{"sub": "g-1", "email": "Owner@Example.com", "name": "O", "email_verified": True, **kw}
    )
    monkeypatch.setattr(google, "fetch_identity", lambda code: ident)


def test_me_requires_login(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_cookie(client):
    client.cookies.set(settings.SESSION_COOKIE_NAME, "garbage")
    assert client.get("/auth/me").status_code == 401


def test_login_redirects_to_google_with_state_cookie(client):
    r = client.get("/auth/google/login", follow_redirects=False)
    assert r.status_code == 307
    assert "accounts.google.com" in r.headers["location"]
    assert "scope=openid+email+profile" in r.headers["location"]
    assert "oauth_state" in r.cookies


def test_callback_creates_user_and_session(client, monkeypatch):
    _patch_identity(monkeypatch)
    client.get("/auth/google/login", follow_redirects=False)
    state = client.cookies.get("oauth_state")
    r = client.get(f"/auth/google/callback?code=x&state={state}", follow_redirects=False)
    assert r.status_code == 307
    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "owner@example.com"


def test_callback_rejects_state_mismatch(client, monkeypatch):
    _patch_identity(monkeypatch)
    client.get("/auth/google/login", follow_redirects=False)
    r = client.get("/auth/google/callback?code=x&state=wrong", follow_redirects=False)
    assert r.status_code == 400


def test_callback_rejects_unverified_email(client, monkeypatch):
    _patch_identity(monkeypatch, email_verified=False)
    client.get("/auth/google/login", follow_redirects=False)
    state = client.cookies.get("oauth_state")
    r = client.get(f"/auth/google/callback?code=x&state={state}", follow_redirects=False)
    assert r.status_code == 400


def test_second_login_reuses_user(client, db, monkeypatch):
    _patch_identity(monkeypatch)
    for _ in range(2):
        client.get("/auth/google/login", follow_redirects=False)
        state = client.cookies.get("oauth_state")
        client.get(f"/auth/google/callback?code=x&state={state}", follow_redirects=False)
    from app.db.models import User
    assert db.query(User).count() == 1


def test_logout_clears_session(client, db):
    login(client, make_user(db))
    assert client.get("/auth/me").status_code == 200
    client.post("/auth/logout")
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401
