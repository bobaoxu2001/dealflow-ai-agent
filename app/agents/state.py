"""LangGraph agent state definition.

Nodes use last-write-wins merge semantics (the LangGraph default). The
`audit_log` list is accumulated explicitly by each node (read -> append ->
return the full list), which keeps the data flow easy to follow and avoids
hidden reducer magic.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    opportunity_id: str
    account_id: str | None
    user_task: str

    structured_context: dict[str, Any]
    retrieved_documents: list[dict[str, Any]]
    risk_flags: list[dict[str, Any]]
    risk_score: float
    missing_fields: list[str]
    recommended_actions: list[str]
    crm_update_draft: dict[str, Any]

    requires_human_approval: bool
    approval_status: str  # not_required | pending | approved | rejected
    execution_status: str  # running | pending_approval | completed | rejected | error
    approved_by: str | None
    rejection_reason: str | None

    final_report: dict[str, Any]
    audit_log: list[dict[str, Any]]


def initial_state(task_id: str, opportunity_id: str, user_task: str) -> AgentState:
    return AgentState(
        task_id=task_id,
        opportunity_id=opportunity_id,
        account_id=None,
        user_task=user_task,
        structured_context={},
        retrieved_documents=[],
        risk_flags=[],
        risk_score=0.0,
        missing_fields=[],
        recommended_actions=[],
        crm_update_draft={},
        requires_human_approval=False,
        approval_status="not_required",
        execution_status="running",
        approved_by=None,
        rejection_reason=None,
        final_report={},
        audit_log=[],
    )
