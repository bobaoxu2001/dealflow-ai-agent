# CRM integrations

The agent reads CRM context and (after human approval) writes back through a
pluggable **CRM adapter** (`app/integrations/crm_adapter.py`). This lets the same
LangGraph workflow target different CRM backends without changing the graph.

> **Default is fully local and secret-free.** Nothing external is contacted
> unless you explicitly opt in. CI never calls HubSpot.

## Adapters

| `CRM_ADAPTER` | Backend | Network | Writeback | Use case |
|---|---|---|---|---|
| `local` *(default)* | Project's own PostgreSQL/SQLite | none | applies to local DB | normal local/CI runs |
| `mock_external` | Simulated external CRM (reads local data) | none | simulated in-memory | demo the external-adapter contract deterministically |
| `hubspot` | Real HubSpot CRM v3 API | yes | **dry-run by default** | demonstrate real external CRM integration |

All adapters implement the same interface:

```python
get_opportunity(opportunity_id)
get_account(account_id)
get_context(opportunity_id)
apply_writeback(opportunity_id, changes, idempotency_key=None)
```

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `CRM_ADAPTER` | `local` | `local` \| `mock_external` \| `hubspot` |
| `HUBSPOT_ACCESS_TOKEN` | *(unset)* | Private-app token. Required only for `hubspot`. Never commit it. |
| `HUBSPOT_BASE_URL` | `https://api.hubapi.com` | HubSpot API base URL |
| `HUBSPOT_DRY_RUN` | `true` | When `true`, writeback never sends a PATCH |
| `HUBSPOT_TIMEOUT_SECONDS` | `10` | Per-request timeout |

### Example `.env` (HubSpot, opt-in)

```dotenv
CRM_ADAPTER=hubspot
HUBSPOT_ACCESS_TOKEN=pat-na1-xxxxxxxx   # your token; DO NOT COMMIT
HUBSPOT_BASE_URL=https://api.hubapi.com
HUBSPOT_DRY_RUN=true                     # set false only when you intend real writes
HUBSPOT_TIMEOUT_SECONDS=10
```

## Safety controls

- **Dry-run by default.** `HUBSPOT_DRY_RUN=true` means `apply_writeback` validates
  and maps the change, logs it, and returns a `dry_run` result **without sending a
  PATCH**. A real write requires `HUBSPOT_DRY_RUN=false`.
- **Strict writeback allowlist.** Only these HubSpot deal properties may be
  written; anything else raises `UnsafeFieldError`:
  - `dealstage` (internal `stage`)
  - `amount` (internal `deal_value`)
  - `closedate` (internal `close_date`)
  - `dealflow_ai_status`
- **Human approval still required.** The adapter does not change *who* may write.
  High-risk/important-field writebacks still pause for human approval in the agent
  graph before `apply_writeback` is ever called.
- **The LLM cannot write.** LLM synthesis only produces the narrative summary; it
  has no path to `apply_writeback`.
- **No token logging.** The access token is only used as a bearer header and is
  never written to logs or error messages.
- **Clean error handling.** 401/403/404/429/5xx are mapped to clear,
  token-free `CRMAdapterError` messages.

## HubSpot specifics

- Reads deals via `GET /crm/v3/objects/deals/{id}` (properties
  `dealname,dealstage,amount,closedate`, association `companies`) and normalizes
  them into the project's internal opportunity shape.
- Best-effort account context via `GET /crm/v3/objects/companies/{id}`.
- Real writeback is `PATCH /crm/v3/objects/deals/{id}` with
  `{"properties": {...allowlisted...}}`.

## Why CI does not call HubSpot

CI must be deterministic, fast, and secret-free. So:

- CI runs only the `local` (SQLite) and `pgvector` paths; `CRM_ADAPTER` stays at
  its `local` default.
- HubSpot adapter tests use `httpx.MockTransport` — they exercise normalization,
  dry-run behavior, the field allowlist, and error mapping **without any network
  call or real token**.
- No HubSpot token exists in the repo or CI secrets, so the live path simply
  cannot run in CI.
