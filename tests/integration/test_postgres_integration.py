"""PostgreSQL + pgvector native-path integration tests.

These run ONLY when DATABASE_URL points at Postgres (the dedicated CI job with a
`pgvector/pgvector:pg16` service container). On SQLite runs they are skipped, so
the offline suite stays zero-infra.

Split of responsibilities:
  * SQLite CI job    -> full offline test suite (logic, agent, approval, etc.)
  * Postgres CI job  -> these tests verify the *native pgvector database path*
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.models import AgentTask, VectorDocument
from app.services.embedding_service import get_embedding_provider
from app.services.vector_search_service import VectorSearchService
from app.utils.config import settings

pytestmark = pytest.mark.skipif(
    not settings.is_postgres,
    reason="Postgres/pgvector integration tests run only when DATABASE_URL is Postgres",
)


def test_postgres_connection(session):
    assert session.execute(text("SELECT 1")).scalar() == 1


def test_pgvector_extension_enabled(session):
    enabled = session.execute(
        text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    assert enabled == 1, "pgvector extension should be enabled by init_db"


def test_pgvector_insert_and_search(session):
    # The demo seed (loaded by the root conftest) populates vector_documents.
    docs = session.query(VectorDocument).all()
    assert docs, "expected seeded vector documents"

    # Native pgvector path: search scoped to the high-risk demo account.
    svc = VectorSearchService(session)
    hits = svc.search_by_account("ACC-DEMO1", "customer wants to cancel and churn", top_k=3)
    assert hits
    assert hits[0].account_id == "ACC-DEMO1"
    # Scores are descending (1 - cosine_distance from pgvector).
    assert hits[0].score >= hits[-1].score


def test_pgvector_native_distance_operator(session):
    """Sanity-check the raw pgvector `<=>` operator is actually being used."""
    embedder = get_embedding_provider()
    qvec = embedder.embed("churn cancel competitor")
    row = session.execute(
        text(
            "SELECT id FROM vector_documents "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 1"
        ),
        {"q": str(qvec)},
    ).first()
    assert row is not None


def test_agent_task_persistence_on_postgres(client, session):
    """End-to-end agent run persists task + JSON state in Postgres."""
    resp = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO1", "task": "pg persistence check"},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    task = session.query(AgentTask).filter_by(task_id=task_id).one()
    assert task.state, "agent state JSON should be persisted"
    assert task.execution_status in {"pending_approval", "completed"}
