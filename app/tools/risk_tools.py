"""Deterministic risk scoring + missing-field detection.

Heuristic, explainable, and key-free so the workflow runs anywhere. An LLM
could later refine these signals, but the rules below give stable, testable
behavior and transparent risk explanations.
"""
from __future__ import annotations

# Keywords that suggest deal risk when found in support/ticket/note text.
RISK_KEYWORDS = {
    "churn": 0.30,
    "cancel": 0.30,
    "refund": 0.20,
    "complaint": 0.15,
    "escalat": 0.25,
    "unhappy": 0.20,
    "dissatisf": 0.20,
    "delay": 0.10,
    "competitor": 0.25,
    "legal": 0.30,
    "outage": 0.20,
    "critical": 0.15,
    "blocker": 0.20,
    "urgent": 0.10,
}


def score_risks(structured_context: dict, retrieved_documents: list[dict]) -> tuple[float, list[dict]]:
    """Return (risk_score in [0,1], list of risk_flag dicts)."""
    flags: list[dict] = []
    score = 0.0

    ticket_summary = (structured_context.get("ticket_summary") or {})
    open_tickets = ticket_summary.get("open", 0)
    high_priority = ticket_summary.get("high_priority", 0)
    if open_tickets >= 3:
        flags.append({"type": "open_tickets", "detail": f"{open_tickets} open tickets", "weight": 0.2})
        score += 0.2
    if high_priority >= 1:
        flags.append(
            {"type": "high_priority_tickets", "detail": f"{high_priority} high/critical tickets", "weight": 0.2}
        )
        score += 0.2

    # Stalled / regressing pipeline stage.
    opp = structured_context.get("opportunity") or {}
    stage = (opp.get("stage") or "").lower()
    if stage in {"lost", "on hold", "stalled"}:
        flags.append({"type": "stage_risk", "detail": f"stage={stage}", "weight": 0.25})
        score += 0.25

    # Keyword scan across retrieved unstructured documents.
    seen_keywords: dict[str, int] = {}
    for doc in retrieved_documents:
        text = (doc.get("content") or "").lower()
        for kw in RISK_KEYWORDS:
            if kw in text:
                seen_keywords[kw] = seen_keywords.get(kw, 0) + 1
    for kw, count in seen_keywords.items():
        w = RISK_KEYWORDS[kw]
        flags.append({"type": "signal", "detail": f"'{kw}' x{count}", "weight": w})
        score += w

    score = max(0.0, min(1.0, round(score, 3)))
    return score, flags


REQUIRED_OPP_FIELDS = ["stage", "deal_value", "close_date", "product", "sales_agent"]


def detect_missing_fields(structured_context: dict) -> list[str]:
    opp = structured_context.get("opportunity") or {}
    missing = []
    for field in REQUIRED_OPP_FIELDS:
        value = opp.get(field)
        if value in (None, "", 0):
            missing.append(field)
    return missing
