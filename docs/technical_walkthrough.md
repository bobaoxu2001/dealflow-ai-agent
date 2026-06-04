# DealFlow AI Agent — Technical Walkthrough

A deeper walkthrough of the architecture, workflow, and design decisions, with a
short speaking guide for demoing the project. Honest framing: this runs locally
and in CI; it is not deployed to production.

---

## 30-second pitch

> DealFlow AI Agent is a LangGraph-powered enterprise CRM workflow agent. You
> hand it a sales opportunity, and it reviews the structured CRM record,
> retrieves the customer's unstructured support history through vector search,
> scores deal risk, detects missing CRM fields, recommends next steps, and
> drafts a CRM update. When the change is high-risk it **pauses for human
> approval before writing back** — and every node is persisted and audited. It
> demonstrates stateful multi-step agent orchestration, tool routing, and
> human-in-the-loop control, not just a chatbot response.

---

## 2-minute technical walkthrough

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

## 10 likely interviewer questions & answers

**1. Why LangGraph instead of a plain function chain or a ReAct agent?**
The workflow is a stateful graph with conditional branching and a human pause
point. LangGraph gives first-class state, explicit nodes/edges, and clean
conditional routing, which makes the control flow auditable and testable —
better than an opaque ReAct loop for an enterprise approval workflow.

**2. The nodes are mostly deterministic — is this really "AI"?**
The orchestration, retrieval, and routing are the engineering substance, and
they're real. Node internals use deterministic heuristics by default so the
project runs without API keys and tests are reproducible, but each node has an
LLM hook. I deliberately didn't fake an LLM dependency to look impressive — the
architecture is what transfers to a real LLM-backed deployment.

**3. How does human-in-the-loop resume survive an API restart?**
I persist the full agent state snapshot to `agent_tasks`, not just an in-memory
checkpointer. Approve/reject rebuilds state from the DB and runs the remaining
nodes, so a pending task survives a process restart. A LangGraph Postgres
checkpointer is a natural future swap.

**4. How does vector search work, and why pgvector?**
Unstructured text (ticket descriptions/resolutions, client/risk/meeting notes)
is embedded into `vector_documents`. On Postgres I use pgvector's cosine-distance
operator; on SQLite I fall back to Python cosine over the same JSON-stored
vectors. Keeping vectors next to the CRM data avoids a second datastore and lets
me filter by account/opportunity in the same query.

**5. The embeddings are a hash-based local provider — limitation?**
Yes — the default `LocalEmbeddingProvider` is a deterministic hashing embedder so
the demo needs no API key. It's behind an `EmbeddingProvider` interface, so
switching to OpenAI (or any model) is a one-line config change. I'd use a real
model in production; the abstraction is the point.

**6. How do you decide what needs approval?**
An explicit rule in `approval_router`: risk ≥ configurable threshold, or the
draft modifies a configured important field (`stage`, `deal_value`,
`close_date`). It's transparent and configurable rather than an LLM "vibe", which
matters for trust and audit.

**7. The two datasets don't join — how did you handle that honestly?**
They share no key, so I built a deterministic, seeded linking layer and
documented it. Real rows stay real; only the join and workflow scaffolding are
synthetic and flagged `is_synthetic`. I call this out in the README rather than
pretending the data natively connects.

**8. How is it tested, and what do the tests cover?**
`pytest` covers health, data transformation, model creation, vector insertion +
retrieval, the agent happy path, the approval-required path, the rejection path,
LLM synthesis fallback, the trace endpoint, idempotent error handling, and the
evaluation helpers — 37 tests total. The full offline suite runs on SQLite with
the local embedder (no services/keys); a separate set of 5 pgvector integration
tests runs against PostgreSQL in CI.

**9. How would you scale or productionize this?**
Move embeddings to a hosted model, switch to the Postgres checkpointer, add
pgvector indexes (IVFFlat/HNSW) for large corpora, put nodes behind a task queue
for true long-running execution, add authn/z and rate limiting, and add tracing
(LangSmith/OpenTelemetry). I intentionally don't claim any of this is deployed.

**10. What was the hardest part / what would you change?**
Making one codebase run both on zero-infra SQLite (for CI/tests) and on
Postgres+pgvector (for the real path) without forking logic — solved with a
portable vector column and a backend-aware search service. If I rebuilt it, I'd
start with the LangGraph Postgres checkpointer to make resume even more native.

---

## What changed in v2

