"""LLM provider abstraction for *final report synthesis only*.

Design intent (important for AI Engineer interviews):
  * The agent's control flow, risk scoring, approval routing, and CRM writeback
    are 100% deterministic and auditable. An LLM is **never** allowed to decide a
    writeback or bypass human approval.
  * The LLM only turns the already-computed structured report (risk flags,
    missing fields, recommended actions, draft) into a readable narrative.
  * The default provider is deterministic and key-free, so tests and local demos
    run with no API key. Set LLM_PROVIDER=openai (+ OPENAI_API_KEY) to opt in.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def synthesize_report(self, report: dict) -> str:
        """Return a human-readable narrative summary of a structured report."""


class LocalLLMProvider(LLMProvider):
    """Deterministic, dependency-free narrative generator (no API key)."""

    name = "local"

    def synthesize_report(self, report: dict) -> str:
        opp = report.get("opportunity_id", "?")
        acct = report.get("account_id") or "unknown account"
        risk = report.get("risk_score", 0.0)
        flags = report.get("risk_flags", []) or []
        missing = report.get("missing_fields", []) or []
        actions = report.get("recommended_actions", []) or []
        crm = report.get("crm_update", {}) or {}
        approval = report.get("approval_status", "n/a")
        docs = report.get("documents_reviewed", 0)

        band = "HIGH" if risk >= settings.high_risk_threshold else ("MODERATE" if risk >= 0.3 else "LOW")
        flag_str = "; ".join(f"{f.get('type')} ({f.get('detail')})" for f in flags) or "none"
        changes = (crm.get("changes") or {})
        change_str = ", ".join(f"{k} -> {v}" for k, v in changes.items()) or "no field changes proposed"

        lines = [
            f"Opportunity {opp} (account {acct}) was reviewed against {docs} retrieved "
            f"support/context documents. Overall deal risk is {band} (score {risk}).",
            f"Risk signals: {flag_str}.",
            f"Missing CRM fields: {', '.join(missing) if missing else 'none'}.",
            f"Proposed CRM update: {change_str} (approval status: {approval}).",
            "Recommended next steps: " + ("; ".join(actions) if actions else "advance as normal."),
        ]
        return " ".join(lines)


class OpenAILLMProvider(LLMProvider):
    """Optional real LLM synthesis. Only used when explicitly configured."""

    name = "openai"

    def __init__(self):
        from openai import OpenAI  # imported lazily so it's not a hard dep

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model
        self._fallback = LocalLLMProvider()

    def synthesize_report(self, report: dict) -> str:
        prompt = (
            "You are a B2B sales operations analyst. Write a concise (3-5 sentence) "
            "executive summary of this opportunity review for a sales manager. Do NOT "
            "invent facts; only use the structured data provided. Do not recommend "
            "writing to the CRM yourself.\n\n"
            f"{report}"
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=300,
            )
            return resp.choices[0].message.content.strip()
        except Exception:  # pragma: no cover - network/provider errors
            logger.exception("OpenAI synthesis failed; using local fallback.")
            return self._fallback.synthesize_report(report)


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        logger.info("Using OpenAI LLM provider (%s) for report synthesis.", settings.llm_model)
        return OpenAILLMProvider()
    if settings.llm_provider == "openai":
        logger.warning("LLM_PROVIDER=openai but no OPENAI_API_KEY; using local synthesis.")
    return LocalLLMProvider()
