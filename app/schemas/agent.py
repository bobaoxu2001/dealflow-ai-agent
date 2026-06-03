"""Agent API schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReviewOpportunityRequest(BaseModel):
    opportunity_id: str = Field(..., examples=["OPP-1001"])
    task: str = Field(
        default="Review this opportunity, identify blockers, summarize client history, "
        "and recommend next steps.",
    )


class AgentTaskResponse(BaseModel):
    task_id: str
    opportunity_id: str | None = None
    account_id: str | None = None
    execution_status: str
    approval_status: str
    requires_human_approval: bool
    risk_score: float | None = None
    risk_flags: list[dict[str, Any]] = []
    missing_fields: list[str] = []
    recommended_actions: list[str] = []
    crm_update_draft: dict[str, Any] = {}
    final_report: dict[str, Any] = {}
    audit_log: list[dict[str, Any]] = []


class ApprovalRequest(BaseModel):
    approver: str = Field(default="human")
    reason: str = Field(default="")
