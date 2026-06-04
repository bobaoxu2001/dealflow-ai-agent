"""Tests for the pluggable CRM adapter layer (local / mock_external / hubspot).

HubSpot tests use httpx.MockTransport — no real network, no real token.
"""
import httpx
import pytest

from app.integrations.crm_adapter import (
    CRMAdapterError,
    HubSpotCRMAdapter,
    LocalDatabaseCRMAdapter,
    MockExternalCRMAdapter,
    UnsafeFieldError,
    get_crm_adapter,
)

SAMPLE_DEAL = {
    "id": "123456",
    "properties": {
        "dealname": "Acme expansion",
        "dealstage": "presentationscheduled",
        "amount": "50000",
        "closedate": "2024-12-01",
    },
    "associations": {"companies": {"results": [{"id": "987"}]}},
}
SAMPLE_COMPANY = {
    "id": "987",
    "properties": {"name": "Acme Corp", "industry": "TECHNOLOGY", "country": "United States"},
}


# --------------------------------------------------------------------------- #
# Factory + local
# --------------------------------------------------------------------------- #
def test_factory_defaults_to_local(session):
    adapter = get_crm_adapter(session)
    assert isinstance(adapter, LocalDatabaseCRMAdapter)
    assert adapter.name == "local"


def test_local_adapter_reads_and_writes(session):
    adapter = LocalDatabaseCRMAdapter(session)
    ctx = adapter.get_context("OPP-DEMO1")
    assert ctx["opportunity"]["opportunity_id"] == "OPP-DEMO1"
    assert adapter.get_opportunity("OPP-DEMO1")["account_id"] == "ACC-DEMO1"

    # Write a benign, non-routing field on the low-risk demo opp.
    result = adapter.apply_writeback("OPP-DEMO2", {"product": "GTX Pro"})
    assert result["adapter"] == "local"
    assert result["dry_run"] is False
    assert result["applied"]["product"]["new"] == "GTX Pro"


# --------------------------------------------------------------------------- #
# Mock external
# --------------------------------------------------------------------------- #
def test_mock_external_adapter_works(session):
    adapter = MockExternalCRMAdapter(session)
    opp = adapter.get_opportunity("OPP-DEMO1")
    assert opp["opportunity_id"] == "OPP-DEMO1"
    assert opp["source"] == "mock_external"

    result = adapter.apply_writeback("OPP-DEMO1", {"stage": "On Hold"})
    assert result["adapter"] == "mock_external"
    assert result["status"] == "applied"
    assert result["applied"]["stage"]["new"] == "On Hold"


# --------------------------------------------------------------------------- #
# HubSpot (mocked transport)
# --------------------------------------------------------------------------- #
def _hubspot_with_mock(dry_run: bool):
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path.startswith("/crm/v3/objects/deals/"):
            return httpx.Response(200, json=SAMPLE_DEAL)
        if request.method == "GET" and request.url.path.startswith("/crm/v3/objects/companies/"):
            return httpx.Response(200, json=SAMPLE_COMPANY)
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": "123456", "properties": {}})
        return httpx.Response(404, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.hubapi.com")
    adapter = HubSpotCRMAdapter(access_token="test-token", dry_run=dry_run, client=client)
    return adapter, calls


def test_hubspot_missing_token_gives_clear_error():
    with pytest.raises(CRMAdapterError) as exc:
        HubSpotCRMAdapter(access_token=None)
    assert "HUBSPOT_ACCESS_TOKEN" in str(exc.value)


def test_hubspot_normalizes_deal_response():
    adapter, _ = _hubspot_with_mock(dry_run=True)
    opp = adapter.get_opportunity("123456")
    assert opp["opportunity_id"] == "123456"
    assert opp["stage"] == "presentationscheduled"
    assert opp["deal_value"] == 50000.0  # string -> float
    assert opp["close_date"] == "2024-12-01"
    assert opp["account_id"] == "987"
    assert opp["source"] == "hubspot"


def test_hubspot_dry_run_does_not_patch():
    adapter, calls = _hubspot_with_mock(dry_run=True)
    result = adapter.apply_writeback("123456", {"stage": "closedwon", "deal_value": 60000})
    assert result["dry_run"] is True
    assert result["status"] == "dry_run"
    # internal names were mapped to HubSpot property names
    assert result["proposed"] == {"dealstage": "closedwon", "amount": 60000}
    assert all(method != "PATCH" for method, _ in calls), "dry-run must not send PATCH"


def test_hubspot_real_patch_when_dry_run_disabled():
    adapter, calls = _hubspot_with_mock(dry_run=False)
    result = adapter.apply_writeback("123456", {"stage": "closedwon"}, idempotency_key="k1")
    assert result["dry_run"] is False
    assert result["status"] == "applied"
    assert result["applied"] == {"dealstage": "closedwon"}
    assert any(method == "PATCH" for method, _ in calls), "real writeback must send PATCH"


def test_hubspot_rejects_unsafe_fields():
    adapter, calls = _hubspot_with_mock(dry_run=False)
    with pytest.raises(UnsafeFieldError):
        adapter.apply_writeback("123456", {"owner_id": "hacker", "stage": "closedwon"})
    assert all(method != "PATCH" for method, _ in calls), "must not PATCH when a field is unsafe"


def test_hubspot_error_mapping_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.hubapi.com")
    adapter = HubSpotCRMAdapter(access_token="test-token", client=client)
    with pytest.raises(CRMAdapterError) as exc:
        adapter.get_opportunity("123456")
    assert "401" in str(exc.value)
