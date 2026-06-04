"""Reusable node instrumentation for the LangGraph workflow.

Wraps each node callable to capture timing and failures without changing node
logic. Nodes still write their own rich audit entry (input/output summary); the
wrapper measures wall-clock duration and attaches it to that audit row, and on an
exception it records a dedicated error audit row. This feeds the existing
`/agent/tasks/{id}/trace` endpoint with `duration_ms` and `status` per node.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.services.agent_task_service import AgentTaskService
from app.utils.logging import get_logger

logger = get_logger(__name__)


def instrument_node(session: Session, node_name: str, fn: Callable[[dict], dict]):
    """Return a wrapped node that records duration_ms and surfaces errors."""

    def wrapped(state: dict) -> dict:
        start = time.perf_counter()
        try:
            result = fn(state)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            task_id = state.get("task_id", "unknown")
            AgentTaskService(session).write_audit(
                task_id,
                node_name,
                input_summary="",
                output_summary=f"node failed after {duration_ms} ms",
                status="error",
                error_message=str(exc),
                duration_ms=duration_ms,
            )
            logger.exception("Node %s failed for task %s", node_name, task_id)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        AgentTaskService(session).set_last_audit_duration(
            state.get("task_id", "unknown"), node_name, duration_ms
        )
        return result

    return wrapped
