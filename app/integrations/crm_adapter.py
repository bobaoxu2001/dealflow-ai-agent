"""Pluggable CRM adapter layer.

The agent reads CRM context and (after human approval) writes back through a CRM
*adapter*, so the same workflow can target different CRM backends:

  * ``local``         - the project's own PostgreSQL/SQLite store (DEFAULT)
  * ``mock_external`` - a simulated external CRM (no network) for demos/tests
  * ``hubspot``       - the real HubSpot CRM v3 API (opt-in)

Safety guarantees (do not weaken):
  * The default is ``local``; nothing external is contacted unless explicitly
    configured via ``CRM_ADAPTER``.
  * The HubSpot adapter is **dry-run by default** — it will not send a PATCH
    unless ``HUBSPOT_DRY_RUN=false``.
  * Real writeback uses a strict field allowlist and rejects everything else.
  * Access tokens are never logged.
  * This layer does not change *who* may write: human approval still gates every
    writeback in the agent graph. The LLM cannot reach this layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.services.crm_service import (
    CRMService,
    _account_dict,
    _opp_dict,
)
from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CRMAdapterError(Exception):
    """Raised for CRM adapter configuration or upstream API errors."""


class UnsafeFieldError(CRMAdapterError):
    """Raised when a writeback attempts to modify a non-allowlisted field."""


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class BaseCRMAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def get_opportunity(self, opportunity_id: str) -> dict | None:
        ...

    @abstractmethod
    def get_account(self, account_id: str) -> dict | None:
        ...

    @abstractmethod
    def get_context(self, opportunity_id: str) -> dict:
        ...

    @abstractmethod
    def apply_writeback(
        self, opportunity_id: str, changes: dict, idempotency_key: str | None = None
    ) -> dict:
        ...


# --------------------------------------------------------------------------- #
# Local (default) — the project's own database
# --------------------------------------------------------------------------- #
class LocalDatabaseCRMAdapter(BaseCRMAdapter):
    name = "local"

    def __init__(self, session: Session):
        self.crm = CRMService(session)

    def get_opportunity(self, opportunity_id: str) -> dict | None:
        opp = self.crm.get_opportunity(opportunity_id)
        return _opp_dict(opp) if opp else None

    def get_account(self, account_id: str) -> dict | None:
        acct = self.crm.get_account(account_id)
        return _account_dict(acct) if acct else None

    def get_context(self, opportunity_id: str) -> dict:
        return self.crm.get_opportunity_context(opportunity_id)

    def apply_writeback(
        self, opportunity_id: str, changes: dict, idempotency_key: str | None = None
    ) -> dict:
        applied = self.crm.apply_opportunity_update(opportunity_id, changes) if changes else {}
        return {
            "adapter": self.name,
            "opportunity_id": opportunity_id,
            "status": "applied",
            "dry_run": False,
            "applied": applied,
            "idempotency_key": idempotency_key,
        }


# --------------------------------------------------------------------------- #
# Mock external — simulates a remote CRM without any network
# --------------------------------------------------------------------------- #
class MockExternalCRMAdapter(BaseCRMAdapter):
    """Reads from the local store but presents itself as an external CRM and
    simulates writeback in-memory (no DB mutation). Useful for demoing the
    external-adapter contract deterministically and for CI."""

    name = "mock_external"

    def __init__(self, session: Session):
        self.crm = CRMService(session)
        self._writes: list[dict] = []

    def get_opportunity(self, opportunity_id: str) -> dict | None:
        opp = self.crm.get_opportunity(opportunity_id)
        if not opp:
            return None
        d = _opp_dict(opp)
        d["source"] = "mock_external"
        return d

    def get_account(self, account_id: str) -> dict | None:
        acct = self.crm.get_account(account_id)
        if not acct:
            return None
        d = _account_dict(acct)
        d["source"] = "mock_external"
        return d

    def get_context(self, opportunity_id: str) -> dict:
        ctx = self.crm.get_opportunity_context(opportunity_id)
        ctx["source"] = "mock_external"
        return ctx

    def apply_writeback(
        self, opportunity_id: str, changes: dict, idempotency_key: str | None = None
    ) -> dict:
        # Simulate the external system applying the change (no local DB write).
        applied = {k: {"old": None, "new": v} for k, v in (changes or {}).items()}
        record = {
            "adapter": self.name,
            "opportunity_id": opportunity_id,
            "status": "applied",
            "dry_run": False,
            "applied": applied,
            "idempotency_key": idempotency_key,
        }
        self._writes.append(record)
        return record


# --------------------------------------------------------------------------- #
# HubSpot — real CRM v3 API (opt-in, dry-run by default)
# --------------------------------------------------------------------------- #
# Map the project's internal field names -> HubSpot deal property names. Only
# these fields may ever be written; everything else is rejected.
_INTERNAL_TO_HUBSPOT = {
    "stage": "dealstage",
    "deal_value": "amount",
    "close_date": "closedate",
    "dealflow_ai_status": "dealflow_ai_status",
}
_ALLOWED_HUBSPOT_PROPERTIES = set(_INTERNAL_TO_HUBSPOT.values())  # the strict allowlist


class HubSpotCRMAdapter(BaseCRMAdapter):
    name = "hubspot"

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str | None = None,
        dry_run: bool | None = None,
        timeout: int | None = None,
        client=None,
    ):
        token = access_token if access_token is not None else settings.hubspot_access_token
        if not token:
            raise CRMAdapterError(
                "HUBSPOT_ACCESS_TOKEN is required to use the HubSpot CRM adapter. "
                "Set it in your environment, or use CRM_ADAPTER=local (default) / "
                "CRM_ADAPTER=mock_external. No token is committed to the repo."
            )
        self._dry_run = settings.hubspot_dry_run if dry_run is None else dry_run
        self._base_url = base_url or settings.hubspot_base_url
        self._timeout = timeout or settings.hubspot_timeout_seconds
        # Allow dependency injection of a client (tests use httpx.MockTransport).
        if client is not None:
            self.client = client
        else:
            import httpx

            self.client = httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {token}",  # never logged
                    "Content-Type": "application/json",
                },
            )

    # -- read --------------------------------------------------------------- #
    def get_opportunity(self, opportunity_id: str) -> dict | None:
        resp = self.client.get(
            f"/crm/v3/objects/deals/{opportunity_id}",
            params={
                "properties": "dealname,dealstage,amount,closedate",
                "associations": "companies",
            },
        )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp, context=f"get deal {opportunity_id}")
        return self._normalize_deal(resp.json())

    def get_account(self, account_id: str) -> dict | None:
        resp = self.client.get(
            f"/crm/v3/objects/companies/{account_id}",
            params={"properties": "name,industry,country"},
        )
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp, context=f"get company {account_id}")
        return self._normalize_company(resp.json())

    def get_context(self, opportunity_id: str) -> dict:
        opp = self.get_opportunity(opportunity_id)
        account = None
        if opp and opp.get("account_id"):
            try:
                account = self.get_account(opp["account_id"])
            except CRMAdapterError:
                account = None  # context is best-effort; never fail the read on it
        return {"opportunity": opp, "account": account, "source": "hubspot"}

    # -- write -------------------------------------------------------------- #
    def apply_writeback(
        self, opportunity_id: str, changes: dict, idempotency_key: str | None = None
    ) -> dict:
        hs_properties = self._validate_and_map(changes or {})

        if self._dry_run:
            logger.info(
                "HubSpot DRY-RUN writeback for deal %s (no PATCH sent): %s",
                opportunity_id,
                sorted(hs_properties.keys()),
            )
            return {
                "adapter": self.name,
                "opportunity_id": opportunity_id,
                "status": "dry_run",
                "dry_run": True,
                "proposed": hs_properties,
                "applied": {},
                "idempotency_key": idempotency_key,
                "detail": "HUBSPOT_DRY_RUN=true; no write was sent to HubSpot.",
            }

        resp = self.client.patch(
            f"/crm/v3/objects/deals/{opportunity_id}",
            json={"properties": hs_properties},
        )
        self._raise_for_status(resp, context=f"patch deal {opportunity_id}")
        return {
            "adapter": self.name,
            "opportunity_id": opportunity_id,
            "status": "applied",
            "dry_run": False,
            "applied": hs_properties,
            "idempotency_key": idempotency_key,
            "detail": "PATCH applied to HubSpot.",
        }

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _validate_and_map(changes: dict) -> dict:
        """Map internal/HubSpot field names to allowlisted HubSpot properties.

        Rejects any field that is not in the strict allowlist.
        """
        hs: dict = {}
        for key, value in changes.items():
            if key in _INTERNAL_TO_HUBSPOT:
                hs[_INTERNAL_TO_HUBSPOT[key]] = value
            elif key in _ALLOWED_HUBSPOT_PROPERTIES:
                hs[key] = value
            else:
                raise UnsafeFieldError(
                    f"Field {key!r} is not allowed for HubSpot writeback. "
                    f"Allowed internal fields: {sorted(_INTERNAL_TO_HUBSPOT)}; "
                    f"allowed HubSpot properties: {sorted(_ALLOWED_HUBSPOT_PROPERTIES)}."
                )
        return hs

    @staticmethod
    def _normalize_deal(payload: dict) -> dict:
        props = payload.get("properties", {}) or {}
        amount = props.get("amount")
        try:
            deal_value = float(amount) if amount not in (None, "") else None
        except (TypeError, ValueError):
            deal_value = None
        account_id = None
        assoc = (payload.get("associations") or {}).get("companies", {})
        results = assoc.get("results") or []
        if results:
            account_id = str(results[0].get("id")) if results[0].get("id") else None
        return {
            "opportunity_id": str(payload.get("id")),
            "name": props.get("dealname"),
            "stage": props.get("dealstage"),
            "deal_value": deal_value,
            "close_date": props.get("closedate"),
            "account_id": account_id,
            "source": "hubspot",
        }

    @staticmethod
    def _normalize_company(payload: dict) -> dict:
        props = payload.get("properties", {}) or {}
        return {
            "account_id": str(payload.get("id")),
            "account_name": props.get("name"),
            "sector": props.get("industry"),
            "office_location": props.get("country"),
            "source": "hubspot",
        }

    @staticmethod
    def _raise_for_status(resp, context: str) -> None:
        code = resp.status_code
        if code < 400:
            return
        # Clear, token-free error messages per status class.
        if code == 401:
            raise CRMAdapterError(f"HubSpot auth failed (401) on {context}: invalid/expired token.")
        if code == 403:
            raise CRMAdapterError(
                f"HubSpot forbidden (403) on {context}: token lacks required scopes."
            )
        if code == 404:
            raise CRMAdapterError(f"HubSpot resource not found (404) on {context}.")
        if code == 429:
            retry_after = resp.headers.get("Retry-After", "unknown")
            raise CRMAdapterError(
                f"HubSpot rate limited (429) on {context}; retry-after={retry_after}s."
            )
        if code >= 500:
            raise CRMAdapterError(f"HubSpot server error ({code}) on {context}; retry later.")
        raise CRMAdapterError(f"HubSpot request failed ({code}) on {context}.")


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def get_crm_adapter(session: Session) -> BaseCRMAdapter:
    """Return the configured CRM adapter. Defaults to the local database."""
    adapter = (settings.crm_adapter or "local").lower()
    if adapter == "hubspot":
        return HubSpotCRMAdapter()
    if adapter == "mock_external":
        return MockExternalCRMAdapter(session)
    return LocalDatabaseCRMAdapter(session)
