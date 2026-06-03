"""Generate the synthetic *workflow* layer that turns two static datasets into
an enterprise-agent simulation.

This does NOT fabricate CRM or support rows. It only adds the workflow context an
agent needs and that the public datasets don't contain:
    meeting_notes.csv, missing_crm_fields.csv, agent_tasks_seed.csv,
    approval_states_seed.csv, crm_writebacks_seed.csv

All rows are deterministic (fixed seed) and flagged is_synthetic = True.
"""
from __future__ import annotations

import random

import pandas as pd

from app.utils.config import PROCESSED_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)

SEED = 42
MEETING_TEMPLATES = [
    "Kickoff call with {acct}. Discussed timeline and budget. Client cautious about pricing.",
    "Quarterly review with {acct}. Stakeholders raised concerns about onboarding speed.",
    "Demo session for {acct}. Positive feedback; competitor {comp} also under evaluation.",
    "Renewal discussion with {acct}. Procurement flagged contract terms for legal review.",
    "Check-in with {acct}. Support backlog mentioned as a blocker to expansion.",
]
COMPETITORS = ["Acme", "Globex", "Initech", "Umbrella", "Soylent"]


def _require(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"{path} missing. Run transform first (`make transform`).")
    return pd.read_csv(path)


def main() -> int:
    rng = random.Random(SEED)
    accounts = _require("accounts.csv")
    opps = _require("opportunities.csv")

    # 1) Meeting notes: ~1 per account (grounded with account name + competitor).
    meeting_rows = []
    for i, acc in accounts.iterrows():
        acc_opps = opps[opps["account_id"] == acc["account_id"]]
        opp_id = acc_opps.iloc[0]["opportunity_id"] if len(acc_opps) else None
        tmpl = MEETING_TEMPLATES[i % len(MEETING_TEMPLATES)]
        meeting_rows.append(
            {
                "note_id": f"MN-{acc['account_id']}",
                "account_id": acc["account_id"],
                "opportunity_id": opp_id,
                "meeting_date": f"2024-{(i % 12) + 1:02d}-15",
                "attendees": f"{acc['account_name']} team; DealFlow AE",
                "content": tmpl.format(acct=acc["account_name"], comp=rng.choice(COMPETITORS)),
                "is_synthetic": True,
            }
        )
    pd.DataFrame(meeting_rows).to_csv(PROCESSED_DIR / "meeting_notes.csv", index=False)

    # 2) Missing CRM fields: deterministically blank some fields on ~15% of opps.
    missing_rows = []
    for _, opp in opps.iterrows():
        h = (hash(opp["opportunity_id"]) % 100 + 100) % 100
        if h < 15:
            field = ["close_date", "deal_value", "product"][h % 3]
            missing_rows.append(
                {
                    "opportunity_id": opp["opportunity_id"],
                    "account_id": opp["account_id"],
                    "missing_field": field,
                    "is_synthetic": True,
                }
            )
    pd.DataFrame(missing_rows).to_csv(PROCESSED_DIR / "missing_crm_fields.csv", index=False)

    # 3) Seed agent tasks / approval states / writebacks (illustrative history).
    sample_opps = opps.dropna(subset=["account_id"]).head(5)
    task_rows, approval_rows, writeback_rows = [], [], []
    for i, opp in sample_opps.reset_index(drop=True).iterrows():
        tid = f"SEED-TASK-{i + 1:03d}"
        status = ["completed", "pending_approval", "rejected"][i % 3]
        task_rows.append(
            {
                "task_id": tid,
                "opportunity_id": opp["opportunity_id"],
                "account_id": opp["account_id"],
                "user_task": "Review this opportunity and recommend next steps.",
                "execution_status": status,
                "is_synthetic": True,
            }
        )
        approval_rows.append(
            {
                "task_id": tid,
                "approval_status": {"completed": "approved", "pending_approval": "pending",
                                    "rejected": "rejected"}[status],
                "approver": "seed_human" if status != "pending_approval" else None,
                "is_synthetic": True,
            }
        )
        if status == "completed":
            writeback_rows.append(
                {
                    "writeback_id": f"SEED-WB-{i + 1:03d}",
                    "task_id": tid,
                    "opportunity_id": opp["opportunity_id"],
                    "account_id": opp["account_id"],
                    "changes": '{"stage": {"old": "Engaging", "new": "Won"}}',
                    "status": "applied",
                    "is_synthetic": True,
                }
            )
    pd.DataFrame(task_rows).to_csv(PROCESSED_DIR / "agent_tasks_seed.csv", index=False)
    pd.DataFrame(approval_rows).to_csv(PROCESSED_DIR / "approval_states_seed.csv", index=False)
    pd.DataFrame(writeback_rows).to_csv(PROCESSED_DIR / "crm_writebacks_seed.csv", index=False)

    logger.info(
        "Synthetic layer written: %d meeting notes, %d missing-field rows, %d seed tasks",
        len(meeting_rows), len(missing_rows), len(task_rows),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
