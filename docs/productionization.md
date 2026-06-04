# Productionization notes

This is an honest map of what would change to run DealFlow AI Agent in
production. It is **not** currently deployed; the project runs locally and in CI.
Several reliability behaviors are already implemented; the rest is documented as
the intended design.

## Already implemented

- **Durable state + restart-safe resume.** Full agent state is persisted to
  `agent_tasks.state`; a pending task survives an API restart and resumes on
  approval (no in-memory checkpointer required).
- **Node-level audit logs** (`agent_audit_logs`) with a `GET /agent/tasks/{id}/trace`
  observability endpoint.
- **Idempotent approval lifecycle.** Approving/rejecting a non-pending task is a
  clean 400 and never double-writes or corrupts state (verified in
  `tests/test_error_handling.py`).
- **Deterministic guardrail.** The LLM can summarize but can never trigger a CRM
  writeback or bypass human approval.
- **Two-path persistence** (SQLite for zero-infra dev/CI; PostgreSQL + pgvector
  for the native path) with a dedicated pgvector CI job.

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
- Move review execution behind a **task queue / worker** (Celery, RQ, or Arq) so
  the HTTP request returns a `task_id` immediately and the graph runs async — the
  API already models this (review returns a task; approval resumes it).
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
