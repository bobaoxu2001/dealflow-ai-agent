"""Agent workflow routes: review, status, approve, reject."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.agents.graph import run_review_workflow
from app.schemas.agent import (
    AgentTaskResponse,
    ApprovalRequest,
    ReviewOpportunityRequest,
)
from app.services.agent_task_service import AgentTaskService
from app.services.approval_service import ApprovalService
from app.services.crm_service import CRMService

router = APIRouter(prefix="/agent", tags=["agent"])


def _state_to_response(task_id: str, state: dict) -> AgentTaskResponse:
    return AgentTaskResponse(
        task_id=task_id,
        opportunity_id=state.get("opportunity_id"),
        account_id=state.get("account_id"),
        execution_status=state.get("execution_status", "unknown"),
        approval_status=state.get("approval_status", "not_required"),
        requires_human_approval=bool(state.get("requires_human_approval", False)),
        risk_score=state.get("risk_score"),
        risk_flags=state.get("risk_flags", []),
        missing_fields=state.get("missing_fields", []),
        recommended_actions=state.get("recommended_actions", []),
        crm_update_draft=state.get("crm_update_draft", {}),
        final_report=state.get("final_report", {}),
        audit_log=state.get("audit_log", []),
    )


@router.post("/review-opportunity", response_model=AgentTaskResponse)
def review_opportunity(req: ReviewOpportunityRequest, session: Session = Depends(get_session)):
    if CRMService(session).get_opportunity(req.opportunity_id) is None:
        raise HTTPException(status_code=404, detail=f"Opportunity {req.opportunity_id} not found")
    state = run_review_workflow(session, req.opportunity_id, req.task)
    return _state_to_response(state["task_id"], state)


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
def get_task(task_id: str, session: Session = Depends(get_session)):
    task = AgentTaskService(session).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return _state_to_response(task.task_id, task.state or {})


@router.post("/tasks/{task_id}/approve", response_model=AgentTaskResponse)
def approve_task(
    task_id: str, req: ApprovalRequest | None = None, session: Session = Depends(get_session)
):
    req = req or ApprovalRequest()
    try:
        state = ApprovalService(session).approve(task_id, approver=req.approver)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _state_to_response(task_id, state)


@router.post("/tasks/{task_id}/reject", response_model=AgentTaskResponse)
def reject_task(
    task_id: str, req: ApprovalRequest | None = None, session: Session = Depends(get_session)
):
    req = req or ApprovalRequest()
    try:
        state = ApprovalService(session).reject(task_id, approver=req.approver, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _state_to_response(task_id, state)
