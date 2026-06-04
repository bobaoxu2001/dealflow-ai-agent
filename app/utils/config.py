"""Application configuration loaded from environment variables.

All settings have sensible local-first defaults so the project runs without any
external services. Override via environment variables or a `.env` file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = two levels up from this file (app/utils/config.py -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "DealFlow AI Agent"
    environment: str = Field(default="local")
    log_level: str = Field(default="INFO")
    api_prefix: str = ""

    # --- Database ---
    # Default to a local SQLite file so the project is runnable with zero infra.
    # docker-compose overrides this with a PostgreSQL + pgvector URL.
    database_url: str = Field(
        default=f"sqlite:///{PROJECT_ROOT / 'dealflow.db'}",
    )

    # --- Embeddings ---
    # "local" -> deterministic hash-based embeddings (no API key required).
    # "openai" -> use OpenAI embeddings if OPENAI_API_KEY is set.
    embedding_provider: str = Field(default="local")
    embedding_dim: int = Field(default=384)
    openai_api_key: str | None = Field(default=None)
    openai_embedding_model: str = Field(default="text-embedding-3-small")

    # --- LLM (optional) ---
    # Agent logic/routing is deterministic; an LLM only synthesizes the final
    # narrative report. "local" -> deterministic template (no key). "openai" ->
    # real LLM if OPENAI_API_KEY is set (falls back to local otherwise).
    llm_provider: str = Field(default="local")
    llm_model: str = Field(default="gpt-4o-mini")
    openai_chat_model: str = Field(default="gpt-4o-mini")  # kept for back-compat

    # --- Agent / risk thresholds ---
    high_risk_threshold: float = Field(default=0.6)
    # CRM fields considered "important" -> changing them needs human approval.
    approval_required_fields: str = Field(default="stage,deal_value,close_date")

    # --- CRM adapter (external integration is OFF by default) ---
    # local         -> read/write the project's own PostgreSQL/SQLite (default)
    # mock_external -> simulated external CRM (no network; for demos/tests)
    # hubspot       -> real HubSpot CRM v3 API (opt-in; dry-run by default)
    crm_adapter: str = Field(default="local")
    hubspot_access_token: str | None = Field(default=None)
    hubspot_base_url: str = Field(default="https://api.hubapi.com")
    # Safety: real PATCH writeback is disabled unless this is explicitly false.
    hubspot_dry_run: bool = Field(default=True)
    hubspot_timeout_seconds: int = Field(default=10)

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    @property
    def approval_field_set(self) -> set[str]:
        return {f.strip() for f in self.approval_required_fields.split(",") if f.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
