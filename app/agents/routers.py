"""Conditional edge routing functions for the LangGraph workflow."""
from __future__ import annotations


def route_after_approval(state: dict) -> str:
    """Decide the edge out of `approval_router`.

    * pending approval  -> stop the graph (END); the task is persisted and waits
                           for a human approve/reject call which resumes it.
    * approved / not_required (and there are changes) -> proceed to writeback.
    * no changes        -> skip straight to the final report.
    """
    approval_status = state.get("approval_status")
    has_changes = bool((state.get("crm_update_draft") or {}).get("changes"))

    if approval_status == "pending":
        return "pending"
    if has_changes and approval_status in {"approved", "not_required"}:
        return "writeback"
    return "finalize"
