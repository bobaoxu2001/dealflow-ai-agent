"""Lightweight, dependency-free evaluation of the agent's building blocks.

This is deliberately *not* an LLM-grading harness. It runs deterministic sanity
checks against whatever data is currently loaded (demo seed or real Kaggle data)
and reports simple, defensible metrics:

  1. Retrieval quality   - scoped vector search returns same-scope documents
  2. Risk scoring        - risky context scores high; clean context scores low
  3. Approval routing    - high risk / important fields -> approval; no changes -> none
  4. Data pipeline       - expected rows exist; synthetic rows are flagged

Each check returns a dict with `passed` plus metrics, so it is unit-testable.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.routers import route_after_approval
from app.db.models import (
    Account,
    MeetingNote,
    Opportunity,
    RiskNote,
    SupportTicket,
    VectorDocument,
)
from app.tools.approval_tools import needs_human_approval
from app.tools.risk_tools import score_risks
from app.services.vector_search_service import VectorSearchService


# --------------------------------------------------------------------------- #
# 1. Retrieval quality
# --------------------------------------------------------------------------- #
def evaluate_retrieval(session: Session, max_samples: int = 20) -> dict:
    """For docs scoped to an opportunity, scoped search should return that scope."""
    svc = VectorSearchService(session)
    rows = (
        session.execute(
            select(VectorDocument)
            .where(VectorDocument.opportunity_id.isnot(None))
            .limit(max_samples)
        )
        .scalars()
        .all()
    )
    total = 0
    correct = 0
    for doc in rows:
        if not (doc.content or "").strip():
            continue
        total += 1
        hits = svc.search_by_opportunity(doc.opportunity_id, doc.content, top_k=3)
        if hits and all(h.opportunity_id == doc.opportunity_id for h in hits):
            correct += 1
    accuracy = round(correct / total, 3) if total else 0.0
    return {
        "name": "retrieval_scoped_accuracy",
        "samples": total,
        "correct": correct,
        "accuracy": accuracy,
        "passed": total == 0 or accuracy >= 0.9,
    }


# --------------------------------------------------------------------------- #
# 2. Risk scoring
# --------------------------------------------------------------------------- #
def evaluate_risk_scoring(session: Session) -> dict:  # noqa: ARG001 (session unused; kept uniform)
    risky_ctx = {
        "opportunity": {"stage": "Engaging"},
        "ticket_summary": {"open": 5, "high_priority": 3, "total": 6},
    }
    risky_docs = [{"content": "customer threatening to churn and cancel; escalated complaint"}]
    risky_score, risky_flags = score_risks(risky_ctx, risky_docs)

    clean_ctx = {
        "opportunity": {"stage": "Engaging"},
        "ticket_summary": {"open": 0, "high_priority": 0, "total": 1},
    }
    clean_docs = [{"content": "customer asked a routine how-to question; resolved happily"}]
    clean_score, _ = score_risks(clean_ctx, clean_docs)

    risky_required, _ = needs_human_approval(risky_score, {"changes": {"stage": "On Hold"}})
    clean_required, _ = needs_human_approval(clean_score, {"changes": {}})

    return {
        "name": "risk_scoring_separation",
        "risky_score": risky_score,
        "clean_score": clean_score,
        "risky_flags": len(risky_flags),
        "passed": (
            risky_score >= 0.6
            and clean_score < 0.6
            and risky_required
            and not clean_required
        ),
    }


# --------------------------------------------------------------------------- #
# 3. Approval routing
# --------------------------------------------------------------------------- #
def evaluate_approval_routing(session: Session) -> dict:  # noqa: ARG001
    pending = route_after_approval(
        {"approval_status": "pending", "crm_update_draft": {"changes": {"stage": "On Hold"}}}
    )
    no_changes = route_after_approval(
        {"approval_status": "not_required", "crm_update_draft": {"changes": {}}}
    )
    approved = route_after_approval(
        {"approval_status": "approved", "crm_update_draft": {"changes": {"stage": "On Hold"}}}
    )
    rejected = route_after_approval(
        {"approval_status": "rejected", "crm_update_draft": {"changes": {"stage": "On Hold"}}}
    )
    return {
        "name": "approval_routing",
        "high_risk_change_route": pending,
        "no_change_route": no_changes,
        "approved_route": approved,
        "rejected_route": rejected,
        "passed": (
            pending == "pending"
            and no_changes == "finalize"
            and approved == "writeback"
            and rejected == "finalize"  # rejected never reaches writeback
        ),
    }


# --------------------------------------------------------------------------- #
# 4. Data pipeline
# --------------------------------------------------------------------------- #
def evaluate_data_pipeline(session: Session) -> dict:
    def count(model) -> int:
        return session.execute(select(func.count()).select_from(model)).scalar() or 0

    counts = {
        "accounts": count(Account),
        "opportunities": count(Opportunity),
        "support_tickets": count(SupportTicket),
        "vector_documents": count(VectorDocument),
    }
    # Synthetic-layer rows must be flagged is_synthetic=True.
    non_synth_meeting = session.execute(
        select(func.count()).select_from(MeetingNote).where(MeetingNote.is_synthetic.is_(False))
    ).scalar() or 0
    non_synth_risk = session.execute(
        select(func.count()).select_from(RiskNote).where(RiskNote.is_synthetic.is_(False))
    ).scalar() or 0

    return {
        "name": "data_pipeline_integrity",
        "counts": counts,
        "non_synthetic_meeting_notes": non_synth_meeting,
        "non_synthetic_risk_notes": non_synth_risk,
        "passed": (
            counts["accounts"] > 0
            and counts["opportunities"] > 0
            and counts["support_tickets"] > 0
            and counts["vector_documents"] > 0
            and non_synth_meeting == 0
            and non_synth_risk == 0
        ),
    }


def run_evaluation(session: Session) -> dict:
    checks = [
        evaluate_retrieval(session),
        evaluate_risk_scoring(session),
        evaluate_approval_routing(session),
        evaluate_data_pipeline(session),
    ]
    passed = sum(1 for c in checks if c["passed"])
    return {
        "summary": {
            "checks": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
            "all_passed": passed == len(checks),
        },
        "checks": checks,
    }
