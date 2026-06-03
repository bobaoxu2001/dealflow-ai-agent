"""FastAPI dependencies."""
from __future__ import annotations

from app.db.session import get_session  # re-exported for route modules

__all__ = ["get_session"]
