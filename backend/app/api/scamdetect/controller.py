import uuid

from fastapi import APIRouter, BackgroundTasks, Request

from app.api.deps import ScanServiceDep
from app.database.schemas.Scan import (
    ChatRequest,
    ChatResponse,
    NotifyTrustedContactsRequest,
    NotifyTrustedContactsResponse,
    ScamSearchRequest,
    ScamSearchResponse,
    ScanCreate,
    ScanList,
    ScanRead,
    TrustedContactsRequest,
    TrustedContactsResponse,
)
from app.limiter import limiter

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/", response_model=ScanRead)
@limiter.limit("5/minute")
async def create_scan(
    request: Request,
    scan_service: ScanServiceDep,
    scan_in: ScanCreate,
    background_tasks: BackgroundTasks,
) -> ScanRead:
    del request
    scan = scan_service.create_scan(scan_in)
    background_tasks.add_task(scan_service.analyze_scan, scan.id)
    return scan


@router.get("/", response_model=ScanList)
def list_scans(scan_service: ScanServiceDep) -> ScanList:
    return scan_service.list_scans()


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
    return scan_service.notify_trusted_contacts(
        notify_in.session_id, notify_in.scan_id
    )
