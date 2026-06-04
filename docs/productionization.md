# Productionization notes

This is an honest map of what would change to run DealFlow AI Agent in
production. It is **not** currently deployed; the project runs locally and in CI.
Several reliability behaviors are already implemented; the rest is documented as
the intended design.

## Already implemented

- **Durable state + restart-safe resume.** Full agent state is persisted to
  `agent_tasks.state`; a pending task survives an API restart and resumes on
  approval (no in-memory checkpointer required).
- **Node-level audit logs** (`agent_audit_logs`) with **per-node timing
  instrumentation** (`duration_ms`) and a `GET /agent/tasks/{id}/trace`
  observability endpoint.
- **Long-running async mode.** `POST /agent/review-opportunity-async` returns a
  `task_id` immediately and runs in a background runner (own DB session) with
  persisted status transitions (`queued → running → completed/pending_approval/error`).
- **Role-based multi-agent layer** supervised by LangGraph (bounded roles, not
  free-form autonomous agents).
- **Idempotent approval lifecycle.** Approving/rejecting a non-pending task is a
  clean 400 and never double-writes or corrupts state (verified in
  `tests/test_error_handling.py`).
- **Deterministic guardrail.** The LLM can summarize but can never trigger a CRM
  writeback or bypass human approval.
- **Optional external CRM integration** (HubSpot adapter) with dry-run default and
  a strict writeback allowlist.
- **Two-path persistence** (SQLite for zero-infra dev/CI; PostgreSQL + pgvector
  for the native path) with dedicated pgvector and Docker-build CI jobs.

## Intended for production (not yet built)

### Retry & timeout model
- **Node-level retries** with exponential backoff for transient failures
  (DB blips, embedding/LLM provider timeouts). Each node is already a pure
  `state -> partial state` function, so wrapping with a retry decorator is
  localized.
- **Per-node timeouts** so a slow external call can't hang the workflow; on
  timeout the node records an `error` audit entry and the task moves to a
  recoverable `error` state.
- **Idempotency keys** on writeback (a deterministic `writeback_id` per
  task+change set) so a retried writeback cannot double-apply.

### Long-running execution
- The async endpoint already returns a `task_id` immediately and runs in a
  lightweight in-process background runner. For production, move that same job
  behind a durable **task queue / worker** (Celery, RQ, or Arq) so work survives
  process restarts and scales horizontally.
- Swap our hand-rolled persistence for the **LangGraph Postgres checkpointer**
  to get native interrupt/resume and time-travel debugging.

### Observability
- **OpenTelemetry** spans per node + **LangSmith** tracing for the LLM path,
  correlated by `task_id` (already the correlation key in every audit row).
- Structured JSON logs shipped to a log aggregator; metrics on risk-score
  distribution, approval rate, and writeback latency.

### Security & multi-tenancy
- AuthN/Z on all endpoints, per-tenant data isolation, rate limiting, and an
  approver-identity/role check (currently the approver is a free-text field).
- Secrets via a manager (not env files); audit logs as append-only.

### Data & retrieval
- Real embedding model + **pgvector ANN index** (IVFFlat/HNSW) for large corpora.
- Incremental ingestion + re-embedding pipeline instead of full reload.
