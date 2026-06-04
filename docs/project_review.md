# Project self-review scorecard

A candid self-assessment, written the way I'd discuss it with a senior reviewer.

## Scorecard

| Dimension | Score | Notes |
|---|---|---|
| Agent orchestration (LangGraph) | 🟢 Strong | Real `StateGraph`, typed state, conditional routing, durable human-in-the-loop resume. |
| Tool routing & separation | 🟢 Strong | Distinct tools (crm/vector/risk/approval/audit); thin nodes call a clean services layer. |
| Structured + unstructured data | 🟢 Strong | PostgreSQL CRM tables + pgvector retrieval over support/notes. |
| Human-in-the-loop safety | 🟢 Strong | Explicit, configurable approval rule; LLM cannot bypass it or write CRM. |
| Observability / audit | 🟢 Strong | Node-level audit logs + `/trace` endpoint, correlated by `task_id`. |
| Testing | 🟢 Strong | Full offline suite (SQLite) + native pgvector integration job in CI. |
| Evaluation | 🟡 Adequate | Deterministic sanity/regression checks, not a labeled benchmark. |
| LLM usage | 🟡 Deliberate | Deterministic by default; optional LLM only for final narrative synthesis. |
| Productionization | 🟡 Documented | Retry/queue/checkpointer/OTel designed and documented, not built. |
| Deployment | 🔴 Out of scope | Not deployed; runs locally + CI. Stated honestly throughout. |

## What is strong

- The orchestration is genuine LangGraph, not a prompt-chain pretending to be an
  agent. State, routing, and the approval pause/resume are the substance.
- It integrates **both** data shapes (structured CRM + vector retrieval) in one
  store and uses both inside the agent's reasoning.
- It is honest and reproducible: deterministic logic, key-free local mode, real
  Kaggle data verified end-to-end, and clearly-labeled synthetic linking.

## What is limited

- The default risk/draft logic is heuristic, not learned. (Intentional, for
  testability — but it's a heuristic.)
- The local hashing embedder limits semantic ranking quality.
- Evaluation validates behavior/plumbing, not ground-truth decision accuracy
  (the datasets have no agent-decision labels).
- No deployment, auth, or async worker yet.

## What was improved in v2

- Optional LLM final-synthesis layer behind a provider abstraction (deterministic
  fallback, no key needed for tests).
- Dedicated **PostgreSQL + pgvector CI job** verifying the native `<=>` path.
- **Evaluation** harness + docs.
- **`/agent/tasks/{id}/trace`** observability endpoint.
- Hardened **error handling / idempotency** for approval/rejection, with tests.
- Demo assets (commands, sample JSON responses) and interview/productionization docs.

## What I'd productionize next

In priority order: async worker + LangGraph Postgres checkpointer → real
embedding/LLM providers + pgvector ANN index → OpenTelemetry/LangSmith tracing →
auth, multi-tenancy, and a labeled evaluation set. Details in
[`productionization.md`](productionization.md).
