# Demo video script (~3–4 minutes)

A tight screen-recording script for a portfolio walkthrough. Honest framing: it
runs locally and in CI; it is **not** deployed to production.

Setup before recording:
```bash
make install
make seed-demo      # zero-infra demo data, no keys
make dev            # http://localhost:8000
```

---

### Scene 1 — Hook + README quick proof (~25s)
- Show the GitHub repo home and the README **Quick proof** bullets.
- Say: "DealFlow is a LangGraph enterprise CRM workflow agent. It reviews a sales
  opportunity over structured CRM data and vector-searched support history, scores
  risk, and pauses for human approval before any CRM write."

### Scene 2 — CI: dual jobs + docker build (~20s)
- Open the **Actions** tab; show the latest run is green with three jobs:
  `tests (sqlite, full offline suite)`, `integration (postgres + pgvector)`,
  `docker build (no deploy)`.
- Say: "CI proves it on a clean machine — offline SQLite suite, a real
  PostgreSQL/pgvector path, and a Docker image build."

### Scene 3 — FastAPI /docs (~20s)
- Open `http://localhost:8000/docs`.
- Point out `/agent/review-opportunity`, `/agent/review-opportunity-async`,
  `/agent/tasks/{id}`, `/agent/tasks/{id}/trace`, approve/reject, `/search/vector`.

### Scene 4 — Review an opportunity (high risk) (~35s)
```bash
curl -s -X POST localhost:8000/agent/review-opportunity \
  -H 'Content-Type: application/json' \
  -d '{"opportunity_id":"OPP-DEMO1","task":"Review this opportunity, identify blockers, summarize client history, and recommend next steps."}' | jq
```
- Call out: `execution_status: pending_approval`, `risk_score`, `risk_flags`,
  `missing_fields`, and `crm_update_draft.changes` — **no writeback yet**.
- Say: "Risk is high and it wants to change an important field, so it stopped for
  a human."

### Scene 5 — Pending approval (~15s)
```bash
curl -s localhost:8000/agent/tasks/<TASK_ID> | jq '{execution_status, approval_status, requires_human_approval}'
```
- Show it is `pending_approval` / `pending`.

### Scene 6 — Trace endpoint (observability) (~25s)
```bash
curl -s localhost:8000/agent/tasks/<TASK_ID>/trace | jq
```
- Point at the ordered node steps, each with `status` and **`duration_ms`**.
- Say: "Every node is audited with timing — this is the agent's observability
  surface, correlated by task_id."

### Scene 7 — Approve → writeback (~25s)
```bash
curl -s -X POST localhost:8000/agent/tasks/<TASK_ID>/approve \
  -H 'Content-Type: application/json' -d '{"approver":"sales_manager"}' | jq
```
- Show `execution_status: completed`, `crm_update_draft.applied`
  (`stage: Engaging → On Hold`), and `final_report.executive_summary`.
- Say: "On approval it resumes, writes back, and records the change — the LLM only
  wrote the summary, never the CRM."

### Scene 8 — Async long-running mode (~15s)
```bash
curl -s -X POST localhost:8000/agent/review-opportunity-async \
  -d '{"opportunity_id":"OPP-DEMO2"}' | jq '{task_id, execution_status}'
curl -s localhost:8000/agent/tasks/<TASK_ID> | jq '.execution_status'
```
- Say: "The async endpoint returns a task id immediately and runs in the
  background — queued → running → completed."

### Scene 9 — Optional HubSpot dry-run adapter (~25s)
- Show `docs/demo/hubspot_dry_run_demo.md`.
- With `CRM_ADAPTER=hubspot` + `HUBSPOT_DRY_RUN=true`, run the dry-run snippet and
  show the result: `status: dry_run`, mapped `proposed` properties, **no PATCH**.
- Say: "It's integration-ready with a real CRM API — dry-run by default, strict
  field allowlist, human approval still required, and CI never calls it."

### Scene 10 — Close (~10s)
- Back to README **Engineering focus** section.
- Say: "Stateful LangGraph orchestration, role-based agents, human approval,
  external CRM integration, structured + vector data, audit/trace/evaluation, and
  dual + docker CI — built like production, honest that it isn't deployed."
