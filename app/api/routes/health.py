"""Health check route."""
from __future__ import annotations

from fastapi import APIRouter

from app.db.session import engine
from app.schemas.api import HealthResponse
from app.utils.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        database=engine.url.get_backend_name(),
        embedding_provider=settings.embedding_provider,
    )
