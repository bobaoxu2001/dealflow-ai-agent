"""Database initialization: enable pgvector (Postgres only) and create tables."""
from __future__ import annotations

from sqlalchemy import text

from app.db import models  # noqa: F401  (ensure models are registered on Base)
from app.db.session import Base, engine
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def enable_pgvector() -> None:
    """Create the pgvector extension when running on PostgreSQL."""
    if not settings.is_postgres:
        logger.info("Skipping pgvector extension (non-postgres database).")
        return
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    logger.info("Ensured pgvector extension exists.")


def create_all() -> None:
    enable_pgvector()
    Base.metadata.create_all(bind=engine)
    logger.info("Created all tables on %s", engine.url.render_as_string(hide_password=True))


def init_db() -> None:
    create_all()


if __name__ == "__main__":
    init_db()
