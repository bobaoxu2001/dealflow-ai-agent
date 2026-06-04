"""Agent workflow routes: review, status, approve, reject."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.agents.graph import (
    create_queued_task,
    run_review_task_in_background,
    run_review_workflow,
)
from app.db.models import AgentAuditLog
from app.schemas.agent import (
    AgentTaskResponse,
    ApprovalRequest,
    ReviewOpportunityRequest,
    TraceResponse,
    TraceStep,
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
        error=state.get("error"),
    )


@router.post("/review-opportunity", response_model=AgentTaskResponse)
def review_opportunity(req: ReviewOpportunityRequest, session: Session = Depends(get_session)):
    if CRMService(session).get_opportunity(req.opportunity_id) is None:
        raise HTTPException(status_code=404, detail=f"Opportunity {req.opportunity_id} not found")
    state = run_review_workflow(session, req.opportunity_id, req.task)
    return _state_to_response(state["task_id"], state)


@router.post("/review-opportunity-async", response_model=AgentTaskResponse)
def review_opportunity_async(
    req: ReviewOpportunityRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Long-running mode: create the task, return immediately, run in background.

    Status transitions: queued -> running -> completed | pending_approval | error.
    Poll GET /agent/tasks/{task_id} (or /trace) for progress. An unknown
    opportunity is accepted, then terminated as `error` by the background runner.
    """
    task = create_queued_task(session, req.opportunity_id, req.task)
    background_tasks.add_task(run_review_task_in_background, task.task_id)
    return _state_to_response(task.task_id, task.state or {})


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
def get_task(task_id: str, session: Session = Depends(get_session)):
    task = AgentTaskService(session).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return _state_to_response(task.task_id, task.state or {})


@router.get("/tasks/{task_id}/trace", response_model=TraceResponse)
def get_task_trace(task_id: str, session: Session = Depends(get_session)):
    """Return the ordered node-by-node execution trace for a task.

    Built from the durable `agent_audit_logs` rows, this is the agent's
    observability surface — every node's status, inputs, and outputs in order.
    """
    task = AgentTaskService(session).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    logs = (
        session.query(AgentAuditLog)
        .filter_by(task_id=task_id)
        .order_by(AgentAuditLog.id)
        .all()
    )
    steps = [
        TraceStep(
            step=i + 1,
            node_name=log.node_name,
            status=log.status,
            duration_ms=log.duration_ms,
            input_summary=log.input_summary,
            output_summary=log.output_summary,
            error_message=log.error_message,
            timestamp=log.created_at.isoformat() if log.created_at else None,
        )
        for i, log in enumerate(logs)
    ]
    return TraceResponse(
        task_id=task_id,
        execution_status=task.execution_status,
        approval_status=task.approval_status,
        step_count=len(steps),
        trace=steps,
    )


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
