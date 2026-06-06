"""The scan orchestrator: redact -> classify -> vector-search -> advise.

The whole pipeline is a single Weave op, so each scan shows up as one trace tree
in the Weave UI with every agent call nested underneath.
"""
from __future__ import annotations

import weave

from ..models import ScamVerdict, ScanRequest, ScanResult, SimilarScam
from ..services.redis_store import get_store
from . import advisor, classifier, redactor


@weave.op()
async def run_scan(req: ScanRequest) -> ScanResult:
    store = get_store()

    # 0. Cheap cache: skip re-paying for an unchanged screen (esp. the 30s loop).
    if req.image_b64:
        cached = store.cache_get(req.image_b64)
        if cached:
            return ScanResult(**cached)

    # 1. Privacy first.
    redaction = await redactor.redact(req.image_b64, req.context_text)

    # 2. Classify the screen for scams.
    verdict: ScamVerdict = await classifier.classify(req.image_b64, req.context_text)

    # 3. Compare detected text against known scams in Redis.
    similar: list[SimilarScam] = []
    if verdict.detected_text:
        similar = store.search_similar(verdict.detected_text, k=3)

    # 4. Generate plain-language advice + suggested actions.
    advice_out = await advisor.advise(verdict, similar)

    result = ScanResult(
        verdict=verdict.verdict,
        risk_score=verdict.risk_score,
        reasons=verdict.reasons,
        redaction=redaction,
        similar_scams=similar,
        suggested_actions=advice_out.suggested_actions,
        advice=advice_out.advice,
    )

    if req.image_b64:
        store.cache_set(req.image_b64, result.model_dump())
    return result
