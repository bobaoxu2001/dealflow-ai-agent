"""SQLAlchemy ORM models for the DealFlow AI Agent.

Logical groups:
  * CRM structured data  : accounts, contacts, opportunities, sales_teams, products
  * Support / unstructured: support_tickets, client_notes, risk_notes, meeting_notes
  * Retrieval            : vector_documents (embeddings)
  * Agent runtime        : agent_tasks, agent_audit_logs, crm_writebacks
"""
from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.vector import embedding_column_type


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# CRM structured data
# --------------------------------------------------------------------------- #
class SalesTeam(Base):
    __tablename__ = "sales_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sales_agent: Mapped[str] = mapped_column(String(255), index=True)
    manager: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regional_office: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product: Mapped[str] = mapped_column(String(255), index=True)
    series: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales_price: Mapped[float | None] = mapped_column(Float, nullable=True)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_name: Mapped[str] = mapped_column(String(255), index=True)
    sector: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year_established: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    office_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subsidiary_of: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="account")
    contacts: Mapped[list[Contact]] = relationship(back_populates="account")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.account_id"), index=True, nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    account: Mapped[Account] = relationship(back_populates="contacts")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.account_id"), index=True, nullable=True
    )
    sales_agent: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    product: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    deal_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    engage_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    close_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    account: Mapped[Account] = relationship(back_populates="opportunities")


# --------------------------------------------------------------------------- #
# Support / unstructured data
# --------------------------------------------------------------------------- #
class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.account_id"), index=True, nullable=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_purchased: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ticket_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ticket_subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ticket_status: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_satisfaction: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class ClientNote(Base):
    __tablename__ = "client_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.account_id"), index=True, nullable=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RiskNote(Base):
    __tablename__ = "risk_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.account_id"), index=True, nullable=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("accounts.account_id"), index=True, nullable=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    meeting_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attendees: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
class VectorDocument(Base):
    __tablename__ = "vector_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(embedding_column_type(), nullable=True)
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# --------------------------------------------------------------------------- #
# Agent runtime
# --------------------------------------------------------------------------- #
class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    user_task: Mapped[str] = mapped_column(Text)
    execution_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    approval_status: Mapped[str] = mapped_column(String(32), default="not_required", index=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    # Full serialized AgentState snapshot -> enables restart-safe resume.
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    audit_logs: Mapped[list[AgentAuditLog]] = relationship(
        back_populates="task", order_by="AgentAuditLog.id"
    )
    writebacks: Mapped[list[CRMWriteback]] = relationship(back_populates="task")


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.task_id"), index=True)
    node_name: Mapped[str] = mapped_column(String(64), index=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    task: Mapped[AgentTask] = relationship(back_populates="audit_logs")


class CRMWriteback(Base):
    __tablename__ = "crm_writebacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    writeback_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_tasks.task_id"), index=True, nullable=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="applied")
    applied_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    task: Mapped[AgentTask] = relationship(back_populates="writebacks")
