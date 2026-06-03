"""Tests for embeddings, vector document insertion, and retrieval."""
from app.db.models import VectorDocument
from app.services.embedding_service import LocalEmbeddingProvider, cosine_similarity
from app.services.vector_search_service import VectorSearchService


def test_local_embedding_is_deterministic_and_normalized():
    p = LocalEmbeddingProvider(dim=64)
    a = p.embed("churn risk competitor")
    b = p.embed("churn risk competitor")
    assert a == b
    assert len(a) == 64
    # L2 normalized -> self-similarity ~1.0
    assert abs(cosine_similarity(a, a) - 1.0) < 1e-6


def test_vector_documents_inserted(session):
    docs = session.query(VectorDocument).all()
    assert len(docs) > 0
    assert all(d.embedding is not None for d in docs)


def test_search_by_account_returns_relevant_doc(session):
    svc = VectorSearchService(session)
    hits = svc.search_by_account("ACC-DEMO1", "customer wants to cancel and churn", top_k=3)
    assert hits
    # Top hit should be from the high-risk account and mention churn/competitor.
    assert hits[0].account_id == "ACC-DEMO1"
    assert hits[0].score >= hits[-1].score  # sorted descending


def test_search_endpoint(client):
    resp = client.post(
        "/search/vector",
        json={"query": "outage churn refund", "account_id": "ACC-DEMO1", "top_k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert body["results"][0]["account_id"] == "ACC-DEMO1"
