"""SQLAlchemy engine/session management.

Works with both SQLite (zero-infra local default) and PostgreSQL+pgvector
(docker-compose / production-style). The dialect is detected from DATABASE_URL.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def _make_engine():
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        # Needed for SQLite when used across FastAPI threads / tests.
        connect_args = {"check_same_thread": False}
    engine = create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
