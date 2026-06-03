"""Vector similarity search over `vector_documents`.

On PostgreSQL it uses pgvector's `<=>` cosine-distance operator (real ANN-style
retrieval). On SQLite it loads candidate rows and ranks them with Python cosine
similarity. The public API is identical regardless of backend.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import VectorDocument
from app.services.embedding_service import cosine_similarity, get_embedding_provider
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchHit:
    id: int
    source_type: str
    source_id: str | None
    account_id: str | None
    opportunity_id: str | None
    content: str
    score: float
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "account_id": self.account_id,
            "opportunity_id": self.opportunity_id,
            "content": self.content,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }


class VectorSearchService:
    def __init__(self, session: Session):
        self.session = session
        self.embedder = get_embedding_provider()

    # -- public API -------------------------------------------------------- #
    def search_by_account(self, account_id: str, query: str, top_k: int = 5) -> list[SearchHit]:
        return self._search(query, top_k, account_id=account_id)

    def search_by_opportunity(
        self, opportunity_id: str, query: str, top_k: int = 5
    ) -> list[SearchHit]:
        return self._search(query, top_k, opportunity_id=opportunity_id)

    def global_search(self, query: str, top_k: int = 5) -> list[SearchHit]:
        return self._search(query, top_k)

    # -- internals --------------------------------------------------------- #
    def _search(
        self,
        query: str,
        top_k: int,
        account_id: str | None = None,
        opportunity_id: str | None = None,
    ) -> list[SearchHit]:
        query_vec = self.embedder.embed(query)
        if settings.is_postgres:
            return self._search_pgvector(query_vec, top_k, account_id, opportunity_id)
        return self._search_python(query_vec, top_k, account_id, opportunity_id)

    def _filtered_query(self, account_id, opportunity_id):
        stmt = select(VectorDocument)
        if account_id is not None:
            stmt = stmt.where(VectorDocument.account_id == account_id)
        if opportunity_id is not None:
            stmt = stmt.where(VectorDocument.opportunity_id == opportunity_id)
        return stmt

    def _search_pgvector(self, query_vec, top_k, account_id, opportunity_id) -> list[SearchHit]:
        # cosine_distance -> smaller is closer; similarity = 1 - distance.
        distance = VectorDocument.embedding.cosine_distance(query_vec).label("distance")
        stmt = self._filtered_query(account_id, opportunity_id).add_columns(distance)
        stmt = stmt.where(VectorDocument.embedding.isnot(None)).order_by(distance).limit(top_k)
        hits: list[SearchHit] = []
        for doc, dist in self.session.execute(stmt).all():
            hits.append(self._to_hit(doc, 1.0 - float(dist)))
        return hits

    def _search_python(self, query_vec, top_k, account_id, opportunity_id) -> list[SearchHit]:
        stmt = self._filtered_query(account_id, opportunity_id)
        scored: list[SearchHit] = []
        for doc in self.session.execute(stmt).scalars():
            if not doc.embedding:
                continue
            scored.append(self._to_hit(doc, cosine_similarity(query_vec, doc.embedding)))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]

    @staticmethod
    def _to_hit(doc: VectorDocument, score: float) -> SearchHit:
        return SearchHit(
            id=doc.id,
            source_type=doc.source_type,
            source_id=doc.source_id,
            account_id=doc.account_id,
            opportunity_id=doc.opportunity_id,
            content=doc.content,
            score=score,
            metadata=doc.doc_metadata or {},
        )
