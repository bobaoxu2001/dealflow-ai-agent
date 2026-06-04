# DealFlow AI Agent — Technical Walkthrough

A deeper walkthrough of the architecture, workflow, and design decisions. Honest
framing: this runs locally and in CI; it is not deployed to production.

---

## Overview

DealFlow AI Agent is a LangGraph-powered enterprise CRM workflow agent. Given a
sales opportunity, it reviews the structured CRM record, retrieves the customer's
unstructured support history through vector search, scores deal risk, detects
missing CRM fields, recommends next steps, and drafts a CRM update. When the
change is high-risk it **pauses for human approval before writing back** — and
every node is persisted and audited. It is stateful multi-step agent
orchestration with tool routing and human-in-the-loop control, not a single
chatbot response.

---

## Execution flow

1. **Input.** `POST /agent/review-opportunity` with an `opportunity_id` and a
   natural-language task. A `task_id` is created and persisted immediately.
2. **LangGraph runs a 10-node workflow** over a typed `AgentState`:
   `parse_task → retrieve_crm_context → retrieve_vector_context → analyze_risks →
   detect_missing_fields → recommend_next_steps → draft_crm_update →
   approval_router → (writeback_crm) → finalize_report`.
3. **Structured retrieval.** `retrieve_crm_context` reads the opportunity,
   account, contacts, and a ticket summary from PostgreSQL (SQLite locally).
4. **Unstructured retrieval.** `retrieve_vector_context` embeds the task and runs
   cosine similarity over `vector_documents` (pgvector on Postgres, Python
   fallback on SQLite) scoped to the account.
5. **Reasoning.** `analyze_risks` scores risk from real signals (open/high-
   priority tickets, refund/cancel mentions in retrieved docs);
   `detect_missing_fields` flags blank CRM fields; `recommend_next_steps` and
   `draft_crm_update` produce actions and a proposed change.
6. **Routing.** `approval_router` is a conditional edge: if risk ≥ threshold
   **or** the draft modifies an important field (`stage`, `deal_value`,
   `close_date`), the graph stops with `execution_status = pending_approval`.
   Otherwise it continues straight to writeback.
7. **Human-in-the-loop.** `POST /agent/tasks/{id}/approve` resumes the workflow
   (writeback + finalize); `/reject` marks it rejected and writes nothing.
8. **Persistence/audit.** Full agent state is saved on `agent_tasks`; every node
   writes an `agent_audit_logs` row; applied changes are recorded in
   `crm_writebacks`.

**Live example (real Kaggle data):** opportunity `OM8LELJW` (account `ACC-0039` /
*Iselectrics*, stage `Engaging`) scored **risk 0.9**, went **pending_approval**,
and on approval applied `stage: Engaging → On Hold` with a writeback record.

---

## Architecture explanation

```
Client / curl
   │  REST (FastAPI)
   ▼
FastAPI routes ──► Services layer ──► PostgreSQL + pgvector
 (health,            (CRM, vector search,    (structured CRM tables +
  search,             embeddings, tasks,      vector_documents,
  agent)              approval)               agent_tasks, audit logs,
   │                                          crm_writebacks)
   ▼
LangGraph agent (StateGraph) ──► Tools (crm_read, vector_search,
   nodes + conditional routing       risk_scoring, missing_field_checker,
                                      crm_writeback, audit_log)
```

- **FastAPI** is the API boundary; thin routes delegate to a **services layer**.
- **Services** encapsulate all data access (CRM reads/writes, vector search,
  embeddings, task/approval lifecycle) so the agent and the HTTP layer share the
  same logic.
- **LangGraph** owns orchestration: a `StateGraph` over a `TypedDict` state with
  conditional edges. Node internals are deterministic by default (rule-based
  risk + templated drafting), with an optional LLM hook — so the whole thing runs
  with **no API keys**.
- **PostgreSQL + pgvector** is the single store for both structured and vector
  data. A portable column type lets the exact same models/tests run on SQLite.

## LangGraph workflow explanation

- State is a `TypedDict` (`AgentState`) threaded through every node; merges are
  last-write-wins, and `audit_log` is accumulated explicitly (read → append →
  return) so the data flow stays readable.
- The graph has one conditional edge at `approval_router`:
  - `pending` → END (stop, await human)
  - otherwise → `writeback_crm → finalize_report → END`
- **Resume design:** rather than relying on an in-memory checkpointer, the full
  state snapshot is persisted to `agent_tasks`. Approve/reject rebuilds state
  from the DB and runs the remaining nodes. This makes the workflow
  **restart-safe** (survives an API restart) and portable across SQLite/Postgres.
  A LangGraph Postgres checkpointer is noted as a future alternative.

## Data source explanation

Two public Kaggle datasets simulate an enterprise environment:

