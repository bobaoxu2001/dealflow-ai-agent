# Demo commands

Copy-paste curl commands for a full walkthrough. Start the stack first:

```bash
make install
make seed-demo          # zero-infra demo data (no Kaggle/API keys needed)
make dev                # serves on http://localhost:8000
```

Sample responses for these calls are committed alongside this file:
[`sample_agent_response.json`](sample_agent_response.json),
[`sample_trace_response.json`](sample_trace_response.json),
[`sample_evaluation_summary.json`](sample_evaluation_summary.json).

```bash
# 1. Health
curl -s http://localhost:8000/health | jq

# 2. Vector search (scoped to an account)
curl -s -X POST http://localhost:8000/search/vector \
  -H 'Content-Type: application/json' \
  -d '{"query":"customer wants to cancel and churn","account_id":"ACC-DEMO1","top_k":3}' | jq

# 3. Opportunity context (structured + unstructured)
curl -s "http://localhost:8000/opportunities/OPP-DEMO1/context?query=risk%20churn&top_k=3" | jq

# 4. Start an opportunity review (HIGH-RISK -> pauses for approval)
curl -s -X POST http://localhost:8000/agent/review-opportunity \
  -H 'Content-Type: application/json' \
  -d '{"opportunity_id":"OPP-DEMO1","task":"Review this opportunity, identify blockers, summarize client history, and recommend next steps."}' | jq

# 5. Task status (grab task_id from step 4)
curl -s http://localhost:8000/agent/tasks/<TASK_ID> | jq

# 6. Execution trace (ordered node-by-node audit)
curl -s http://localhost:8000/agent/tasks/<TASK_ID>/trace | jq

# 7. Approve -> resumes workflow -> CRM writeback
curl -s -X POST http://localhost:8000/agent/tasks/<TASK_ID>/approve \
  -H 'Content-Type: application/json' -d '{"approver":"sales_manager"}' | jq

#    ...or reject -> no writeback
curl -s -X POST http://localhost:8000/agent/tasks/<TASK_ID>/reject \
  -H 'Content-Type: application/json' -d '{"approver":"sales_manager","reason":"need more info"}' | jq

# 8. Low-risk opportunity completes with no approval/writeback
curl -s -X POST http://localhost:8000/agent/review-opportunity \
  -H 'Content-Type: application/json' -d '{"opportunity_id":"OPP-DEMO2"}' | jq

# 9. Evaluation summary
make evaluate            # writes reports/evaluation_summary.json
```
