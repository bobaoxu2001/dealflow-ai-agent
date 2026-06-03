"""FastAPI application entrypoint for the DealFlow AI Agent."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import agent, health, search
from app.db.init_db import init_db
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables (and pgvector extension on Postgres) exist on startup.
    try:
        init_db()
    except Exception:  # pragma: no cover - startup resilience
        logger.exception("init_db failed during startup; continuing")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="LangGraph-powered enterprise CRM workflow agent for opportunity review, "
        "risk analysis, customer-context retrieval, and human-approved CRM writeback.",
        lifespan=lifespan,
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(search.router, prefix=settings.api_prefix)
    app.include_router(agent.router, prefix=settings.api_prefix)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/", tags=["root"])
    def root():
        return {
            "app": settings.app_name,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
