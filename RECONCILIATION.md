# Backend reconciliation: one detection engine, not two

After merging `brendan` → `main`, the backend ended up with **two parallel scam-detection
implementations**. This doc explains the overlap and proposes a small, surgical integration
so we keep all the good infrastructure and use the stronger detection engine.

> Shared code — let's agree on this before editing `main`. Suggest doing it on a branch + PR.

## What overlaps today

| Concern | GaelGil's version (full-stack template) | Brendan's version (agents) |
|---|---|---|
| Entry point | `app/main.py` → `app/api/main.py` routers | (old flat `/scan` endpoints, now superseded) |
| **Detection** | `ScanService.analyze_scan` → `openai_service.analyze_image_bytes` (one-shot vision) → `_finalize_verdict` (confidence thresholds) | `app/agents/pipeline.run_scan` → redact ∥ collect → **research (web + Redis)** → advise (calibrated) |
| Persistence | Postgres via `sqlmodel` (`Scan` table), alembic | none (stateless) |
| Realtime | websocket `ConnectionManager` | none |
| Vector store | `RedisScamVectorStore` (index `scam_vectors`) | `services/redis_store` (index `example_idx`, scam+legit) |
| Config | `app/core/config.py` (`../.env`, Postgres) | `app/config.py` (`./.env`) |
| Trusted contacts | DB + `contact_store` per session | `redis_store` contacts (soft signal) |

The main user flow — `POST /api/v1/scans/` → `analyze_scan` — uses **GaelGil's one-shot
classifier**. That's the exact approach whose false positives we fixed this week (e.g. the
legit WeaveHacks/Luma email scored 60% risk). Brendan's multi-agent pipeline is only reachable
through the side endpoint `POST /api/v1/scans/scan`, so the real flow doesn't benefit from it.

## Proposal: make the pipeline the engine inside `ScanService`

Keep **everything** GaelGil built (DB, websockets, trusted contacts, frontend contract). Change
only the detection core of `ScanService.analyze_scan`: instead of `analyze_image_bytes` +
`_finalize_verdict`, call `pipeline.run_scan(...)` and map the `ScanResult` onto the `Scan` row.

### Field mapping: `ScanResult` → `Scan` (DB)

| `Scan` column | from `ScanResult` |
|---|---|
| `summary` | `advice` |
| `is_scam` | `verdict == "scam"` |
| `risk_level` | `scam → HIGH`, `suspicious → MEDIUM`, `safe → LOW` |
| `confidence_score` | `risk_score` |
| `scam_type` | top `similar_scams[0].category` if any else `"unknown"` |
| `impersonated_brand` | `facts.brand_claimed or None` |
| `detected_text` | `facts.raw_text` |
| `detected_urls` | `facts.links` |
| `evidence` | `reasons + research.scam_indicators` |
| `extracted_details` | `facts.model_dump()` (+ `research.model_dump()`) |
| `similar_scams` | `[s.model_dump() for s in similar_scams]` |
| `recommended_actions` | `[f"{a.label}: {a.detail}" for a in suggested_actions]` |

### Code sketch (`app/api/scamdetect/ScanService.py`)