A production-readiness pass on top of the working prototype:

- **Optional LLM final-synthesis layer** behind a provider abstraction
  (`app/services/llm_service.py`). Deterministic local summary by default; OpenAI
  if a key is set. The LLM only narrates the already-computed report.
- **PostgreSQL + pgvector CI job** (`pgvector/pgvector:pg16` service container)
  that verifies the native `<=>` operator — separate from the SQLite full-suite job.
- **Evaluation harness** (`scripts/evaluate_agent.py`, `docs/evaluation.md`):
  deterministic checks on retrieval, risk scoring, approval routing, and pipeline integrity.
- **`GET /agent/tasks/{id}/trace`** observability endpoint (ordered node trace).
- **Hardened error handling / idempotency** for approve/reject, with tests.
- **Demo assets** (`docs/demo/`) and `docs/productionization.md` + `docs/project_review.md`.

## How to explain the optional LLM synthesis

"The agent's decisions are deterministic and auditable — risk scoring, approval
routing, and writeback are rules, not model output. The LLM sits at the very end
and only turns the structured report into a readable executive summary. It is
architecturally prevented from triggering a writeback or skipping approval. That
gives me LLM polish without sacrificing testability or safety — and because it's
behind a provider interface with a deterministic fallback, the whole suite runs
with no API key."

## How to explain Postgres CI vs SQLite CI

"Two CI jobs. The SQLite job runs the full offline suite fast, with zero
infrastructure — that's where logic, agent, and approval tests live. The Postgres
job spins up a `pgvector/pgvector:pg16` container and runs integration tests that
exercise the real pgvector path (extension enabled, native cosine-distance
search, agent state persisted in Postgres). One codebase, two backends, proven by
CI rather than claimed."

## "Is this production-ready?"

"No — and I'm explicit about that everywhere. It runs locally and in CI; it's not
deployed. What *is* production-style: durable restart-safe state, node-level audit
logs and a trace endpoint, idempotent approval handling, a hard guardrail that the
LLM can't write to the CRM, and a native pgvector path tested in CI. What's
missing for production is in `docs/productionization.md`: an async worker, the
LangGraph Postgres checkpointer, real embedding/LLM providers, OpenTelemetry/
LangSmith tracing, and auth/multi-tenancy."

## "What would you do next?"

"In order: move execution to an async worker and adopt the LangGraph Postgres
checkpointer for native interrupt/resume; swap in a real embedding model + a
pgvector ANN index; add OpenTelemetry/LangSmith tracing keyed by task_id; then
auth, multi-tenancy, and a labeled evaluation set to measure decision accuracy
rather than just behavior."

---

## What changed in v3

- **Long-running async mode:** `POST /agent/review-opportunity-async` creates a
  task, returns immediately, and runs the workflow in a background runner with
  persisted status transitions (`queued → running → completed/pending_approval/error`).
  The synchronous endpoint is unchanged.
- **Role-based multi-agent layer:** four bounded roles
  (`CustomerContextAgent`, `DealAnalysisAgent`, `CRMGovernanceAgent`,
  `ExecutiveSynthesisAgent`) wrap the deterministic tools; LangGraph supervises.
  See [`multi_agent_design.md`](multi_agent_design.md).
- **Node instrumentation:** a wrapper captures `duration_ms` + status per node,
  surfaced via the `/trace` endpoint.
- **Docker-build CI job:** validates the image builds (no deploy) — now three CI jobs.

## How to explain the async / long-running design

"The sync endpoint runs the graph inline and returns the final state. The async
endpoint creates the task, returns a `task_id` immediately, and runs the same
graph in a background runner that opens its own DB session so it survives request
teardown. Status is persisted at each transition, and the client polls
`/agent/tasks/{id}` or `/trace`. It's deliberately a lightweight local runner —
in production I'd put the same task behind a queue/worker and the LangGraph
Postgres checkpointer, which the code is already shaped for."

## How to explain "multi-agent" without overclaiming

"It's role-based, not autonomous. Each role owns one responsibility and wraps
pre-approved tools; LangGraph is the supervisor that orders them and owns
routing, including the human-approval pause. That gives the separation-of-concerns
benefit of multi-agent systems while staying deterministic, testable, and
auditable — and only the synthesis role can touch the LLM, which still can't write
to the CRM. I can speak to the trade-off vs. free-form ReAct agents: I chose
bounded roles because enterprise CRM writes need predictability and an audit
trail."
