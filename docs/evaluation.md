# Evaluation

A common gap in agent portfolio projects is "I built it but never measured it."
This project ships a lightweight, deterministic evaluation harness
(`app/services/evaluation_service.py`, run via `scripts/evaluate_agent.py`).

It is intentionally **not** an LLM-as-judge harness — the agent's logic is
deterministic, so the checks are deterministic and reproducible too. Each check
returns a `passed` flag plus metrics and is unit-tested in
`tests/test_evaluation.py`.

Run it:

```bash
make seed-demo        # or run the Kaggle ingest pipeline
make evaluate         # prints a table + writes reports/evaluation_summary.json
```

## What it checks

| Check | What it verifies |
|---|---|
| `retrieval_scoped_accuracy` | Vector search scoped to an opportunity returns documents from that same opportunity (scoped retrieval correctness). Reports sample size + accuracy. |
| `risk_scoring_separation` | A churn/escalation-heavy context scores **≥ 0.6** while a clean context scores **< 0.6**, and only the risky one triggers approval. |
| `approval_routing` | High risk + important-field change → `pending`; no proposed change → `finalize` (no writeback); approved → `writeback`; rejected → never `writeback`. |
| `data_pipeline_integrity` | Expected tables are non-empty and synthetic-layer rows (meeting/risk notes) are correctly flagged `is_synthetic=true`. |

## Example result (offline demo data)

```text
=== DealFlow AI Agent — Evaluation Summary ===
check                            passed   detail
------------------------------------------------------------------------
retrieval_scoped_accuracy        PASS     samples=4, correct=4, accuracy=1.0
risk_scoring_separation          PASS     risky_score=1.0, clean_score=0.0, risky_flags=...
approval_routing                 PASS     high_risk_change_route=pending, approved_route=writeback, ...
data_pipeline_integrity          PASS     counts={...}, non_synthetic_meeting_notes=0, ...
------------------------------------------------------------------------
TOTAL: 4/4 checks passed (ALL PASSED)
```

A machine-generated sample is committed at
[`demo/sample_evaluation_summary.json`](demo/sample_evaluation_summary.json).

## Honest limitations

- These are **sanity / regression** checks, not a benchmark against labeled
  ground truth (the datasets have no agent-decision labels).
- Retrieval accuracy uses scoped self-retrieval, which validates the plumbing and
  filtering — not semantic ranking quality of a production embedding model.
- With the local hashing embedder, semantic quality is limited by design; swap in
  a real embedding model (one config change) for meaningful ranking metrics.