1. `nilkamalsaha/crm-sales-opportunities-on-google-sheets` — structured CRM
   (accounts, opportunities, products, sales teams).
2. `suraj520/customer-support-ticket-dataset` — unstructured support tickets.

`scripts/` downloads, inspects, transforms, generates a synthetic workflow layer,
and loads everything. Verified raw/loaded counts: 85 accounts, 8,800
opportunities, 8,469 tickets → 8,469 client notes + 4,729 risk notes → 24,521
embedded vector documents.

## Real data vs. synthetic linking explanation

The two datasets **share no native join key** (CRM keys accounts by *name*; the
support dataset has no account id). So:

- The underlying CRM and support **rows are the real Kaggle data**.
- A **deterministic, seeded** layer adds the scaffolding a real system would have:
  surrogate `account_id`s, a reproducible `ticket → account → opportunity`
  mapping (hash of `ticket_id`), plus synthetic meeting notes, missing-field
  blanks, and approval/writeback seeds. Synthetic rows are flagged
  `is_synthetic=true`.
- This is documented openly in the README rather than hidden — the goal is an
  honest enterprise *simulation*, not fabricated data.

## PostgreSQL / pgvector explanation

- Structured CRM tables and the `vector_documents` table live in the same
  Postgres instance; the pgvector extension stores embeddings and supports cosine
  distance (`<=>`) for similarity search.
- A custom portable column type uses the native `Vector` type on Postgres and a
  JSON-encoded fallback on SQLite, with similarity computed in Python — so local
  dev and CI need zero infrastructure while the Docker path exercises real
  pgvector.
- `docker-compose.yml` brings up the API + a pgvector-enabled Postgres;
  `init_db` enables the extension and creates tables.

## Human approval explanation

- Approval is triggered by an explicit, auditable rule: high risk score **or** a
  draft that edits an important field.
- On trigger, the agent **does not write back** — it persists `pending_approval`
  and returns, leaving the CRM untouched.
- A human calls `/approve` (resume → writeback → finalize) or `/reject` (no
  writeback). Both outcomes are recorded in the audit log; applied changes get a
  `crm_writebacks` row with `applied_by`. This is the "safeguard before automated
  writes" story enterprises care about.

---

## Design decisions and trade-offs

**LangGraph vs. a plain function chain**
The workflow is a stateful graph with conditional branching and a human pause
point. LangGraph provides first-class state, explicit nodes/edges, and clean
conditional routing, which keeps the control flow auditable and testable —
preferable to an opaque ReAct loop for an enterprise approval workflow.

**Deterministic nodes with an optional LLM**
The orchestration, retrieval, and routing are the engineering substance and are
fully real. Node internals use deterministic heuristics by default so the project
runs without API keys and tests are reproducible, while each node has an LLM hook.
The architecture is what transfers to a real LLM-backed deployment; no LLM
dependency is faked.

**Restart-safe human-in-the-loop resume**
The full agent state snapshot is persisted to `agent_tasks`, not just an
in-memory checkpointer. Approve/reject rebuilds state from the DB and runs the
remaining nodes, so a pending task survives a process restart. A LangGraph
Postgres checkpointer is a natural future swap.

**Vector search and why pgvector**
Unstructured text (ticket descriptions/resolutions, client/risk/meeting notes) is
embedded into `vector_documents`. On Postgres the pgvector cosine-distance
operator is used; on SQLite the same JSON-stored vectors are ranked with Python
cosine. Keeping vectors next to the CRM data avoids a second datastore and allows
filtering by account/opportunity in the same query.

**Local hashing embedder (a deliberate limitation)**
The default `LocalEmbeddingProvider` is a deterministic hashing embedder so the
demo needs no API key. It sits behind an `EmbeddingProvider` interface, so
switching to a hosted model is a one-line config change; a real model would be
used in production. The abstraction is the point.

**Explicit approval policy**
Approval is an explicit rule in `approval_router`: risk ≥ a configurable
threshold, or the draft modifies a configured important field (`stage`,
`deal_value`, `close_date`). The policy is transparent and configurable rather
than model-driven, which matters for trust and audit.

**Datasets without a shared key**
The two datasets share no key, so the project uses a deterministic, seeded linking
layer that is documented openly. Real rows stay real; only the join and workflow
scaffolding are synthetic and flagged `is_synthetic`, rather than pretending the
data natively connects.

**Testing strategy**
`pytest` covers health, data transformation, model creation, vector insertion +
retrieval, the agent happy path, the approval-required path, the rejection path,
LLM synthesis fallback, the trace endpoint, idempotent error handling, and the
evaluation helpers. The full offline suite runs on SQLite with the local embedder
(no services/keys); a separate set of pgvector integration tests runs against
PostgreSQL in CI.

