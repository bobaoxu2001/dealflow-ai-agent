"""Tests for the agent execution-trace observability endpoint."""


def test_trace_returns_ordered_node_steps(client):
    body = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO2", "task": "trace check"},
    ).json()
    task_id = body["task_id"]

    resp = client.get(f"/agent/tasks/{task_id}/trace")
    assert resp.status_code == 200
    trace = resp.json()

    assert trace["task_id"] == task_id
    assert trace["step_count"] >= 5
    nodes = [s["node_name"] for s in trace["trace"]]
    # First node is always parse_task; steps are numbered in order.
    assert nodes[0] == "parse_task"
    assert [s["step"] for s in trace["trace"]] == list(range(1, len(nodes) + 1))
    assert {"retrieve_crm_context", "analyze_risks", "finalize_report"} <= set(nodes)


def test_trace_includes_timing_metadata(client):
    body = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO2", "task": "timing check"},
    ).json()
    trace = client.get(f"/agent/tasks/{body['task_id']}/trace").json()

    # Instrumentation attaches duration_ms (and status) to every node step.
    assert all("duration_ms" in s for s in trace["trace"])
    assert all(s["duration_ms"] is not None and s["duration_ms"] >= 0 for s in trace["trace"])
    assert all(s["status"] for s in trace["trace"])


def test_trace_for_unknown_task_is_404(client):
    resp = client.get("/agent/tasks/TASK-does-not-exist/trace")
    assert resp.status_code == 404
