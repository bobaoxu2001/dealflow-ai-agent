"""Read/write access to structured CRM records."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Contact, Opportunity, SupportTicket
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CRMService:
    def __init__(self, session: Session):
        self.session = session

    def get_opportunity(self, opportunity_id: str) -> Opportunity | None:
        return self.session.execute(
            select(Opportunity).where(Opportunity.opportunity_id == opportunity_id)
        ).scalar_one_or_none()

    def get_account(self, account_id: str) -> Account | None:
        return self.session.execute(
            select(Account).where(Account.account_id == account_id)
        ).scalar_one_or_none()

    def get_account_contacts(self, account_id: str) -> list[Contact]:
        return list(
            self.session.execute(
                select(Contact).where(Contact.account_id == account_id)
            ).scalars()
        )

    def get_account_tickets(self, account_id: str, limit: int = 50) -> list[SupportTicket]:
        return list(
            self.session.execute(
                select(SupportTicket)
                .where(SupportTicket.account_id == account_id)
                .limit(limit)
            ).scalars()
        )

    def get_opportunity_context(self, opportunity_id: str) -> dict:
        """Assemble a structured snapshot used both by the API and the agent."""
        opp = self.get_opportunity(opportunity_id)
        if opp is None:
            return {}
        account = self.get_account(opp.account_id) if opp.account_id else None
        contacts = self.get_account_contacts(opp.account_id) if opp.account_id else []
        tickets = self.get_account_tickets(opp.account_id) if opp.account_id else []
        return {
            "opportunity": _opp_dict(opp),
            "account": _account_dict(account) if account else None,
            "contacts": [_contact_dict(c) for c in contacts],
            "ticket_summary": {
                "total": len(tickets),
                "open": sum(1 for t in tickets if (t.ticket_status or "").lower() != "closed"),
                "high_priority": sum(
                    1 for t in tickets if (t.priority or "").lower() in {"high", "critical"}
                ),
            },
        }

    def apply_opportunity_update(self, opportunity_id: str, changes: dict) -> dict:
        """Apply a validated set of field changes to an opportunity."""
        opp = self.get_opportunity(opportunity_id)
        if opp is None:
            raise ValueError(f"Opportunity {opportunity_id} not found")
        applied: dict[str, dict] = {}
        editable = {"stage", "deal_value", "close_date", "product", "sales_agent"}
        for field, new_value in changes.items():
            if field not in editable:
                continue
            old_value = getattr(opp, field)
            setattr(opp, field, new_value)
            applied[field] = {"old": old_value, "new": new_value}
        self.session.add(opp)
        self.session.flush()
        return applied


def _opp_dict(o: Opportunity) -> dict:
    return {
        "opportunity_id": o.opportunity_id,
        "account_id": o.account_id,
        "sales_agent": o.sales_agent,
        "product": o.product,
        "stage": o.stage,
        "deal_value": o.deal_value,
        "engage_date": o.engage_date,
        "close_date": o.close_date,
    }


def _account_dict(a: Account) -> dict:
    return {
        "account_id": a.account_id,
        "account_name": a.account_name,
        "sector": a.sector,
        "revenue": a.revenue,
        "employees": a.employees,
        "office_location": a.office_location,
    }


def _contact_dict(c: Contact) -> dict:
    return {"contact_id": c.contact_id, "name": c.name, "email": c.email, "title": c.title}
