"""CRM read/write tools used by the agent.

These thin wrappers route through the configured CRM adapter
(`app/integrations/crm_adapter.py`). By default the adapter is ``local`` and
behavior is identical to talking to the project's own database; setting
``CRM_ADAPTER=mock_external`` or ``hubspot`` retargets reads/writes without
changing the agent graph. Human approval still gates every writeback.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.integrations.crm_adapter import get_crm_adapter


def crm_read(session: Session, opportunity_id: str) -> dict:
    """Read structured CRM context for an opportunity (account, contacts, tickets)."""
    return get_crm_adapter(session).get_context(opportunity_id)


def crm_writeback(session: Session, opportunity_id: str, changes: dict) -> dict:
    """Apply approved field changes via the configured CRM adapter.

    Returns the applied-diffs mapping (``{field: {old, new}}`` for the local
    adapter). Note: a HubSpot dry-run returns no applied changes by design.
    """
    result = get_crm_adapter(session).apply_writeback(opportunity_id, changes)
    return result.get("applied", {})


def build_crm_read_tool(session: Session):
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        func=lambda opportunity_id: crm_read(session, opportunity_id),
        name="crm_read_tool",
        description="Read structured CRM context (account, contacts, ticket summary) for an opportunity_id.",
    )
