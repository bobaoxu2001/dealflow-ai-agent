"""Load processed CSVs into the database and build the vector index.

Idempotent: clears the loaded tables first, then inserts. Works against both
SQLite and PostgreSQL+pgvector (whatever DATABASE_URL points at).
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import delete

from app.db.init_db import init_db
from app.db.models import (
    Account,
    ClientNote,
    Contact,
    MeetingNote,
    Opportunity,
    Product,
    RiskNote,
    SalesTeam,
    SupportTicket,
    VectorDocument,
)
from app.db.session import SessionLocal
from app.services.embedding_service import get_embedding_provider
from app.utils.config import PROCESSED_DIR
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _read(name: str) -> pd.DataFrame | None:
    path = PROCESSED_DIR / name
    if not path.exists():
        logger.warning("Skipping %s (not found)", name)
        return None
    return pd.read_csv(path)


def _clean(value):
    if pd.isna(value):
        return None
    return value


def load_all() -> None:
    init_db()
    session = SessionLocal()
    try:
        # Clear in FK-safe order.
        for model in [
            VectorDocument, MeetingNote, RiskNote, ClientNote, SupportTicket,
            Contact, Opportunity, Account, Product, SalesTeam,
        ]:
            session.execute(delete(model))
        session.commit()

        _load_simple(session, "accounts.csv", Account, [
            "account_id", "account_name", "sector", "year_established", "revenue",
            "employees", "office_location", "subsidiary_of", "is_synthetic"])
        _load_simple(session, "products.csv", Product, ["product", "series", "sales_price"])
        _load_simple(session, "sales_teams.csv", SalesTeam,
                     ["sales_agent", "manager", "regional_office"])
        _load_simple(session, "contacts.csv", Contact,
                     ["contact_id", "account_id", "name", "email", "title", "is_synthetic"])
        _load_simple(session, "opportunities.csv", Opportunity, [
            "opportunity_id", "account_id", "sales_agent", "product", "stage",
            "deal_value", "engage_date", "close_date", "is_synthetic"])
        _load_simple(session, "support_tickets.csv", SupportTicket, [
            "ticket_id", "account_id", "opportunity_id", "customer_name",
            "product_purchased", "ticket_type", "ticket_subject", "ticket_status",
            "priority", "description", "resolution", "customer_satisfaction", "is_synthetic"])
        _load_simple(session, "client_notes.csv", ClientNote, [
            "note_id", "account_id", "opportunity_id", "author", "content", "is_synthetic"])
        _load_simple(session, "risk_notes.csv", RiskNote, [
            "note_id", "account_id", "opportunity_id", "severity", "content", "is_synthetic"])
        _load_simple(session, "meeting_notes.csv", MeetingNote, [
            "note_id", "account_id", "opportunity_id", "meeting_date", "attendees",
            "content", "is_synthetic"])
        session.commit()

        _apply_missing_fields(session)
        _build_vector_index(session)
        session.commit()
        logger.info("Load complete.")
    finally:
        session.close()


def _load_simple(session, filename, model, columns) -> None:
    df = _read(filename)
    if df is None:
        return
    available = [c for c in columns if c in df.columns]
    objs = []
    for _, row in df.iterrows():
        objs.append(model(**{c: _clean(row[c]) for c in available}))
    session.add_all(objs)
    logger.info("Loaded %d rows into %s", len(objs), model.__tablename__)


def _apply_missing_fields(session) -> None:
    df = _read("missing_crm_fields.csv")
    if df is None or df.empty:
        return
    count = 0
    for _, row in df.iterrows():
        opp = session.query(Opportunity).filter_by(opportunity_id=row["opportunity_id"]).first()
        if opp and hasattr(opp, row["missing_field"]):
            setattr(opp, row["missing_field"], None)
            count += 1
    logger.info("Applied %d synthetic missing-field blanks", count)


def _build_vector_index(session) -> None:
    embedder = get_embedding_provider()
    docs: list[VectorDocument] = []

    def add(source_type, source_id, account_id, opportunity_id, content, is_synthetic, meta=None):
        if not content or pd.isna(content):
            return
        docs.append(
            VectorDocument(
                source_type=source_type,
                source_id=str(source_id) if source_id is not None else None,
                account_id=_clean(account_id),
                opportunity_id=_clean(opportunity_id),
                content=str(content),
                doc_metadata=meta or {},
                is_synthetic=is_synthetic,
            )
        )

    for t in session.query(SupportTicket).all():
        add("support_ticket", t.ticket_id, t.account_id, t.opportunity_id,
            t.description, False, {"priority": t.priority, "status": t.ticket_status})
        if t.resolution:
            add("ticket_resolution", t.ticket_id, t.account_id, t.opportunity_id,
                t.resolution, False)
    for n in session.query(ClientNote).all():
        add("client_note", n.note_id, n.account_id, n.opportunity_id, n.content, True)
    for n in session.query(RiskNote).all():
        add("risk_note", n.note_id, n.account_id, n.opportunity_id, n.content, True,
            {"severity": n.severity})
    for n in session.query(MeetingNote).all():
        add("meeting_note", n.note_id, n.account_id, n.opportunity_id, n.content, True)

    # Embed in batch.
    embeddings = embedder.embed_batch([d.content for d in docs])
    for doc, emb in zip(docs, embeddings, strict=False):
        doc.embedding = emb
    session.add_all(docs)
    logger.info("Built %d vector documents", len(docs))


if __name__ == "__main__":
    load_all()
