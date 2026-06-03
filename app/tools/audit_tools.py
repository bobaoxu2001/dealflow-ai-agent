"""Audit log helper shared by graph nodes.

Each node calls `record` to (a) append a compact entry to the in-state audit_log
and (b) persist a row to `agent_audit_logs` for durable, queryable history.
"""
from __future__ import annotations

from app.services.agent_task_service import AgentTaskService


def record(
    session,
    state: dict,
    node_name: str,
    input_summary: str = "",
    output_summary: str = "",
    status: str = "ok",
    error_message: str | None = None,
) -> list[dict]:
    """Persist an audit row and return the updated in-state audit_log list."""
    AgentTaskService(session).write_audit(
        task_id=state["task_id"],
        node_name=node_name,
        input_summary=input_summary,
        output_summary=output_summary,
        status=status,
        error_message=error_message,
    )
    entry = {
        "node": node_name,
        "status": status,
        "input": input_summary[:200],
        "output": output_summary[:200],
    }
    if error_message:
        entry["error"] = error_message[:200]
    return (state.get("audit_log") or []) + [entry]
