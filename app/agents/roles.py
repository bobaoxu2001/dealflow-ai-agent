"""Role-based agent layer.

These are *lightweight, bounded role objects* — not free-form autonomous agents.
Each role owns one enterprise responsibility and wraps the project's existing
deterministic tools/services. LangGraph remains the supervisor: it orders the
roles and routes between them. No role can self-direct, call arbitrary tools, or
write to the CRM outside the approval-gated path.

Roles:
  * CustomerContextAgent   - gather structured CRM context + retrieve support history
  * DealAnalysisAgent      - score risk + detect missing fields
  * CRMGovernanceAgent     - draft the CRM update + decide if approval is required
  * ExecutiveSynthesisAgent- recommend next steps + synthesize the final narrative

See docs/multi_agent_design.md for the rationale and supervision model.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.llm_service import get_llm_provider
from app.tools.approval_tools import needs_human_approval
from app.tools.crm_tools import crm_read
from app.tools.risk_tools import detect_missing_fields, score_risks
from app.tools.vector_tools import vector_search


class CustomerContextAgent:
    """Retrieves structured CRM context and unstructured support history."""

    role = "customer_context"

    def __init__(self, session: Session):
        self.session = session

    def structured_context(self, opportunity_id: str) -> dict:
        return crm_read(self.session, opportunity_id)

    def retrieve_documents(
        self, query: str, account_id: str | None, opportunity_id: str | None, top_k: int = 6
    ) -> list[dict]:
        return vector_search(
            self.session, query, account_id=account_id,
            opportunity_id=opportunity_id, top_k=top_k,
        )


class DealAnalysisAgent:
    """Scores deal risk and detects missing CRM fields (deterministic)."""

    role = "deal_analysis"

    def score_risks(self, structured_context: dict, documents: list[dict]) -> tuple[float, list[dict]]:
        return score_risks(structured_context, documents)

    def missing_fields(self, structured_context: dict) -> list[str]:
        return detect_missing_fields(structured_context)


class CRMGovernanceAgent:
    """Owns CRM-write governance: drafts the update and decides approval.

    This is the only role that proposes a writeback, and it always routes a
    high-risk / important-field change to human approval. It cannot apply writes
    itself — that happens in the approval-gated writeback node.
    """

    role = "crm_governance"

    def draft_update(self, opportunity: dict, risk_score: float, missing_fields: list[str]) -> dict:
        opp = opportunity or {}
        changes: dict = {}
        if "stage" in (missing_fields or []):
            changes["stage"] = "Engaging"
        if risk_score >= 0.6 and opp.get("stage") not in (None, "Won", "Lost"):
            changes["stage"] = "On Hold"
        return {
            "opportunity_id": opp.get("opportunity_id"),
            "changes": changes,
            "rationale": self._rationale(risk_score, missing_fields, changes),
        }

    def requires_approval(self, risk_score: float, draft: dict) -> tuple[bool, list[str]]:
        return needs_human_approval(risk_score, draft)

    @staticmethod
    def _rationale(risk_score: float, missing_fields: list[str], changes: dict) -> str:
        if not changes:
            return "No changes proposed; opportunity data is complete and risk is acceptable."
        parts = []
        if risk_score >= 0.6:
            parts.append("elevated risk score")
        if missing_fields:
            parts.append(f"missing fields {missing_fields}")
        return "Proposed because of: " + ", ".join(parts) if parts else "Routine update."


class ExecutiveSynthesisAgent:
    """Recommends next steps and synthesizes the final narrative report.

    Only this role touches the LLM, and only to summarize already-computed,
    deterministic results — it cannot change decisions or write to the CRM.
    """

    role = "executive_synthesis"

    def recommend_actions(
        self, risk_flags: list[dict], missing_fields: list[str], risk_score: float
    ) -> list[str]:
        actions: list[str] = []
        flags = risk_flags or []
        if any(f["type"] in {"high_priority_tickets", "open_tickets"} for f in flags):
            actions.append("Schedule a customer success check-in to address open support issues.")
        if any(f["type"] == "signal" for f in flags):
            actions.append("Review flagged support history for churn/competitor signals before next call.")
        if missing_fields:
            actions.append(f"Complete missing CRM fields: {', '.join(missing_fields)}.")
        if risk_score >= 0.6:
            actions.append("Escalate to deal-desk: high overall risk score.")
        if not actions:
            actions.append("Advance opportunity to next stage; no blockers detected.")
        return actions

    def synthesize(self, report: dict) -> tuple[str, str]:
        llm = get_llm_provider()
        return llm.synthesize_report(report), llm.name
