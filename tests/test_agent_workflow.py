"""Tests for the LangGraph agent happy path (low-risk, no approval needed)."""
from app.db.models import AgentAuditLog


def test_low_risk_opportunity_completes_without_approval(client):
    resp = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO2", "task": "Review and recommend next steps."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution_status"] == "completed"
    assert body["requires_human_approval"] is False
    assert body["approval_status"] in {"not_required", "approved"}
    assert body["final_report"]
    assert isinstance(body["recommended_actions"], list)


def test_review_writes_node_level_audit_logs(client, session):
    resp = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO2", "task": "Audit log check."},
    )
    task_id = resp.json()["task_id"]
    logs = session.query(AgentAuditLog).filter_by(task_id=task_id).all()
    node_names = {log.node_name for log in logs}
    assert {"parse_task", "retrieve_crm_context", "analyze_risks", "finalize_report"} <= node_names


def test_unknown_opportunity_returns_404(client):
    resp = client.post("/agent/review-opportunity", json={"opportunity_id": "NOPE"})
    assert resp.status_code == 404
