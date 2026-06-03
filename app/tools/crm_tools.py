"""CRM read/write tools used by the agent.

These are thin, side-effect-aware wrappers around `CRMService` exposed as
LangChain `StructuredTool`s. The agent graph mostly calls the underlying
functions directly (deterministic orchestration), while the StructuredTool
wrappers document the tool surface and make it usable from an LLM tool-router.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.crm_service import CRMService


def crm_read(session: Session, opportunity_id: str) -> dict:
    """Read structured CRM context for an opportunity (account, contacts, tickets)."""
    return CRMService(session).get_opportunity_context(opportunity_id)


def crm_writeback(session: Session, opportunity_id: str, changes: dict) -> dict:
    """Apply approved field changes to an opportunity. Returns applied diffs."""
    return CRMService(session).apply_opportunity_update(opportunity_id, changes)


def build_crm_read_tool(session: Session):
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=lambda opportunity_id: crm_read(session, opportunity_id),
        name="crm_read_tool",
        description="Read structured CRM context (account, contacts, ticket summary) for an opportunity_id.",
    )
