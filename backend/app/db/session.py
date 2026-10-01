from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


@lru_cache
def get_engine() -> Engine:
    # Keep pools small: API + worker + beat each hold one, and Supabase caps connections.
    return create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
    )


def SessionLocal() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
