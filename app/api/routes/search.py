"""Vector search + context retrieval routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.crm import (
    ContextResponse,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.services.crm_service import CRMService
from app.services.vector_search_service import VectorSearchService

router = APIRouter(tags=["search"])


@router.post("/search/vector", response_model=VectorSearchResponse)
def vector_search(req: VectorSearchRequest, session: Session = Depends(get_session)):
    svc = VectorSearchService(session)
    if req.opportunity_id:
        hits = svc.search_by_opportunity(req.opportunity_id, req.query, req.top_k)
    elif req.account_id:
        hits = svc.search_by_account(req.account_id, req.query, req.top_k)
    else:
        hits = svc.global_search(req.query, req.top_k)
    results = [h.to_dict() for h in hits]
    return VectorSearchResponse(query=req.query, count=len(results), results=results)


@router.get("/accounts/{account_id}/context", response_model=ContextResponse)
def account_context(
    account_id: str,
    query: str = "client risks blockers support history",
    top_k: int = 5,
    session: Session = Depends(get_session),
):
    crm = CRMService(session)
    account = crm.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    contacts = crm.get_account_contacts(account_id)
    tickets = crm.get_account_tickets(account_id)
    hits = VectorSearchService(session).search_by_account(account_id, query, top_k)
    structured = {
        "account": {
            "account_id": account.account_id,
            "account_name": account.account_name,
            "sector": account.sector,
        },
        "contacts": [{"name": c.name, "email": c.email} for c in contacts],
        "ticket_count": len(tickets),
    }
    return ContextResponse(structured=structured, documents=[h.to_dict() for h in hits])


@router.get("/opportunities/{opportunity_id}/context", response_model=ContextResponse)
def opportunity_context(
    opportunity_id: str,
    query: str = "client risks blockers support history",
    top_k: int = 5,
    session: Session = Depends(get_session),
):
    crm = CRMService(session)
    structured = crm.get_opportunity_context(opportunity_id)
    if not structured:
        raise HTTPException(status_code=404, detail=f"Opportunity {opportunity_id} not found")
    hits = VectorSearchService(session).search_by_opportunity(opportunity_id, query, top_k)
    return ContextResponse(structured=structured, documents=[h.to_dict() for h in hits])
