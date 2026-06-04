"""LangGraph node implementations.

Nodes are created via `make_nodes(session)` so each closure has access to the
active DB session. Every node:
  * does one well-scoped step,
  * delegates the domain work to a bounded role agent (see app/agents/roles.py),
  * writes a durable audit log entry, and
  * returns a partial state update (last-write-wins merge).

Node internals are deterministic by default (no API key required). LangGraph is
the supervisor; the role agents wrap the underlying tools/services. Timing and
errors are captured by app/agents/instrumentation.py.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.agents.roles import (
    CRMGovernanceAgent,
    CustomerContextAgent,
    DealAnalysisAgent,
    ExecutiveSynthesisAgent,
)
from app.db.models import CRMWriteback
from app.tools import audit_tools
from app.tools.crm_tools import crm_writeback
from app.utils.logging import get_logger

logger = get_logger(__name__)


def make_nodes(session: Session) -> dict:
    """Return a mapping of node_name -> node callable bound to `session`."""

    context_agent = CustomerContextAgent(session)
    analysis_agent = DealAnalysisAgent()
    governance_agent = CRMGovernanceAgent()
    synthesis_agent = ExecutiveSynthesisAgent()

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
        context = context_agent.structured_context(opp_id)
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
        docs = context_agent.retrieve_documents(
            query, account_id=account_id,
            opportunity_id=state.get("opportunity_id"), top_k=6,
        )
        audit = audit_tools.record(
            session, state, "retrieve_vector_context",
            input_summary=f"query='{query[:60]}' account_id={account_id}",
            output_summary=f"retrieved {len(docs)} documents",
        )
        return {"retrieved_documents": docs, "audit_log": audit}

    def analyze_risks(state: dict) -> dict:
        score, flags = analysis_agent.score_risks(
            state.get("structured_context", {}), state.get("retrieved_documents", [])
        )
        audit = audit_tools.record(
            session, state, "analyze_risks",
            input_summary=f"{len(state.get('retrieved_documents', []))} docs",
            output_summary=f"risk_score={score}, flags={len(flags)}",
        )
        return {"risk_score": score, "risk_flags": flags, "audit_log": audit}

    def detect_missing_fields_node(state: dict) -> dict:
        missing = analysis_agent.missing_fields(state.get("structured_context", {}))
        audit = audit_tools.record(
            session, state, "detect_missing_fields",
            input_summary="opportunity fields",
            output_summary=f"missing={missing}",
        )
        return {"missing_fields": missing, "audit_log": audit}

    def recommend_next_steps(state: dict) -> dict:
        actions = synthesis_agent.recommend_actions(
            state.get("risk_flags", []),
            state.get("missing_fields", []),
            state.get("risk_score", 0.0),
        )
        audit = audit_tools.record(
            session, state, "recommend_next_steps",
            output_summary=f"{len(actions)} recommendations",
        )
        return {"recommended_actions": actions, "audit_log": audit}

    def draft_crm_update(state: dict) -> dict:
        """Propose CRM field changes via the governance role. Conservative + explainable."""
        opp = (state.get("structured_context") or {}).get("opportunity") or {}
        draft = governance_agent.draft_update(
            opp, state.get("risk_score", 0.0), state.get("missing_fields", [])
        )
        draft["opportunity_id"] = state["opportunity_id"]
        audit = audit_tools.record(
            session, state, "draft_crm_update",
            output_summary=f"proposed changes: {list(draft['changes'].keys()) or 'none'}",
        )
        return {"crm_update_draft": draft, "audit_log": audit}

    def approval_router(state: dict) -> dict:
        """Compute whether human approval is required and set status flags."""
        required, reasons = governance_agent.requires_approval(
            state.get("risk_score", 0.0), state.get("crm_update_draft", {})
        )
        has_changes = bool((state.get("crm_update_draft") or {}).get("changes"))
        if not has_changes:
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
        # Optional LLM synthesis (via the executive-synthesis role): turns the
        # structured report into a narrative. It never decides writeback/approval.
        summary, llm_name = synthesis_agent.synthesize(report)
        report["executive_summary"] = summary
        report["synthesized_by"] = llm_name
        audit = audit_tools.record(
            session, state, "finalize_report",
            output_summary=f"report assembled (summary by '{llm_name}')",
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
