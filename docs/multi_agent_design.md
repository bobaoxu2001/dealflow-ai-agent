# Multi-agent design (role-based, supervised)

DealFlow uses a **role-based** multi-agent layer (`app/agents/roles.py`) under a
**LangGraph supervisor** (`app/agents/graph.py`). These are bounded role objects,
not free-form autonomous agents.

## The roles

| Role | Responsibility | Wraps |
|---|---|---|
| `CustomerContextAgent` | Gather structured CRM context + retrieve support history | `crm_read`, `vector_search` |
| `DealAnalysisAgent` | Score deal risk, detect missing CRM fields | `score_risks`, `detect_missing_fields` |
| `CRMGovernanceAgent` | Draft the CRM update; decide if human approval is required | `needs_human_approval` + draft rules |
| `ExecutiveSynthesisAgent` | Recommend next steps; synthesize the final narrative | recommendation rules, `llm_service` |

Each role owns exactly one enterprise responsibility and is the only place that
responsibility lives.

## Why role-based is safer than free-form autonomous agents

- **Bounded authority.** Each role exposes a small, fixed set of methods over
  pre-approved tools. There is no open-ended "agent decides which tool to call
  next" loop that can wander, loop, or take unintended actions.
- **Deterministic & testable.** Role logic is deterministic by default, so the
  same inputs give the same outputs — every role is unit-tested
  (`tests/test_roles.py`). Free-form agents are hard to test and reproduce.
- **Governed writes.** Only `CRMGovernanceAgent` can propose a CRM change, and it
  always routes high-risk / important-field changes to human approval. No role —
  and not the LLM — can apply a writeback outside the approval-gated node.
- **Auditable.** Because responsibilities are fixed, every step maps to a known
  node with an audit row and timing (see the `/trace` endpoint). With autonomous
  agents, the trace is whatever the model decided to do.
- **Least privilege.** The LLM is confined to `ExecutiveSynthesisAgent` and only
  summarizes already-computed results; it has no path to tools, routing, or writes.

## How LangGraph supervises the roles

LangGraph is the **supervisor / orchestrator**. The `StateGraph` defines the
order and the branch points; nodes are thin adapters that call into a role and
write state + an audit entry:

```
parse_task
  → retrieve_crm_context      (CustomerContextAgent)
  → retrieve_vector_context   (CustomerContextAgent)
  → analyze_risks             (DealAnalysisAgent)
  → detect_missing_fields     (DealAnalysisAgent)
  → recommend_next_steps      (ExecutiveSynthesisAgent)
  → draft_crm_update          (CRMGovernanceAgent)
  → approval_router           (CRMGovernanceAgent decides)  ──► pending? → STOP (await human)
                                                             └► else      → writeback_crm → finalize_report
  → finalize_report           (ExecutiveSynthesisAgent synthesizes)
```

The supervisor — not any role — decides routing (including the human-in-the-loop
pause and resume). Roles cannot call each other directly or change the route;
they only return results to the graph.

## How this maps to enterprise AI workflows

This mirrors how regulated enterprises (professional/financial services,
consulting, B2B sales ops) actually want AI to operate:

- A **research/context** function gathers the facts.
- A **risk/analysis** function evaluates them with explainable rules.
- A **governance** function proposes changes and enforces approval policy before
  any system-of-record write.
- A **synthesis** function communicates the result to a human.
- A **supervisor** sequences the work, keeps durable state, and stops for human
  sign-off on high-impact actions.

Role-based supervision gives the benefits of "multi-agent" decomposition —
separation of concerns, parallelizable responsibilities, clear ownership —
without the unpredictability and audit gaps of fully autonomous agents.