```python
import base64
from app.agents import pipeline
from app.models import ScanRequest as AgentScanRequest
from app.models import ScanResult as AgentScanResult

_RISK = {"scam": ScanRiskLevel.HIGH, "suspicious": ScanRiskLevel.MEDIUM, "safe": ScanRiskLevel.LOW}

def _result_to_scan_fields(r: AgentScanResult) -> dict:
    facts = r.facts
    return dict(
        status=ScanStatus.COMPLETE,
        summary=r.advice,
        is_scam=(r.verdict == "scam"),
        risk_level=_RISK.get(r.verdict, ScanRiskLevel.LOW),
        confidence_score=r.risk_score,
        scam_type=(r.similar_scams[0].category if r.similar_scams else "unknown"),
        impersonated_brand=(facts.brand_claimed or None) if facts else None,
        detected_text=(facts.raw_text if facts else ""),
        detected_urls=(facts.links if facts else []),
        evidence=[*r.reasons, *(r.research.scam_indicators if r.research else [])],
        extracted_details={"facts": facts.model_dump() if facts else {},
                           "research": r.research.model_dump() if r.research else {}},
        similar_scams=[s.model_dump() for s in r.similar_scams],
        recommended_actions=[f"{a.label}: {a.detail}" for a in r.suggested_actions],
    )

async def analyze_scan(self, scan_id, image_bytes, content_type) -> None:
    with Session(engine) as session:
        scan = session.get(Scan, scan_id)
        if not scan:
            return
        try:
            # ...keep the size check + status=IN_PROGRESS + scan_started event...
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            result = await pipeline.run_scan(
                AgentScanRequest(image_b64=image_b64, context_text=scan.source_text or "")
            )
            fields = _result_to_scan_fields(result)

            refreshed = session.get(Scan, scan_id)
            for k, v in fields.items():
                setattr(refreshed, k, v)
            session.add(refreshed); session.commit()

            if refreshed.is_scam:
                self.vector_store.index_confirmed_scam(...)   # unchanged

            await manager.send_scan_event(scan_id=str(scan_id),
                event_type="scan_completed", payload={...from fields...})
        except Exception as exc:
            # ...keep the existing failure path...
```

`analyze_image_bytes` / `_finalize_verdict` are kept behind a config flag
(`DETECTION_ENGINE=agents|oneshot`) for A/B comparison in the demo — a nice Weave story.

### Status: implemented on branch `integrate-agents-engine`
- Added `DETECTION_ENGINE` to `app/core/config.py` (defaults to **`agents`**).
- `ScanService.analyze_scan` now dispatches: `_analyze_scan_agents` (pipeline) or
  `_analyze_scan_oneshot` (GaelGil's original, unchanged).
- Added `_result_to_scan_fields()` implementing the mapping table above.
- Nothing of the original path was deleted — set `DETECTION_ENGINE=oneshot` in the root `.env`
  to fall back. The DB schema, websocket events, and frontend contract are unchanged.

## Follow-up cleanups (not blocking)

1. **Two configs.** Decide on one. Simplest now: make sure `OPENAI_API_KEY`, `WANDB_API_KEY`,
   `REDIS_URL` are present for *both* `app/config.py` (`backend/.env`) and `app/core/config.py`
   (`../.env`). Longer term, fold the agent settings into `core/config` and delete `app/config.py`.
2. **Two Redis vector stores** (`scam_vectors` vs `example_idx`). They don't conflict (different
   indexes), but we should pick one. The pipeline needs the scam+legit corpus, so `example_idx`
   (seeded via `app/seed.py`) is the one to keep; `RedisScamVectorStore.index_confirmed_scam`
   can write into it instead.
3. **Dead files** once integrated: `app/api/scamdetect/openai_service.py` (or flag-gated),
   and the old flat `/scan` wrappers if unused.
4. **Frontend endpoint.** The Electron app should hit `POST /api/v1/scans/` (multipart image +
   `session_id`) and subscribe to the websocket for the result — not the old `http://localhost:8000/scan`.
   Confirm `frontend/renderer/src/lib/api.ts` matches the merged routes.

## How to run the merged backend (either way)
```bash
cd backend
uv sync                                   # installs the full dep set (pyproject.toml/uv.lock)
docker run -d --name sg-postgres -p 5432:5432 \
  -e POSTGRES_PASSWORD=devpass -e POSTGRES_DB=scamguard postgres:16
docker run -d --name sg-redis -p 6379:6379 redis/redis-stack-server:latest
# create repo-root ../.env with at least:
#   PROJECT_NAME=ScamGuard
#   POSTGRES_SERVER=localhost  POSTGRES_USER=postgres  POSTGRES_PASSWORD=devpass  POSTGRES_DB=scamguard
#   OPENAI_API_KEY=...  WANDB_API_KEY=...  REDIS_URL=redis://localhost:6379
uv run alembic upgrade head               # apply migrations
uv run python -m app.seed                 # seed scam+legit corpus
uv run uvicorn app.main:app --reload --port 8000
```
