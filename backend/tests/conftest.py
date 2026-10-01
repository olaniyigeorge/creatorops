import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
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
