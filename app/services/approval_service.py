"""Approval lifecycle: approve/reject a pending task and resume the workflow."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.agent_task_service import AgentTaskService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ApprovalService:
    def __init__(self, session: Session):
        self.session = session
        self.tasks = AgentTaskService(session)

    def approve(self, task_id: str, approver: str = "human") -> dict:
        # Imported here to avoid a circular import with the agent graph module.
        from app.agents.graph import resume_after_approval

        task = self.tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.approval_status != "pending":
            raise ValueError(
                f"Task {task_id} is not awaiting approval "
                f"(approval_status={task.approval_status!r}, "
                f"execution_status={task.execution_status!r}). "
                "Only tasks in 'pending' approval can be approved or rejected; "
                "this is a no-op to keep the task's state consistent."
            )
        state = dict(task.state or {})
        state["approval_status"] = "approved"
        state["approved_by"] = approver
        final_state = resume_after_approval(self.session, task, state)
        return final_state

    def reject(self, task_id: str, approver: str = "human", reason: str = "") -> dict:
        task = self.tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.approval_status != "pending":
            raise ValueError(
                f"Task {task_id} is not awaiting approval "
                f"(approval_status={task.approval_status!r}, "
                f"execution_status={task.execution_status!r}). "
                "Only tasks in 'pending' approval can be approved or rejected; "
                "this is a no-op to keep the task's state consistent."
            )
        state = dict(task.state or {})
        state["approval_status"] = "rejected"
        state["execution_status"] = "rejected"
        state["rejection_reason"] = reason
        state.setdefault("audit_log", []).append(
            {"node": "approval", "status": "rejected", "summary": reason or "rejected by human"}
        )
        self.tasks.write_audit(
            task_id, "approval_router", "human review", f"rejected: {reason}", status="rejected"
        )
        self.tasks.save_state(task, state)
        self.session.commit()
        return state
