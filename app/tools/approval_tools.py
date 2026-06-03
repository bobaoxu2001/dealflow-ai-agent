"""Approval decision helpers used by the routing logic."""
from __future__ import annotations

from app.utils.config import settings


def needs_human_approval(risk_score: float, crm_update_draft: dict) -> tuple[bool, list[str]]:
    """Decide whether a CRM writeback requires human sign-off.

    Approval is required when EITHER:
      * the computed risk score is at/above the configured high-risk threshold, OR
      * the drafted update modifies any field in APPROVAL_REQUIRED_FIELDS.
    """
    reasons: list[str] = []
    if risk_score >= settings.high_risk_threshold:
        reasons.append(f"risk_score {risk_score} >= threshold {settings.high_risk_threshold}")

    changed_fields = set((crm_update_draft or {}).get("changes", {}).keys())
    important = changed_fields & settings.approval_field_set
    if important:
        reasons.append(f"modifies important fields: {sorted(important)}")

    return (len(reasons) > 0, reasons)
