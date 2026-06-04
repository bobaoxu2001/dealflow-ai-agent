"""Tests for the optional LLM final-synthesis layer (local fallback)."""
from app.services.llm_service import LocalLLMProvider, get_llm_provider


def test_local_llm_provider_is_default_and_keyfree():
    provider = get_llm_provider()
    # With no OPENAI_API_KEY configured, we must get the deterministic local one.
    assert provider.name == "local"


def test_local_synthesis_is_deterministic_and_grounded():
    p = LocalLLMProvider()
    report = {
        "opportunity_id": "OPP-DEMO1",
        "account_id": "ACC-DEMO1",
        "risk_score": 0.9,
        "risk_flags": [{"type": "signal", "detail": "'churn' x1"}],
        "missing_fields": ["close_date"],
        "recommended_actions": ["Escalate to deal-desk."],
        "crm_update": {"changes": {"stage": "On Hold"}},
        "approval_status": "approved",
        "documents_reviewed": 4,
    }
    a = p.synthesize_report(report)
    b = p.synthesize_report(report)
    assert a == b  # deterministic
    assert "OPP-DEMO1" in a
    assert "HIGH" in a  # 0.9 >= threshold
    assert "stage -> On Hold" in a


def test_finalize_report_includes_executive_summary(client):
    body = client.post(
        "/agent/review-opportunity",
        json={"opportunity_id": "OPP-DEMO2", "task": "summary check"},
    ).json()
    report = body["final_report"]
    assert report.get("executive_summary")
    assert report.get("synthesized_by") == "local"
