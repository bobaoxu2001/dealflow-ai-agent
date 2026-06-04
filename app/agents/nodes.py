"""LangGraph node implementations.

Nodes are created via `make_nodes(session)` so each closure has access to the
active DB session. Every node:
  * does one well-scoped step,
  * writes a durable audit log entry, and
  * returns a partial state update (last-write-wins merge).

Node internals are deterministic heuristics by default (no API key required).
The orchestration, routing, state, and human-in-the-loop are the real LangGraph
demonstration; node logic can be swapped for LLM calls without touching the graph.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.llm_service import get_llm_provider
from app.tools import audit_tools
from app.tools.approval_tools import needs_human_approval
from app.tools.crm_tools import crm_read, crm_writeback
from app.tools.risk_tools import detect_missing_fields, score_risks
from app.tools.vector_tools import vector_search
from app.utils.logging import get_logger

logger = get_logger(__name__)


def make_nodes(session: Session) -> dict:
    """Return a mapping of node_name -> node callable bound to `session`."""

    def parse_task(state: dict) -> dict:
        task = state.get("user_task", "")
        audit = audit_tools.record(
            session, state, "parse_task",
            input_summary=task,
            output_summary=f"opportunity_id={state.get('opportunity_id')}",
        )
        return {"execution_status": "running", "audit_log": audit}

    def retrieve_crm_context(state: dict) -> dict:
        opp_id = state["opportunity_id"]
        context = crm_read(session, opp_id)
        account_id = (context.get("opportunity") or {}).get("account_id")
        audit = audit_tools.record(
            session, state, "retrieve_crm_context",
            input_summary=f"opportunity_id={opp_id}",
            output_summary=f"account_id={account_id}, "
            f"tickets={(context.get('ticket_summary') or {}).get('total', 0)}",
        )
        return {
            "structured_context": context,
            "account_id": account_id,
            "audit_log": audit,
        }

    def retrieve_vector_context(state: dict) -> dict:
        account_id = state.get("account_id")
        query = state.get("user_task") or "client risks blockers history"
        docs = vector_search(
            session, query, account_id=account_id,
            opportunity_id=state.get("opportunity_id"), top_k=6,
        )
        audit = audit_tools.record(
            session, state, "retrieve_vector_context",
            input_summary=f"query='{query[:60]}' account_id={account_id}",
            output_summary=f"retrieved {len(docs)} documents",
        )
        return {"retrieved_documents": docs, "audit_log": audit}

    def analyze_risks(state: dict) -> dict:
        score, flags = score_risks(
            state.get("structured_context", {}), state.get("retrieved_documents", [])
        )
        audit = audit_tools.record(
            session, state, "analyze_risks",
            input_summary=f"{len(state.get('retrieved_documents', []))} docs",
            output_summary=f"risk_score={score}, flags={len(flags)}",
        )
        return {"risk_score": score, "risk_flags": flags, "audit_log": audit}

    def detect_missing_fields_node(state: dict) -> dict:
        missing = detect_missing_fields(state.get("structured_context", {}))
        audit = audit_tools.record(
            session, state, "detect_missing_fields",
            input_summary="opportunity fields",
            output_summary=f"missing={missing}",
        )
        return {"missing_fields": missing, "audit_log": audit}

    def recommend_next_steps(state: dict) -> dict:
        actions: list[str] = []
        flags = state.get("risk_flags", [])
        missing = state.get("missing_fields", [])
        if any(f["type"] in {"high_priority_tickets", "open_tickets"} for f in flags):
            actions.append("Schedule a customer success check-in to address open support issues.")
        if any(f["type"] == "signal" for f in flags):
            actions.append("Review flagged support history for churn/competitor signals before next call.")
        if missing:
            actions.append(f"Complete missing CRM fields: {', '.join(missing)}.")
        if state.get("risk_score", 0) >= 0.6:
            actions.append("Escalate to deal-desk: high overall risk score.")
        if not actions:
            actions.append("Advance opportunity to next stage; no blockers detected.")
        audit = audit_tools.record(
            session, state, "recommend_next_steps",
            output_summary=f"{len(actions)} recommendations",
        )
        return {"recommended_actions": actions, "audit_log": audit}

    def draft_crm_update(state: dict) -> dict:
        """Propose CRM field changes. Conservative + explainable."""
        opp = (state.get("structured_context") or {}).get("opportunity") or {}
        changes: dict = {}
        missing = state.get("missing_fields", [])

        # Fill an obviously-missing sales stage with a safe default proposal.
        if "stage" in missing:
            changes["stage"] = "Engaging"
        # If risk is high, propose moving stage to "On Hold" pending review.
        if state.get("risk_score", 0) >= 0.6 and opp.get("stage") not in (None, "Won", "Lost"):
            changes["stage"] = "On Hold"

        draft = {
            "opportunity_id": state["opportunity_id"],
            "changes": changes,
            "rationale": _draft_rationale(state, changes),
        }
        audit = audit_tools.record(
            session, state, "draft_crm_update",
            output_summary=f"proposed changes: {list(changes.keys()) or 'none'}",
        )
        return {"crm_update_draft": draft, "audit_log": audit}

    def approval_router(state: dict) -> dict:
        """Compute whether human approval is required and set status flags."""
        required, reasons = needs_human_approval(
            state.get("risk_score", 0.0), state.get("crm_update_draft", {})
        )
        has_changes = bool((state.get("crm_update_draft") or {}).get("changes"))
        if not has_changes:
            # Nothing to write back; no approval needed.
            audit = audit_tools.record(
                session, state, "approval_router",
                output_summary="no CRM changes -> skip writeback",
            )
            return {
                "requires_human_approval": False,
                "approval_status": "not_required",
                "audit_log": audit,
            }
        if required:
            audit = audit_tools.record(
                session, state, "approval_router",
                output_summary=f"approval required: {reasons}",
                status="pending_approval",
            )
            return {
                "requires_human_approval": True,
                "approval_status": "pending",
                "execution_status": "pending_approval",
                "audit_log": audit,
            }
        audit = audit_tools.record(
            session, state, "approval_router",
            output_summary="auto-approved (low risk, non-critical fields)",
        )
        return {
            "requires_human_approval": False,
            "approval_status": "approved",
            "audit_log": audit,
        }

    def writeback_crm(state: dict) -> dict:
        import uuid

        from app.db.models import CRMWriteback

        draft = state.get("crm_update_draft", {})
        changes = draft.get("changes", {})
        applied = crm_writeback(session, state["opportunity_id"], changes) if changes else {}

        wb = CRMWriteback(
            writeback_id=f"WB-{uuid.uuid4().hex[:10]}",
            task_id=state["task_id"],
            opportunity_id=state["opportunity_id"],
            account_id=state.get("account_id"),
            changes=applied,
            status="applied",
            applied_by=state.get("approved_by") or "agent",
        )
        session.add(wb)
        session.flush()

        audit = audit_tools.record(
            session, state, "writeback_crm",
            input_summary=f"changes={list(changes.keys())}",
            output_summary=f"applied {list(applied.keys())} writeback_id={wb.writeback_id}",
        )
        return {"audit_log": audit, "crm_update_draft": {**draft, "applied": applied,
                                                         "writeback_id": wb.writeback_id}}

    def finalize_report(state: dict) -> dict:
        report = {
            "opportunity_id": state["opportunity_id"],
            "account_id": state.get("account_id"),
            "risk_score": state.get("risk_score", 0.0),
            "risk_flags": state.get("risk_flags", []),
            "missing_fields": state.get("missing_fields", []),
            "recommended_actions": state.get("recommended_actions", []),
            "crm_update": state.get("crm_update_draft", {}),
            "approval_status": state.get("approval_status"),
            "documents_reviewed": len(state.get("retrieved_documents", [])),
        }
        # Optional LLM synthesis: turns the structured report into a narrative.
        # The LLM never decides writeback/approval — those are already settled.
        llm = get_llm_provider()
        report["executive_summary"] = llm.synthesize_report(report)
        report["synthesized_by"] = llm.name
        audit = audit_tools.record(
            session, state, "finalize_report",
            output_summary=f"report assembled (summary by '{llm.name}')",
        )
        return {
            "final_report": report,
            "execution_status": "completed",
            "audit_log": audit,
        }

    return {
        "parse_task": parse_task,
        "retrieve_crm_context": retrieve_crm_context,
        "retrieve_vector_context": retrieve_vector_context,
        "analyze_risks": analyze_risks,
        "detect_missing_fields": detect_missing_fields_node,
        "recommend_next_steps": recommend_next_steps,
        "draft_crm_update": draft_crm_update,
        "approval_router": approval_router,
        "writeback_crm": writeback_crm,
        "finalize_report": finalize_report,
    }


def _draft_rationale(state: dict, changes: dict) -> str:
    if not changes:
        return "No changes proposed; opportunity data is complete and risk is acceptable."
    parts = []
    if state.get("risk_score", 0) >= 0.6:
        parts.append("elevated risk score")
    if state.get("missing_fields"):
        parts.append(f"missing fields {state['missing_fields']}")
    return "Proposed because of: " + ", ".join(parts) if parts else "Routine update."
