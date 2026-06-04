"""Tests for the async (long-running) review endpoint.

Note: Starlette runs BackgroundTasks before the TestClient call returns, so by
the time we poll GET the background job has already finished — which makes these
tests deterministic while still exercising the queued -> terminal transition.
"""


def test_async_returns_task_id_immediately(client):
    resp = client.post(
        "/agent/review-opportunity-async",
        json={"opportunity_id": "OPP-DEMO2", "task": "async happy path"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"]
    # The response is produced before the background job mutates status.
    assert body["execution_status"] == "queued"


def test_async_task_reaches_terminal_state(client):
    body = client.post(
        "/agent/review-opportunity-async",
        json={"opportunity_id": "OPP-DEMO1", "task": "async high risk"},
    ).json()
    task_id = body["task_id"]

    status = client.get(f"/agent/tasks/{task_id}").json()
    assert status["execution_status"] in {"completed", "pending_approval"}


def test_async_low_risk_completes(client):
    body = client.post(
        "/agent/review-opportunity-async", json={"opportunity_id": "OPP-DEMO2"}
    ).json()
    final = client.get(f"/agent/tasks/{body['task_id']}").json()
    assert final["execution_status"] == "completed"


def test_async_unknown_opportunity_goes_to_error(client):
    body = client.post(
        "/agent/review-opportunity-async", json={"opportunity_id": "OPP-NOPE"}
    ).json()
    task_id = body["task_id"]

    final = client.get(f"/agent/tasks/{task_id}").json()
    assert final["execution_status"] == "error"
    assert final["error"] and "not found" in final["error"].lower()
