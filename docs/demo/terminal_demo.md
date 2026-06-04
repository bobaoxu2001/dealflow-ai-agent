# Terminal demo (realistic run)

A realistic end-to-end run against the offline demo data (`make seed-demo`). The
high-risk opportunity `OPP-DEMO1` pauses for human approval; after approval the
agent resumes and writes back to the CRM. Task ids are abbreviated.

```text
$ curl -s localhost:8000/health
{"status":"ok","app":"DealFlow AI Agent","environment":"local",
 "database":"sqlite","embedding_provider":"local"}

$ curl -s -X POST localhost:8000/search/vector \
    -d '{"query":"customer wants to cancel and churn","account_id":"ACC-DEMO1","top_k":2}'
{"query":"customer wants to cancel and churn","count":2,
 "results":[
   {"source_type":"risk_note","account_id":"ACC-DEMO1",
    "content":"RISK: churn signal, competitor evaluation, escalated complaint.","score":0.41},
   {"source_type":"support_ticket","account_id":"ACC-DEMO1",
    "content":"Customer reports critical outages and is threatening to cancel ...","score":0.33}]}

$ curl -s -X POST localhost:8000/agent/review-opportunity \
    -d '{"opportunity_id":"OPP-DEMO1","task":"Review this opportunity..."}'
{ "task_id":"TASK-fe82...","execution_status":"pending_approval",
  "approval_status":"pending","requires_human_approval":true,"risk_score":1.0,
  "missing_fields":["close_date"],
  "crm_update_draft":{"changes":{"stage":"On Hold"}, ...} }     # NOTE: not written yet

$ curl -s localhost:8000/agent/tasks/TASK-fe82.../trace
{ "task_id":"TASK-fe82...","execution_status":"pending_approval","step_count":8,
  "trace":[
    {"step":1,"node_name":"parse_task","status":"ok"},
    {"step":2,"node_name":"retrieve_crm_context","status":"ok","output_summary":"account_id=ACC-DEMO1, tickets=2"},
    {"step":3,"node_name":"retrieve_vector_context","status":"ok","output_summary":"retrieved 4 documents"},
    {"step":4,"node_name":"analyze_risks","status":"ok","output_summary":"risk_score=1.0, flags=11"},
    {"step":5,"node_name":"detect_missing_fields","status":"ok","output_summary":"missing=['close_date']"},
    {"step":6,"node_name":"recommend_next_steps","status":"ok"},
    {"step":7,"node_name":"draft_crm_update","status":"ok","output_summary":"proposed changes: ['stage']"},
    {"step":8,"node_name":"approval_router","status":"pending_approval",
     "output_summary":"approval required: ['risk_score 1.0 >= threshold 0.6', \"modifies important fields: ['stage']\"]"}]}

$ curl -s -X POST localhost:8000/agent/tasks/TASK-fe82.../approve -d '{"approver":"sales_manager"}'
{ "execution_status":"completed","approval_status":"approved",
  "crm_update_draft":{"applied":{"stage":{"old":"Engaging","new":"On Hold"}},
                      "writeback_id":"WB-1a51..."},
  "final_report":{"executive_summary":"Opportunity OPP-DEMO1 ... Overall deal risk is HIGH (score 1.0) ...",
                  "synthesized_by":"local"} }
```

Full machine-generated responses: [`sample_agent_response.json`](sample_agent_response.json),
[`sample_trace_response.json`](sample_trace_response.json).
