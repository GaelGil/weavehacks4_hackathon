import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Request, UploadFile

from app.api.deps import ScanServiceDep
from app.config import get_settings
from app.database.schemas.Scan import (
    ChatRequest,
    ChatResponse,
    NotifyTrustedContactsRequest,
    NotifyTrustedContactsResponse,
    ScamSearchRequest,
    ScamSearchResponse,
    ScanList,
    ScanRead,
    TrustedContactsRequest,
    TrustedContactsResponse,
)
from app.limiter import limiter
from app.models import AdvisorRequest, ScanRequest, ScanResult
from app.services.redis_store import get_store

router = APIRouter(prefix="/scans", tags=["scans"])
settings = get_settings()


@router.post("/", response_model=ScanRead)
@limiter.limit("5/minute")
async def create_scan(
    request: Request,
    scan_service: ScanServiceDep,
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    image: UploadFile = File(...),
    source_text: str | None = Form(default=None),
) -> ScanRead:
    del request
    image_bytes = await image.read()
    scan = scan_service.create_scan(session_id=session_id, source_text=source_text)
    background_tasks.add_task(
        scan_service.analyze_scan,
        scan.id,
        image_bytes,
        image.content_type,
    )
    return scan


@router.post("/scan", response_model=ScanResult)
async def scan(req: ScanRequest) -> ScanResult:
    """Run the full redact -> classify -> vector-search -> advise pipeline."""
    from app.agents import pipeline

    return await pipeline.run_scan(req)


@router.get("/health")
async def health() -> dict:
    store = get_store()
    return {
        "ok": True,
        "redis": store.r is not None,
        "scan_interval_seconds": settings.scan_interval_seconds,
    }


@router.get("/", response_model=ScanList)
def list_scans(
    scan_service: ScanServiceDep, session_id: str | None = Query(default=None)
) -> ScanList:
    return scan_service.list_scans(session_id=session_id)


@router.get("/{scan_id}", response_model=ScanRead)
def get_scan(scan_id: uuid.UUID, scan_service: ScanServiceDep) -> ScanRead:
    return scan_service.get_scan(scan_id)


@router.post("/search", response_model=ScamSearchResponse)
def search_scams(
    search_in: ScamSearchRequest, scan_service: ScanServiceDep
) -> ScamSearchResponse:
    return scan_service.search_scams(search_in)


@router.post("/chat", response_model=ChatResponse)
def chat_about_scan(chat_in: ChatRequest, scan_service: ScanServiceDep) -> ChatResponse:
    return scan_service.chat_about_scan(chat_in.scan_id, chat_in.message)


@router.post("/advisor")
async def advisor_chat(req: AdvisorRequest) -> dict:
    """Plain REST chat fallback (also used if CopilotKit isn't wired up yet)."""
    from app.agents import advisor

    context = ""
    if req.scan:
        context = (
            f"Verdict: {req.scan.verdict} (risk {req.scan.risk_score}). "
            f"Reasons: {'; '.join(req.scan.reasons)}. Advice given: {req.scan.advice}"
        )
    answer = await advisor.chat(req.question, context)
    return {"answer": answer}


@router.post("/trusted-contacts", response_model=TrustedContactsResponse)
def save_trusted_contacts(
    contacts_in: TrustedContactsRequest, scan_service: ScanServiceDep
) -> TrustedContactsResponse:
    return scan_service.save_trusted_contacts(
        contacts_in.session_id, contacts_in.contacts
    )


@router.get("/trusted-contacts/{session_id}", response_model=TrustedContactsResponse)
def get_trusted_contacts(
    session_id: str, scan_service: ScanServiceDep
) -> TrustedContactsResponse:
    return scan_service.get_trusted_contacts(session_id)


@router.post("/notify", response_model=NotifyTrustedContactsResponse)
def notify_trusted_contacts(
    notify_in: NotifyTrustedContactsRequest, scan_service: ScanServiceDep
) -> NotifyTrustedContactsResponse:
    return scan_service.notify_trusted_contacts(notify_in.session_id, notify_in.scan_id)
