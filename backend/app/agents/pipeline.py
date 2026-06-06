"""The scan orchestrator: redact + collect -> research -> decide.

Stages:
  1. PrivacyRedactor  — flag sensitive info (runs in parallel with collection).
  2. CollectDataAgent — extract structured facts from the screen (observation only).
  3. ResearchAgent    — gather grounded comparison evidence (web + Redis scam/legit).
  4. Advisor          — final verdict + advice + actions, with full context.

The whole pipeline is one Weave op, so each scan is a single trace tree with every
agent call nested underneath.
"""
from __future__ import annotations

import asyncio

import weave

from ..models import ScanRequest, ScanResult
from ..services.redis_store import RedisStore, get_store
from . import advisor, collector, redactor, researcher


def _lookup_trust(store: RedisStore, sender_address: str) -> bool | None:
    """Check the full address first, then fall back to its domain. None = unknown."""
    if not sender_address:
        return None
    by_address = store.get_contact(sender_address.lower())
    if by_address is not None:
        return by_address
    if "@" in sender_address:
        domain = sender_address.split("@")[-1].lower()
        return store.get_contact(domain)
    return None


@weave.op()
async def run_scan(req: ScanRequest) -> ScanResult:
    store = get_store()

    # 0. Cheap cache: skip re-paying for an unchanged screen (esp. the 30s loop).
    if req.image_b64:
        cached = store.cache_get(req.image_b64)
        if cached:
            return ScanResult(**cached)

    # 1 + 2. Privacy check and fact collection are independent — run them together.
    redaction, facts = await asyncio.gather(
        redactor.redact(req.image_b64, req.context_text),
        collector.collect(req.image_b64, req.context_text),
    )

    # Trusted-contacts is a SOFT signal only — it never skips analysis. The agents
    # always research and inspect the content (a trusted account can be compromised
    # or spoofed); trust merely nudges the prior and can be overridden by red flags.
    trusted = _lookup_trust(store, facts.sender_address)

    # 3. Research the facts: grounded scam/legit comparison + web vetting.
    research, similar_scams, similar_legit = await researcher.research(facts)

    trust_note = ""
    if trusted is True:
        trust_note = (
            f"The user previously marked '{facts.sender_address}' as TRUSTED. Treat this as a mild "
            "positive prior ONLY — still judge the actual content and override it if you see real red flags."
        )
    elif trusted is False:
        trust_note = f"The user previously marked '{facts.sender_address}' as UNTRUSTED. Weigh this as a real negative signal."

    # 4. Final decision with the full picture (looks at the image again).
    decision = await advisor.decide(
        req.image_b64, facts, research, similar_scams, similar_legit, trust_note=trust_note
    )

    result = ScanResult(
        verdict=decision.verdict.verdict,
        risk_score=decision.verdict.risk_score,
        reasons=decision.verdict.reasons,
        advice=decision.verdict.advice,
        redaction=redaction,
        suggested_actions=decision.suggested_actions,
        similar_scams=similar_scams,
        similar_legit=similar_legit,
        trusted_sender=trusted,
        facts=facts,
        research=research,
    )

    if req.image_b64:
        store.cache_set(req.image_b64, result.model_dump())
    return result


@weave.op()
async def assess_text(context_text: str) -> ScanResult:
    """Text-only path (no screenshot) used by the eval harness and the /advisor flow."""
    return await run_scan(ScanRequest(image_b64=None, context_text=context_text, source="manual"))
