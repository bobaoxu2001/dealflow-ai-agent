"""Tests for the role-based agent layer (deterministic role wrappers)."""
from app.agents.roles import (
    CRMGovernanceAgent,
    CustomerContextAgent,
    DealAnalysisAgent,
    ExecutiveSynthesisAgent,
)


def test_customer_context_agent_reads_and_retrieves(session):
    agent = CustomerContextAgent(session)
    ctx = agent.structured_context("OPP-DEMO1")
    assert ctx["opportunity"]["opportunity_id"] == "OPP-DEMO1"
    docs = agent.retrieve_documents(
        "cancel churn competitor", account_id="ACC-DEMO1", opportunity_id="OPP-DEMO1"
    )
    assert docs and all(d["account_id"] == "ACC-DEMO1" for d in docs)


def test_deal_analysis_agent_scores_and_flags(session):
    agent = DealAnalysisAgent()
    ctx = {"opportunity": {"stage": "Engaging"}, "ticket_summary": {"open": 5, "high_priority": 3}}
    docs = [{"content": "customer threatening to churn and cancel; escalated complaint"}]
    score, flags = agent.score_risks(ctx, docs)
    assert score >= 0.6 and flags
    missing = agent.missing_fields({"opportunity": {"stage": "Engaging", "deal_value": None}})
    assert "deal_value" in missing


def test_crm_governance_agent_drafts_and_gates_approval(session):
    agent = CRMGovernanceAgent()
    draft = agent.draft_update({"opportunity_id": "OPP-DEMO1", "stage": "Engaging"}, 0.9, ["close_date"])
    assert draft["changes"]["stage"] == "On Hold"  # high risk -> On Hold
    required, reasons = agent.requires_approval(0.9, draft)
    assert required and reasons

    # Low risk, no important-field change -> no approval required.
    clean = agent.draft_update({"opportunity_id": "OPP-DEMO2", "stage": "Engaging"}, 0.0, [])
    assert clean["changes"] == {}
    assert agent.requires_approval(0.0, clean)[0] is False


def test_executive_synthesis_agent_recommends_and_summarizes(session):
    agent = ExecutiveSynthesisAgent()
    actions = agent.recommend_actions(
        [{"type": "high_priority_tickets"}, {"type": "signal"}], ["close_date"], 0.9
    )
    assert any("deal-desk" in a for a in actions)
    summary, name = agent.synthesize({
        "opportunity_id": "OPP-DEMO1", "risk_score": 0.9, "risk_flags": [],
        "missing_fields": ["close_date"], "recommended_actions": actions,
        "crm_update": {"changes": {"stage": "On Hold"}}, "approval_status": "approved",
        "documents_reviewed": 4,
    })
    assert name == "local"
    assert "OPP-DEMO1" in summary
