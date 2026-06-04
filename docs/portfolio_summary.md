# DealFlow AI Agent — Portfolio Summary

Copy-paste-ready material for resumes, LinkedIn, and job applications. Honest
framing: a portfolio project that runs locally and in CI (not production-deployed).

---

## Resume bullets

**DealFlow AI Agent — LangGraph Enterprise CRM Workflow Automation**

- Built a production-style AI agent system that automates long-running CRM
  opportunity-review workflows across structured sales data and unstructured
  customer-support history from two public Kaggle datasets (8,800 opportunities,
  8,469 tickets, 24,521 embedded documents).
- Designed a LangGraph orchestration with a 10-node stateful workflow, dynamic
  tool routing, human-in-the-loop approval, and CRM-writeback safeguards.
- Implemented a PostgreSQL + pgvector retrieval layer combining structured CRM
  records with embedded support tickets, client/risk notes, and meeting notes,
  behind a swappable embedding-provider abstraction.
- Engineered restart-safe state persistence, node-level audit logs, and a
  `/trace` observability endpoint; added an optional LLM final-synthesis layer
  (deterministic fallback) that is architecturally barred from triggering CRM writes.
- Containerized the FastAPI service with Docker Compose (API + pgvector Postgres)
  and built dual GitHub Actions CI: a full offline SQLite suite plus a native
  PostgreSQL + pgvector integration job; added a deterministic evaluation harness.

**Condensed (3-bullet) version**

- Built a LangGraph enterprise CRM agent: stateful 10-node workflow with tool
  routing, human-in-the-loop approval, and audited CRM writeback over FastAPI +
  PostgreSQL/pgvector.
- Combined structured CRM data with vector retrieval over 24,521 embedded
  support/notes documents (8,800 opportunities, 8,469 tickets from public Kaggle
  data + a documented synthetic linking layer).
- Shipped dual CI (full offline SQLite suite + native pgvector integration job),
  an evaluation harness, and a trace endpoint; runs fully offline with no LLM/API
  keys via deterministic fallbacks (production-style prototype, not deployed).

---

## LinkedIn post

> 🚀 New project: **DealFlow AI Agent** — a LangGraph-powered enterprise CRM
> workflow agent.
>
> Most "AI agent" demos are chatbots. I wanted to build the thing enterprises
> actually need: a stateful, auditable workflow that does real work and knows
> when to ask a human.
>
> You hand it a sales opportunity and it:
> • reads the structured CRM record (PostgreSQL)
> • retrieves the customer's support history via vector search (pgvector)
> • scores deal risk and flags missing CRM fields
> • drafts a CRM update — and **pauses for human approval** when the change is
>   high-risk, before writing anything back
> • persists full state + node-level audit logs the whole way
>
> Stack: LangGraph · LangChain · FastAPI · PostgreSQL + pgvector · SQLAlchemy ·
> Docker · GitHub Actions · pytest.
>
> It runs end-to-end on real public Kaggle data (8,800 opportunities, 8,469
> support tickets, 24,521 embedded documents) — and fully offline with
> deterministic fallbacks, so there are no API keys required to try it.
>
> It's a portfolio project (not production-deployed), but it's built like one:
> dual CI (offline SQLite suite + a PostgreSQL/pgvector integration job), an
> evaluation harness, a trace endpoint, modular services, and honest docs on
> what's real data vs. a documented synthetic linking layer.
>
> Code + write-up 👇
> #AI #LLM #LangGraph #AIAgents #FastAPI #pgvector #MachineLearning

---

## Application-form short description

> DealFlow AI Agent is a LangGraph-powered enterprise CRM workflow agent. It
> reviews a sales opportunity by combining structured CRM data with vector search
> over customer-support history, scores risk, drafts a CRM update, and requires
> human approval before high-risk writeback — with full state persistence and
> node-level audit logs. Built with FastAPI, PostgreSQL/pgvector, Docker, and
> GitHub Actions CI; runs on real public Kaggle data and offline with no API
> keys. (Portfolio project, not production-deployed.)

**One-liner**

> LangGraph enterprise CRM agent: stateful multi-step workflow, tool routing,
> human-in-the-loop approval, and audited CRM writeback over FastAPI +
> PostgreSQL/pgvector.

---

## Role positioning

**AI Agent Engineer**
Demonstrates the core of the role: multi-step agent orchestration with LangGraph,
a typed state machine, dynamic tool routing, conditional branching, human-in-the-
loop control, and restart-safe execution with audit logging — applied to a
realistic enterprise workflow rather than a chat demo.

**AI Engineer**
Shows end-to-end system ownership: structured + unstructured data integration,
PostgreSQL + pgvector retrieval, a swappable embedding abstraction, a clean
FastAPI service layer, Dockerized local dev, CI, and tests. Pragmatic engineering
(SQLite/Postgres portability, deterministic fallbacks) over flashy complexity.

**LLM Application Engineer**
Shows the scaffolding real LLM apps need around the model: retrieval, tool
interfaces, guardrails (approval before writes), state/audit persistence, and
provider abstractions for embeddings/LLMs. The deterministic node internals are
LLM-ready hooks, so the path to a model-backed deployment is a config change, not
a rewrite.
