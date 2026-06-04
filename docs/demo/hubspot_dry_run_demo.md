# HubSpot dry-run verification (local only)

A short, **local-only** guide to exercise the optional HubSpot CRM adapter
against your own HubSpot account in **dry-run mode** — it reads a real deal but
sends **no** write. This is opt-in and never used by CI.

> **Safety first**
> - **Dry-run = no PATCH is sent.** With `HUBSPOT_DRY_RUN=true` the adapter
>   validates and maps the change, then returns a `dry_run` result without
>   writing anything to HubSpot.
> - **Real writeback requires `HUBSPOT_DRY_RUN=false`** (do not do this unless you
>   intend a real write, and only against a sandbox/test deal).
> - **Never commit `.env`** — it is git-ignored. Never paste a token into code,
>   docs, or commits.
> - **Only use sandbox/test deals**, not production records.
> - Human approval still gates writeback in the agent graph; the LLM cannot write.

## 1. Setup

### 1a. Create a HubSpot private app token
1. In HubSpot: **Settings → Integrations → Private Apps → Create a private app**
   (use a **developer/test account or sandbox**, not production).
2. Under **Scopes**, grant CRM deal access (e.g. `crm.objects.deals.read`, and
   `crm.objects.deals.write` only if you later test a real write).
3. Create the app and copy the **access token** (looks like `pat-na1-...`).

### 1b. Configure your local `.env` (never commit it)
```bash
cp .env.example .env
```
Edit `.env` and set:
```dotenv
CRM_ADAPTER=hubspot
HUBSPOT_ACCESS_TOKEN=<your token>     # paste your pat-na1-... here; DO NOT COMMIT
HUBSPOT_DRY_RUN=true                  # keep true for this guide
HUBSPOT_BASE_URL=https://api.hubapi.com
HUBSPOT_TIMEOUT_SECONDS=10
```

Confirm `.env` is ignored (should print `.env`):
```bash
git check-ignore .env
```

Install deps if you haven't:
```bash
make install
```

## 2. Read a HubSpot deal by deal ID

Replace `DEAL_ID` with a deal id from your sandbox (the numeric id in the deal
URL). This performs a **read only**.

```bash
python - <<'PY'
from app.db.session import SessionLocal
from app.integrations.crm_adapter import get_crm_adapter

DEAL_ID = "DEAL_ID"  # <-- your sandbox deal id

session = SessionLocal()
adapter = get_crm_adapter(session)          # CRM_ADAPTER=hubspot -> HubSpotCRMAdapter
print("adapter:", adapter.name)
print("opportunity:", adapter.get_opportunity(DEAL_ID))
print("context:", adapter.get_context(DEAL_ID))
session.close()
PY
```

Expected: a normalized opportunity dict (`opportunity_id`, `stage`, `deal_value`,
`close_date`, `account_id`, `source="hubspot"`).

## 3. Run a dry-run writeback (no PATCH is sent)

```bash
python - <<'PY'
from app.db.session import SessionLocal
from app.integrations.crm_adapter import get_crm_adapter

DEAL_ID = "DEAL_ID"  # <-- your sandbox deal id

session = SessionLocal()
adapter = get_crm_adapter(session)
result = adapter.apply_writeback(
    DEAL_ID,
    {"stage": "appointmentscheduled", "deal_value": 12345},  # internal field names
)
print(result)
session.close()
PY
```

Expected result (note **no PATCH was sent**):
```python
{
  "adapter": "hubspot",
  "opportunity_id": "DEAL_ID",
  "status": "dry_run",
  "dry_run": True,
  "proposed": {"dealstage": "appointmentscheduled", "amount": 12345},  # mapped to HubSpot props
  "applied": {},
  "detail": "HUBSPOT_DRY_RUN=true; no write was sent to HubSpot.",
}
```

### Field allowlist (everything else is rejected)
Only these may be written; any other field raises `UnsafeFieldError`:

| Internal field | HubSpot property |
|---|---|
| `stage` | `dealstage` |
| `deal_value` | `amount` |
| `close_date` | `closedate` |
| `dealflow_ai_status` | `dealflow_ai_status` |

Try an unsafe field to confirm it is rejected (still no PATCH):
```bash
python - <<'PY'
from app.db.session import SessionLocal
from app.integrations.crm_adapter import get_crm_adapter, UnsafeFieldError

session = SessionLocal()
adapter = get_crm_adapter(session)
try:
    adapter.apply_writeback("DEAL_ID", {"owner_id": "nope"})
except UnsafeFieldError as e:
    print("rejected as expected:", e)
session.close()
PY
```

## 4. (Optional) Real writeback — only if you mean it

Real writes are intentionally gated. **Only** against a sandbox/test deal, and
only when you actually intend a write:

```dotenv
HUBSPOT_DRY_RUN=false
```

Then re-run the step 3 snippet. The result will show `"status": "applied"` and a
real `PATCH /crm/v3/objects/deals/{id}` is sent with the allowlisted properties.
Set `HUBSPOT_DRY_RUN=true` again afterward.

## 5. Reset to the default (no external calls)

```dotenv
CRM_ADAPTER=local
```

This returns the project to its zero-secret local behavior.

---

**Why CI doesn't do this:** CI must be deterministic and secret-free, so it never
sets `CRM_ADAPTER=hubspot`. HubSpot behavior is covered by `tests/test_crm_adapter.py`
using `httpx.MockTransport` — no network, no token. See
[`../integrations.md`](../integrations.md) for the full safety model.
