import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.api.main import app
from app.auth.security import create_session_token
from app.core.config import settings
from app.db import models
from app.db.base import Base
from app.db.session import get_db


@pytest.fixture
def engine():
    """SQLite in-memory by default; set TEST_DATABASE_URL to run against real Postgres."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        # The suite drops every table before and after each test: refuse anything
        # that is not clearly a throwaway database.
        dbname = make_url(url).database or ""
        if "test" not in dbname:
            pytest.exit(f"TEST_DATABASE_URL must point at a database whose name contains 'test' (got '{dbname}')", returncode=2)
        eng = create_engine(url, poolclass=NullPool)
        Base.metadata.drop_all(eng)
    else:
        eng = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):  # enforce FKs/cascades like Postgres does
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    if url:
        Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


@pytest.fixture
def client(engine):
    maker = sessionmaker(bind=engine, expire_on_commit=False)

    def _get_db():
        s = maker()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_user(db: Session, email: str = None, name: str = "Test") -> models.User:
    u = models.User(email=email or f"{uuid.uuid4().hex[:8]}@example.com", name=name)
    db.add(u)
    db.commit()
    return u


def login(client: TestClient, user: models.User) -> TestClient:
    client.cookies.set(settings.SESSION_COOKIE_NAME, create_session_token(user.id))
    return client


def make_client_for(engine, user) -> TestClient:
    """A separate client (own cookie jar) logged in as `user`."""
    c = TestClient(app)
    return login(c, user)


# ---------------------------------------------------------------- shared M2/M3 helpers

from sqlalchemy.orm import sessionmaker as _sessionmaker  # noqa: E402

from app.gate import guardrails as _guardrails  # noqa: E402
from app.gate.guardrails import GuardrailVerdict  # noqa: E402
from app.tasks import dispatch as _dispatch  # noqa: E402
from app.tasks.runner import execute_run  # noqa: E402


class Worker:
    """Stands in for Celery: runs tasks inline against the test database."""

    def __init__(self):
        self.emails: list[tuple[str, str]] = []
        self.guardrail_score = 0.95


@pytest.fixture
def worker(engine, monkeypatch):
    w = Worker()
    maker = _sessionmaker(bind=engine, expire_on_commit=False)

    def inline_run(workspace_id, run_id):
        s = maker()
        try:
            execute_run(s, workspace_id, run_id)
        finally:
            s.close()

    monkeypatch.setattr(_dispatch, "enqueue_run", inline_run)
    monkeypatch.setattr(_dispatch, "enqueue_email", lambda to, subject, html: w.emails.append((to, subject)))
    # The judge is an LLM; tests control its verdict.
    monkeypatch.setattr(
        _guardrails, "rate", lambda content, rubric: GuardrailVerdict(score=w.guardrail_score)
    )
    return w


PROFILE = {
    "channel_name": "Retro Fix",
    "goal": "growth",
    "audience": "hobbyists who repair old consoles",
    "tone": "friendly and practical",
    "brand_voice": "plain language, no hype",
    "banned_topics": ["politics"],
    "extra_rules": ["never promise income"],
    "competitors": ["@retrorepair"],
    "videos_per_week": 2,
    "region_code": "us",
}


def new_workspace(client, db, autonomy="medium", onboard=True, email="owner@x.co"):
    owner = make_user(db, email)
    login(client, owner)
    wid = client.post("/workspaces", json={"name": "Acme"}).json()["id"]
    client.patch(f"/workspaces/{wid}", json={"autonomy": autonomy})
    if onboard:
        r = client.put(f"/workspaces/{wid}/onboarding", json=PROFILE)
        assert r.status_code == 200, r.text
    return wid, owner
