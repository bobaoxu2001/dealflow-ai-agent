"""Error-handling and idempotency tests for the agent endpoints."""
from app.db.models import CRMWriteback


def _start_pending(client) -> str:
    body = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO1", "task": "high risk"},
    ).json()
    assert body["approval_status"] == "pending"
    return body["task_id"]


def test_unknown_opportunity_returns_404(client):
    resp = client.post("/agent/review-opportunity", json={"opportunity_id": "OPP-NOPE"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_double_approval_is_rejected_and_state_preserved(client, session):
    task_id = _start_pending(client)

    first = client.post(f"/agent/tasks/{task_id}/approve", json={"approver": "mgr"})
    assert first.status_code == 200
    assert first.json()["execution_status"] == "completed"

    # Second approval must not corrupt state.
    second = client.post(f"/agent/tasks/{task_id}/approve", json={"approver": "mgr"})
    assert second.status_code == 400
    assert "not awaiting approval" in second.json()["detail"]

    # Exactly one writeback row exists (no duplicate writeback).
    wbs = session.query(CRMWriteback).filter_by(task_id=task_id).all()
    assert len(wbs) == 1


def test_reject_after_approval_is_blocked(client, session):
    task_id = _start_pending(client)
    assert client.post(f"/agent/tasks/{task_id}/approve").status_code == 200

    resp = client.post(f"/agent/tasks/{task_id}/reject", json={"reason": "too late"})
    assert resp.status_code == 400
    # Writeback from the earlier approval is untouched.
    assert session.query(CRMWriteback).filter_by(task_id=task_id).count() == 1


def test_approve_after_rejection_is_blocked(client, session):
    task_id = _start_pending(client)
    assert client.post(f"/agent/tasks/{task_id}/reject", json={"reason": "no"}).status_code == 200

    resp = client.post(f"/agent/tasks/{task_id}/approve")
    assert resp.status_code == 400
    # Rejected task never produced a writeback.
    assert session.query(CRMWriteback).filter_by(task_id=task_id).count() == 0


def test_low_risk_no_change_produces_no_writeback(client, session):
    body = client.post(
        "/agent/review-opportunity", json={"opportunity_id": "OPP-DEMO2"}
    ).json()
    assert body["execution_status"] == "completed"
    assert session.query(CRMWriteback).filter_by(task_id=body["task_id"]).count() == 0
