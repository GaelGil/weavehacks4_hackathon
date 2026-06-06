"""ScamGuard FastAPI backend.

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents import advisor, pipeline
from .config import get_settings
from .copilot import mount_copilotkit
from .models import AdvisorRequest, ScanRequest, ScanResult
from .services.redis_store import get_store


def _init_weave() -> None:
    settings = get_settings()
    if settings.weave_disabled:
        print("[weave] disabled via WEAVE_DISABLED")
        return
    try:
        import weave

        weave.init(settings.weave_project)
        print(f"[weave] tracing to project '{settings.weave_project}'")
    except Exception as e:  # noqa: BLE001
        print(f"[weave] init failed ({e}); continuing without tracing.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_weave()
    try:
        get_store().ensure_index()
    except Exception as e:  # noqa: BLE001
        print(f"[startup] redis index init skipped: {e}")
    yield


app = FastAPI(title="ScamGuard", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    store = get_store()
    return {
        "ok": True,
        "redis": store.r is not None,
        "scan_interval_seconds": _settings.scan_interval_seconds,
    }


@app.post("/scan", response_model=ScanResult)
async def scan(req: ScanRequest) -> ScanResult:
    """Run the full redact -> classify -> vector-search -> advise pipeline."""
    return await pipeline.run_scan(req)


@app.post("/advisor")
async def advisor_chat(req: AdvisorRequest) -> dict:
    """Plain REST chat fallback (also used if CopilotKit isn't wired up yet)."""
    context = ""
    if req.scan:
        context = (
            f"Verdict: {req.scan.verdict} (risk {req.scan.risk_score}). "
            f"Reasons: {'; '.join(req.scan.reasons)}. Advice given: {req.scan.advice}"
        )
    answer = await advisor.chat(req.question, context)
    return {"answer": answer}


# Optional: CopilotKit remote endpoint at /copilotkit
mount_copilotkit(app)
app.include_router(api_router, prefix=settings.API_V1_STR)
