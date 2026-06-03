"""Vector retrieval tool wrapper for the agent."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.vector_search_service import VectorSearchService


def vector_search(
    session: Session,
    query: str,
    account_id: str | None = None,
    opportunity_id: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    svc = VectorSearchService(session)
    if opportunity_id:
        hits = svc.search_by_opportunity(opportunity_id, query, top_k)
        if hits:
            return [h.to_dict() for h in hits]
    if account_id:
        return [h.to_dict() for h in svc.search_by_account(account_id, query, top_k)]
    return [h.to_dict() for h in svc.global_search(query, top_k)]


def build_vector_search_tool(session: Session):
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=lambda query, account_id=None, top_k=5: vector_search(
            session, query, account_id=account_id, top_k=top_k
        ),
        name="vector_search_tool",
        description="Semantic search over support tickets, client/risk/meeting notes for an account.",
    )
