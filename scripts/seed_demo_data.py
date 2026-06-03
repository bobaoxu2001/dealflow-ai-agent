"""Seed a small, clearly-synthetic demo dataset so the project runs fully offline
(no Kaggle download required). Also used by the test suite.

The demo set is intentionally crafted to exercise both workflow paths:
  * OPP-DEMO1 (Northwind): high-risk + missing field  -> requires human approval
  * OPP-DEMO2 (Initech)  : clean + low-risk           -> completes with no writeback
"""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.init_db import init_db
from app.db.models import (
    Account,
    ClientNote,
    Contact,
    MeetingNote,
    Opportunity,
    RiskNote,
    SupportTicket,
    VectorDocument,
)
from app.db.session import SessionLocal
from app.services.embedding_service import get_embedding_provider
from app.utils.logging import get_logger

logger = get_logger(__name__)


def seed(session: Session) -> None:
    """Insert the demo dataset into the given session (idempotent)."""
    for model in [VectorDocument, MeetingNote, RiskNote, ClientNote, SupportTicket,
                  Contact, Opportunity, Account]:
        session.execute(delete(model))
    session.flush()

    session.add_all([
        Account(account_id="ACC-DEMO1", account_name="Northwind Trading", sector="Retail",
                revenue=120.0, employees=2400, office_location="United States",
                is_synthetic=True),
        Account(account_id="ACC-DEMO2", account_name="Initech", sector="Technology",
                revenue=80.0, employees=900, office_location="United States", is_synthetic=True),
    ])
    session.add_all([
        Contact(contact_id="CON-DEMO1", account_id="ACC-DEMO1", name="Dana Reed",
                email="dana@northwind.example", title="VP Ops", is_synthetic=True),
        Contact(contact_id="CON-DEMO2", account_id="ACC-DEMO2", name="Sam Lee",
                email="sam@initech.example", title="CTO", is_synthetic=True),
    ])
    session.add_all([
        # High-risk deal, missing close_date.
        Opportunity(opportunity_id="OPP-DEMO1", account_id="ACC-DEMO1", sales_agent="Moses Frase",
                    product="GTX Pro", stage="Engaging", deal_value=50000.0,
                    engage_date="2024-03-01", close_date=None, is_synthetic=True),
        # Clean, low-risk deal.
        Opportunity(opportunity_id="OPP-DEMO2", account_id="ACC-DEMO2", sales_agent="Darcel Schlecht",
                    product="MG Special", stage="Engaging", deal_value=15000.0,
                    engage_date="2024-04-01", close_date="2024-09-01", is_synthetic=True),
    ])
    session.add_all([
        SupportTicket(ticket_id="TCK-DEMO1", account_id="ACC-DEMO1", opportunity_id="OPP-DEMO1",
                      customer_name="Dana Reed", product_purchased="GTX Pro",
                      ticket_type="Technical issue", ticket_subject="Repeated outages",
                      ticket_status="Open", priority="Critical",
                      description="Customer reports critical outages and is threatening to cancel "
                      "and churn to a competitor due to unresolved escalation.",
                      resolution=None, customer_satisfaction=1.0, is_synthetic=True),
        SupportTicket(ticket_id="TCK-DEMO2", account_id="ACC-DEMO1", opportunity_id="OPP-DEMO1",
                      customer_name="Dana Reed", product_purchased="GTX Pro",
                      ticket_type="Billing inquiry", ticket_subject="Refund request",
                      ticket_status="Open", priority="High",
                      description="Client unhappy about delay and requesting a refund; complaint escalated.",
                      resolution=None, customer_satisfaction=2.0, is_synthetic=True),
        SupportTicket(ticket_id="TCK-DEMO3", account_id="ACC-DEMO2", opportunity_id="OPP-DEMO2",
                      customer_name="Sam Lee", product_purchased="MG Special",
                      ticket_type="Routine inquiry", ticket_subject="How-to question",
                      ticket_status="Closed", priority="Low",
                      description="Customer asked a routine how-to question; resolved happily.",
                      resolution="Provided documentation link; customer satisfied.",
                      customer_satisfaction=5.0, is_synthetic=True),
    ])
    session.add_all([
        RiskNote(note_id="RN-DEMO1", account_id="ACC-DEMO1", opportunity_id="OPP-DEMO1",
                 severity="high",
                 content="RISK: churn signal, competitor evaluation, escalated complaint.",
                 is_synthetic=True),
        ClientNote(note_id="CN-DEMO2", account_id="ACC-DEMO2", opportunity_id="OPP-DEMO2",
                   author="support_system", content="Client happy with onboarding.",
                   is_synthetic=True),
        MeetingNote(note_id="MN-DEMO1", account_id="ACC-DEMO1", opportunity_id="OPP-DEMO1",
                    meeting_date="2024-05-15", attendees="Northwind team; DealFlow AE",
                    content="Northwind frustrated with outages; competitor Acme under evaluation.",
                    is_synthetic=True),
    ])
    session.flush()
    _build_vectors(session)
    session.flush()
    logger.info("Demo dataset seeded.")


def _build_vectors(session: Session) -> None:
    embedder = get_embedding_provider()
    docs: list[VectorDocument] = []
    for t in session.query(SupportTicket).all():
        docs.append(VectorDocument(source_type="support_ticket", source_id=t.ticket_id,
                                   account_id=t.account_id, opportunity_id=t.opportunity_id,
                                   content=t.description, is_synthetic=True,
                                   doc_metadata={"priority": t.priority}))
    for n in session.query(RiskNote).all():
        docs.append(VectorDocument(source_type="risk_note", source_id=n.note_id,
                                   account_id=n.account_id, opportunity_id=n.opportunity_id,
                                   content=n.content, is_synthetic=True))
    for n in session.query(ClientNote).all():
        docs.append(VectorDocument(source_type="client_note", source_id=n.note_id,
                                   account_id=n.account_id, opportunity_id=n.opportunity_id,
                                   content=n.content, is_synthetic=True))
    for n in session.query(MeetingNote).all():
        docs.append(VectorDocument(source_type="meeting_note", source_id=n.note_id,
                                   account_id=n.account_id, opportunity_id=n.opportunity_id,
                                   content=n.content, is_synthetic=True))
    for doc, emb in zip(docs, embedder.embed_batch([d.content for d in docs]), strict=False):
        doc.embedding = emb
    session.add_all(docs)


def main() -> int:
    init_db()
    session = SessionLocal()
    try:
        seed(session)
        session.commit()
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
