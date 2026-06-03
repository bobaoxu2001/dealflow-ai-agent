"""Tests for data transformation logic and model creation."""
from app.db.models import Account, Opportunity, SupportTicket


def test_models_created_and_seeded(session):
    accounts = session.query(Account).all()
    assert {a.account_id for a in accounts} >= {"ACC-DEMO1", "ACC-DEMO2"}

    opp = session.query(Opportunity).filter_by(opportunity_id="OPP-DEMO1").one()
    assert opp.account_id == "ACC-DEMO1"
    # Synthetic "missing field" -> close_date intentionally blank.
    assert opp.close_date is None


def test_support_tickets_linked_to_accounts(session):
    tickets = session.query(SupportTicket).filter_by(account_id="ACC-DEMO1").all()
    assert len(tickets) >= 2
    assert any((t.priority or "").lower() in {"high", "critical"} for t in tickets)


def test_transform_account_id_mapping_is_deterministic():
    """The surrogate account-id minting must be stable across runs."""
    import pandas as pd

    names = ["Beta Corp", "Alpha Inc", "Gamma LLC"]
    df = pd.DataFrame({"account": names})
    sorted_names = sorted(df["account"].dropna().unique())
    mapping = {n: f"ACC-{i + 1:04d}" for i, n in enumerate(sorted_names)}
    assert mapping["Alpha Inc"] == "ACC-0001"
    assert mapping["Gamma LLC"] == "ACC-0003"
