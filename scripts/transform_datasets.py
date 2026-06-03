"""Transform raw Kaggle CSVs into normalized processed CSVs.

Inputs  (data/raw/crm, data/raw/support)
Outputs (data/processed):
    accounts.csv, opportunities.csv, products.csv, sales_teams.csv, contacts.csv,
    support_tickets.csv, client_notes.csv, risk_notes.csv

Key mapping decisions (documented in README):
  * The CRM dataset keys accounts by *name*; we mint stable surrogate
    account_id values (ACC-0001 ...) from the sorted unique account names.
  * The two datasets share no real join key, so each support ticket is mapped to
    a CRM account deterministically via a hash of its ticket id (seeded), and,
    where the account has opportunities, to one of those opportunities.
  * client_notes / risk_notes are *derived from real ticket text* (not invented):
    risk_notes come from low-satisfaction or high-priority tickets.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from app.utils.config import PROCESSED_DIR, RAW_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)

CRM_DIR = RAW_DIR / "crm"
SUPPORT_DIR = RAW_DIR / "support"


def _find(directory: Path, *keywords: str) -> Path | None:
    for path in sorted(directory.rglob("*.csv")):
        name = path.name.lower()
        if all(k in name for k in keywords):
            return path
    return None


def _account_id_for(name: str, mapping: dict[str, str]) -> str | None:
    if pd.isna(name) or name == "":
        return None
    return mapping.get(str(name))


def _stable_index(key: str, modulo: int) -> int:
    h = int(hashlib.md5(f"dealflow::{key}".encode()).hexdigest(), 16)
    return h % modulo


def transform_crm() -> dict[str, str]:
    accounts_f = _find(CRM_DIR, "account")
    pipeline_f = _find(CRM_DIR, "pipeline") or _find(CRM_DIR, "sales", "pipeline")
    products_f = _find(CRM_DIR, "product")
    teams_f = _find(CRM_DIR, "team")
    if not accounts_f or not pipeline_f:
        raise FileNotFoundError(
            f"CRM raw files not found under {CRM_DIR}. Run `make download` or `make seed-demo`."
        )

    accounts = pd.read_csv(accounts_f)
    account_names = sorted(accounts["account"].dropna().unique())
    name_to_id = {n: f"ACC-{i + 1:04d}" for i, n in enumerate(account_names)}

    accounts_out = pd.DataFrame(
        {
            "account_id": accounts["account"].map(name_to_id),
            "account_name": accounts["account"],
            "sector": accounts.get("sector"),
            "year_established": accounts.get("year_established"),
            "revenue": accounts.get("revenue"),
            "employees": accounts.get("employees"),
            "office_location": accounts.get("office_location"),
            "subsidiary_of": accounts.get("subsidiary_of"),
            "is_synthetic": False,
        }
    ).dropna(subset=["account_id"])
    accounts_out.to_csv(PROCESSED_DIR / "accounts.csv", index=False)

    pipeline = pd.read_csv(pipeline_f)
    opps_out = pd.DataFrame(
        {
            "opportunity_id": pipeline["opportunity_id"],
            "account_id": pipeline["account"].map(lambda n: _account_id_for(n, name_to_id)),
            "sales_agent": pipeline.get("sales_agent"),
            "product": pipeline.get("product"),
            "stage": pipeline.get("deal_stage"),
            "deal_value": pipeline.get("close_value"),
            "engage_date": pipeline.get("engage_date"),
            "close_date": pipeline.get("close_date"),
            "is_synthetic": False,
        }
    )
    opps_out.to_csv(PROCESSED_DIR / "opportunities.csv", index=False)

    if products_f is not None:
        products = pd.read_csv(products_f)
        pd.DataFrame(
            {
                "product": products.get("product"),
                "series": products.get("series"),
                "sales_price": products.get("sales_price"),
            }
        ).to_csv(PROCESSED_DIR / "products.csv", index=False)

    if teams_f is not None:
        teams = pd.read_csv(teams_f)
        pd.DataFrame(
            {
                "sales_agent": teams.get("sales_agent"),
                "manager": teams.get("manager"),
                "regional_office": teams.get("regional_office"),
            }
        ).to_csv(PROCESSED_DIR / "sales_teams.csv", index=False)

    logger.info("CRM transform complete: %d accounts, %d opportunities", len(accounts_out), len(opps_out))
    return name_to_id


def transform_support(account_ids: list[str], opps_by_account: dict[str, list[str]]) -> None:
    tickets_f = _find(SUPPORT_DIR, "ticket") or next(iter(sorted(SUPPORT_DIR.rglob("*.csv"))), None)
    if not tickets_f:
        raise FileNotFoundError(
            f"Support raw files not found under {SUPPORT_DIR}. Run `make download` or `make seed-demo`."
        )

    df = pd.read_csv(tickets_f)
    cols = {c.lower().strip(): c for c in df.columns}

    def col(*cands: str):
        for c in cands:
            if c in cols:
                return df[cols[c]]
        return pd.Series([None] * len(df))

    n_accounts = max(1, len(account_ids))
    ticket_ids = col("ticket id", "ticket_id").fillna(pd.Series(range(len(df)))).astype(str)

    mapped_accounts = [account_ids[_stable_index(tid, n_accounts)] for tid in ticket_ids]
    mapped_opps = []
    for acc, tid in zip(mapped_accounts, ticket_ids, strict=False):
        opps = opps_by_account.get(acc, [])
        mapped_opps.append(opps[_stable_index(tid, len(opps))] if opps else None)

    tickets_out = pd.DataFrame(
        {
            "ticket_id": ["TCK-" + str(t) for t in ticket_ids],
            "account_id": mapped_accounts,
            "opportunity_id": mapped_opps,
            "customer_name": col("customer name", "customer_name"),
            "product_purchased": col("product purchased", "product_purchased"),
            "ticket_type": col("ticket type", "ticket_type"),
            "ticket_subject": col("ticket subject", "ticket_subject"),
            "ticket_status": col("ticket status", "ticket_status"),
            "priority": col("ticket priority", "ticket_priority", "priority"),
            "description": col("ticket description", "ticket_description", "description"),
            "resolution": col("resolution"),
            "customer_satisfaction": pd.to_numeric(
                col("customer satisfaction rating", "customer_satisfaction_rating"),
                errors="coerce",
            ),
            "is_synthetic": False,
        }
    )
    tickets_out.to_csv(PROCESSED_DIR / "support_tickets.csv", index=False)

    # Derived (grounded) notes -------------------------------------------------
    client_rows, risk_rows = [], []
    for _, r in tickets_out.iterrows():
        subject = r["ticket_subject"] or "support issue"
        client_rows.append(
            {
                "note_id": "CN-" + r["ticket_id"],
                "account_id": r["account_id"],
                "opportunity_id": r["opportunity_id"],
                "author": "support_system",
                "content": f"Client raised a {r['ticket_type'] or 'support'} ticket: "
                f"'{subject}'. Status: {r['ticket_status'] or 'unknown'}.",
                "is_synthetic": True,
            }
        )
        sat = r["customer_satisfaction"]
        high_priority = str(r["priority"]).lower() in {"high", "critical"}
        low_sat = pd.notna(sat) and float(sat) <= 2
        if high_priority or low_sat:
            severity = "high" if (high_priority and low_sat) else "medium"
            risk_rows.append(
                {
                    "note_id": "RN-" + r["ticket_id"],
                    "account_id": r["account_id"],
                    "opportunity_id": r["opportunity_id"],
                    "severity": severity,
                    "content": f"RISK: ticket '{subject}' priority={r['priority']} "
                    f"satisfaction={sat}. Potential dissatisfaction / churn signal.",
                    "is_synthetic": True,
                }
            )

    pd.DataFrame(client_rows).to_csv(PROCESSED_DIR / "client_notes.csv", index=False)
    pd.DataFrame(risk_rows).to_csv(PROCESSED_DIR / "risk_notes.csv", index=False)

    # Lightweight synthetic contacts derived from ticket customer names.
    contacts = (
        tickets_out[["account_id", "customer_name"]]
        .dropna()
        .drop_duplicates("account_id")
        .reset_index(drop=True)
    )
    contacts_out = pd.DataFrame(
        {
            "contact_id": ["CON-" + a for a in contacts["account_id"]],
            "account_id": contacts["account_id"],
            "name": contacts["customer_name"],
            "email": [
                f"{str(n).split()[0].lower()}@example.com" if pd.notna(n) else None
                for n in contacts["customer_name"]
            ],
            "title": "Primary Contact",
            "is_synthetic": True,
        }
    )
    contacts_out.to_csv(PROCESSED_DIR / "contacts.csv", index=False)

    logger.info("Support transform complete: %d tickets, %d risk notes", len(tickets_out), len(risk_rows))


def main() -> int:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    name_to_id = transform_crm()

    opps = pd.read_csv(PROCESSED_DIR / "opportunities.csv")
    opps_by_account: dict[str, list[str]] = {}
    for _, row in opps.dropna(subset=["account_id"]).iterrows():
        opps_by_account.setdefault(row["account_id"], []).append(row["opportunity_id"])

    transform_support(sorted(name_to_id.values()), opps_by_account)
    logger.info("All processed CSVs written to %s", PROCESSED_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
