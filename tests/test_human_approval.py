"""Tests for the human-in-the-loop approval and rejection paths."""
from app.db.models import CRMWriteback, Opportunity


def _start_high_risk_review(client) -> dict:
    resp = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO1", "task": "Review high-risk deal."},
    )
    assert resp.status_code == 200
    return resp.json()


def test_high_risk_requires_approval_and_pauses(client):
    body = _start_high_risk_review(client)
    assert body["requires_human_approval"] is True
    assert body["approval_status"] == "pending"
    assert body["execution_status"] == "pending_approval"
    assert body["risk_score"] >= 0.6
    # No writeback should have happened yet.
    assert "applied" not in body["crm_update_draft"]


def test_approval_resumes_and_writes_back(client, session):
    body = _start_high_risk_review(client)
    task_id = body["task_id"]

    resp = client.post(f"/agent/tasks/{task_id}/approve", json={"approver": "manager"})
    assert resp.status_code == 200
    final = resp.json()
    assert final["execution_status"] == "completed"
    assert final["approval_status"] == "approved"

    wb = session.query(CRMWriteback).filter_by(task_id=task_id).all()
    assert wb, "expected a CRM writeback row after approval"
    # The opportunity should reflect the applied change.
    opp = session.query(Opportunity).filter_by(opportunity_id="OPP-DEMO1").one()
    assert opp.stage is not None


def test_rejection_blocks_writeback(client, session):
    body = _start_high_risk_review(client)
    task_id = body["task_id"]

    resp = client.post(
        f"/agent/tasks/{task_id}/reject", json={"approver": "manager", "reason": "needs more info"}
    )
    assert resp.status_code == 200
    final = resp.json()
    assert final["execution_status"] == "rejected"
    assert final["approval_status"] == "rejected"

    wb = session.query(CRMWriteback).filter_by(task_id=task_id).all()
    assert not wb, "no writeback should occur on rejection"


def test_cannot_approve_non_pending_task(client):
    # OPP-DEMO2 completes without approval -> approving it is a 400.
    started = client.post(
        "/agent/review-opportunity", json={"opportunity_id": "OPP-DEMO2"}
    ).json()
    resp = client.post(f"/agent/tasks/{started['task_id']}/approve")
    assert resp.status_code == 400


def test_get_task_status(client):
    body = _start_high_risk_review(client)
    resp = client.get(f"/agent/tasks/{body['task_id']}")
    assert resp.status_code == 200
    assert resp.json()["task_id"] == body["task_id"]