**Scaling considerations**
Move embeddings to a hosted model, switch to the Postgres checkpointer, add
pgvector indexes (IVFFlat/HNSW) for large corpora, put nodes behind a task queue
for true long-running execution, add authn/z and rate limiting, and add tracing
(LangSmith/OpenTelemetry). None of this is claimed to be deployed.

**Hardest part / what to change**
Running one codebase on both zero-infra SQLite (for CI/tests) and Postgres+pgvector
(for the real path) without forking logic — solved with a portable vector column
and a backend-aware search service. A rebuild would start from the LangGraph
Postgres checkpointer to make resume even more native.

---

## Recent improvements

A production-readiness pass on top of the working prototype:

- **Optional LLM final-synthesis layer** behind a provider abstraction
  (`app/services/llm_service.py`). Deterministic local summary by default; a
  hosted model if a key is set. The LLM only narrates the already-computed report.
- **PostgreSQL + pgvector CI job** (`pgvector/pgvector:pg16` service container)
  that verifies the native `<=>` operator — separate from the SQLite full-suite job.
- **Evaluation harness** (`scripts/evaluate_agent.py`, `docs/evaluation.md`):
  deterministic checks on retrieval, risk scoring, approval routing, and pipeline integrity.
- **`GET /agent/tasks/{id}/trace`** observability endpoint (ordered node trace).
- **Hardened error handling / idempotency** for approve/reject, with tests.
- **Long-running async mode:** `POST /agent/review-opportunity-async` creates a
  task, returns immediately, and runs the workflow in a background runner with
  persisted status transitions (`queued → running → completed/pending_approval/error`).
  The synchronous endpoint is unchanged.
- **Role-based multi-agent layer:** four bounded roles (`CustomerContextAgent`,
  `DealAnalysisAgent`, `CRMGovernanceAgent`, `ExecutiveSynthesisAgent`) wrap the
  deterministic tools; LangGraph supervises. See [`multi_agent_design.md`](multi_agent_design.md).
- **Node instrumentation:** a wrapper captures `duration_ms` + status per node,
  surfaced via the `/trace` endpoint.
- **Docker-build CI job:** validates the image builds (no deploy) — three CI jobs total.
- **Demo assets** (`docs/demo/`) and `docs/productionization.md` + `docs/project_review.md`.

## Optional LLM synthesis design

The agent's decisions are deterministic and auditable — risk scoring, approval
routing, and writeback are rules, not model output. The LLM sits at the very end
and only turns the structured report into a readable executive summary; it is
architecturally prevented from triggering a writeback or skipping approval.
Because it sits behind a provider interface with a deterministic fallback, the
whole suite runs with no API key.

## SQLite and PostgreSQL CI strategy

Two CI jobs. The SQLite job runs the full offline suite fast, with zero
infrastructure — logic, agent, and approval tests live there. The PostgreSQL job
spins up a `pgvector/pgvector:pg16` container and runs integration tests that
exercise the real pgvector path (extension enabled, native cosine-distance search,
agent state persisted in Postgres). One codebase, two backends, verified by CI
rather than asserted.

## Async execution design

The sync endpoint runs the graph inline and returns the final state. The async
endpoint creates the task, returns a `task_id` immediately, and runs the same
graph in a background runner that opens its own DB session so it survives request
teardown. Status is persisted at each transition, and clients poll
`/agent/tasks/{id}` or `/trace`. It is a deliberately lightweight in-process
runner; in production the same task would sit behind a queue/worker and the
LangGraph Postgres checkpointer, which the code is already shaped for.

## Role-based agent coordination design

The design is role-based, not autonomous. Each role owns one responsibility and
wraps pre-approved tools; LangGraph is the supervisor that orders them and owns
routing, including the human-approval pause. This gives the separation-of-concerns
benefit of multi-agent systems while staying deterministic, testable, and
auditable — and only the synthesis role can touch the LLM, which still cannot
write to the CRM. The trade-off vs. free-form ReAct agents is intentional:
bounded roles are chosen because enterprise CRM writes need predictability and an
audit trail.

## Production readiness

Not production-ready, and stated explicitly throughout: it runs locally and in CI
and is not deployed. What *is* production-style: durable restart-safe state,
node-level audit logs and a trace endpoint, idempotent approval handling, a hard
guardrail that the LLM cannot write to the CRM, and a native pgvector path tested
in CI. What is missing for production is captured in `docs/productionization.md`:
an async worker/queue, the LangGraph Postgres checkpointer, real embedding/LLM
providers, OpenTelemetry/LangSmith tracing, and auth/multi-tenancy.

## Future improvements

In priority order: move execution to a durable queue/worker and adopt the
LangGraph Postgres checkpointer for native interrupt/resume; swap in a real
embedding model and a pgvector ANN index; add OpenTelemetry/LangSmith tracing
keyed by `task_id`; then auth, multi-tenancy, and a labeled evaluation set to
measure decision accuracy rather than just behavior.
