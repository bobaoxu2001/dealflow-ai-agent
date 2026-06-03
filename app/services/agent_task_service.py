"""Persistence helpers for agent tasks and node-level audit logs."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentAuditLog, AgentTask
from app.utils.logging import get_logger

logger = get_logger(__name__)


def new_task_id() -> str:
    return f"TASK-{uuid.uuid4().hex[:12]}"


class AgentTaskService:
    def __init__(self, session: Session):
        self.session = session

    def create_task(self, opportunity_id: str, account_id: str | None, user_task: str) -> AgentTask:
        task = AgentTask(
            task_id=new_task_id(),
            opportunity_id=opportunity_id,
            account_id=account_id,
            user_task=user_task,
            execution_status="running",
            approval_status="not_required",
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get_task(self, task_id: str) -> AgentTask | None:
        return self.session.execute(
            select(AgentTask).where(AgentTask.task_id == task_id)
        ).scalar_one_or_none()

    def save_state(self, task: AgentTask, state: dict) -> None:
        task.state = state
        task.execution_status = state.get("execution_status", task.execution_status)
        task.approval_status = state.get("approval_status", task.approval_status)
        task.requires_human_approval = bool(state.get("requires_human_approval", False))
        if state.get("account_id"):
            task.account_id = state["account_id"]
        self.session.add(task)
        self.session.flush()

    def write_audit(
        self,
        task_id: str,
        node_name: str,
        input_summary: str = "",
        output_summary: str = "",
        status: str = "ok",
        error_message: str | None = None,
    ) -> AgentAuditLog:
        log = AgentAuditLog(
            task_id=task_id,
            node_name=node_name,
            input_summary=input_summary[:2000] if input_summary else None,
            output_summary=output_summary[:2000] if output_summary else None,
            status=status,
            error_message=error_message,
        )
        self.session.add(log)
        self.session.flush()
        return log
