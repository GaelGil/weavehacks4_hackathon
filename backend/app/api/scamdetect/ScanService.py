import base64
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import desc
from sqlmodel import Session, select

from app.agents import pipeline
from app.api.scamdetect.contact_store import get_contacts, save_contacts
from app.api.scamdetect.openai_service import analyze_image_bytes, embed_text
from app.api.scamdetect.redis_vector_store import RedisScamVectorStore
from app.api.websocket.ConnectionManager import manager
from app.core.config import settings
from app.database.db import engine
from app.database.models import Scan
from app.models import ScanRequest as AgentScanRequest
from app.models import ScanResult as AgentScanResult
from app.database.schemas.Scan import (
    ChatResponse,
    NotifyTrustedContactsResponse,
    ScamSearchRequest,
    ScamSearchResponse,
    ScamSearchResult,
    ScanList,
    ScanRead,
    ScanRiskLevel,
    ScanStatus,
    TrustedContact,
    TrustedContactsResponse,
    VisionAnalysisResult,
)
from app.utils import send_email


class ScanService:
    def __init__(self, session: Session):
        self.session = session
        self.manager = manager
        self.vector_store = RedisScamVectorStore()

    def create_scan(self, session_id: str, source_text: str | None) -> ScanRead:
        scan = Scan(
            session_id=session_id,
            source_type="image",
            source_text=source_text,
            status=ScanStatus.PENDING,
        )
        self.session.add(scan)
        self.session.commit()
        self.session.refresh(scan)
        return ScanRead.model_validate(scan)

    def list_scans(self, session_id: str | None = None) -> ScanList:
        statement = select(Scan).order_by(desc(Scan.created_at))
        if session_id:
            statement = statement.where(Scan.session_id == session_id)
        scans = self.session.exec(statement).all()
        return ScanList(scans=[ScanRead.model_validate(scan) for scan in scans])

    def get_scan(self, scan_id: uuid.UUID) -> ScanRead:
        scan = self.session.get(Scan, scan_id)
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        return ScanRead.model_validate(scan)

    def search_scams(self, search_in: ScamSearchRequest) -> ScamSearchResponse:
        embedding = embed_text(search_in.query)
        matches = self.vector_store.search_similar_scams(
            embedding=embedding,
            limit=search_in.limit,
        )
        return ScamSearchResponse(
            matches=[
                ScamSearchResult(
                    id=uuid.UUID(str(match["id"])),
                    session_id=match["session_id"],
                    summary=match["summary"],
                    scam_type=match["scam_type"],
                    risk_level=(
                        ScanRiskLevel(str(match["risk_level"]))
                        if match["risk_level"] is not None
                        else None
                    ),
                    similarity_score=match["similarity_score"],
                )
                for match in matches
            ]
        )

    def chat_about_scan(self, scan_id: uuid.UUID, message: str) -> ChatResponse:
        scan = self.session.get(Scan, scan_id)
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")

        summary = scan.summary or "This scan has not been analyzed yet."
        actions = scan.recommended_actions or ["Wait for the scan result before taking action."]
        response = (
            f"Based on this scan, here is the safest guidance. {summary} "
            f"Question: {message} Recommended next step: {actions[0]}"
        )
        return ChatResponse(response=response)

    def save_trusted_contacts(
        self, session_id: str, contacts: list[TrustedContact]
    ) -> TrustedContactsResponse:
        save_contacts(session_id, contacts)
        return TrustedContactsResponse(session_id=session_id, contacts=contacts)

    def get_trusted_contacts(self, session_id: str) -> TrustedContactsResponse:
        return TrustedContactsResponse(
            session_id=session_id, contacts=get_contacts(session_id)
        )

    def notify_trusted_contacts(
        self, session_id: str, scan_id: uuid.UUID
    ) -> NotifyTrustedContactsResponse:
        scan = self.session.get(Scan, scan_id)
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")

        contacts = get_contacts(session_id)
        if not contacts:
            raise HTTPException(status_code=404, detail="No trusted contacts for session")

        notified_contacts: list[str] = []
        summary = scan.summary or "Potential scam detected."
        for contact in contacts:
            label = contact.email or contact.phone or contact.name
            if contact.email and settings.emails_enabled:
                send_email(
                    email_to=contact.email,
                    subject=f"{settings.PROJECT_NAME} trusted contact alert",
                    html_content=(
                        f"<p>{summary}</p><p>Recommended action: "
                        f"{', '.join(scan.recommended_actions)}</p>"
                    ),
                )
            notified_contacts.append(label)

        return NotifyTrustedContactsResponse(
            session_id=session_id,
            notified_contacts=notified_contacts,
            message="Trusted contacts notified",
        )

    async def analyze_scan(
        self, scan_id: uuid.UUID, image_bytes: bytes, content_type: str | None
    ) -> None:
        """Dispatch to the configured detection engine (see settings.DETECTION_ENGINE)."""
        if settings.DETECTION_ENGINE == "agents":
            await self._analyze_scan_agents(scan_id, image_bytes, content_type)
        else:
            await self._analyze_scan_oneshot(scan_id, image_bytes, content_type)

    async def _analyze_scan_agents(
        self, scan_id: uuid.UUID, image_bytes: bytes, content_type: str | None
    ) -> None:
        """Run Brendan's multi-agent pipeline (collect -> research -> decide) and persist."""
        del content_type  # the pipeline takes base64; mime not needed
        with Session(engine) as session:
            scan = session.get(Scan, scan_id)
            if not scan:
                return
            try:
                if not image_bytes:
                    raise ValueError("Uploaded image was empty")
                if len(image_bytes) > settings.MAX_IMAGE_UPLOAD_BYTES:
                    raise ValueError("Uploaded image exceeded the maximum allowed size")

                scan.status = ScanStatus.IN_PROGRESS
                session.add(scan)
                session.commit()
                await manager.send_scan_event(
                    scan_id=str(scan_id),
                    event_type="scan_started",
                    payload={"status": ScanStatus.IN_PROGRESS.value},
                )

                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                result = await pipeline.run_scan(
                    AgentScanRequest(image_b64=image_b64, context_text=scan.source_text or "")
                )
                fields = _result_to_scan_fields(result)

                refreshed_scan = session.get(Scan, scan_id)
                if not refreshed_scan:
                    return
                for key, value in fields.items():
                    setattr(refreshed_scan, key, value)
                session.add(refreshed_scan)
                session.commit()

                if refreshed_scan.is_scam:
                    self.vector_store.index_confirmed_scam(
                        scan_id=refreshed_scan.id,
                        session_id=refreshed_scan.session_id,
                        summary=refreshed_scan.summary or "",
                        detected_text=refreshed_scan.detected_text or "",
                        detected_urls=refreshed_scan.detected_urls,
                        scam_type=refreshed_scan.scam_type or "unknown",
                        risk_level=refreshed_scan.risk_level,
                    )

                await manager.send_scan_event(
                    scan_id=str(scan_id),
                    event_type="scan_completed",
                    payload={
                        "status": ScanStatus.COMPLETE.value,
                        "summary": refreshed_scan.summary,
                        "is_scam": refreshed_scan.is_scam,
                        "risk_level": refreshed_scan.risk_level.value
                        if refreshed_scan.risk_level
                        else None,
                        "scam_type": refreshed_scan.scam_type,
                        "impersonated_brand": refreshed_scan.impersonated_brand,
                        "confidence_score": refreshed_scan.confidence_score,
                        "detected_text": refreshed_scan.detected_text,
                        "detected_urls": refreshed_scan.detected_urls,
                        "evidence": refreshed_scan.evidence,
                        "similar_scams": refreshed_scan.similar_scams,
                        "recommended_actions": refreshed_scan.recommended_actions,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                failed_scan = session.get(Scan, scan_id)
                if failed_scan:
                    failed_scan.status = ScanStatus.FAILED
                    failed_scan.summary = str(exc)
                    session.add(failed_scan)
                    session.commit()
                await manager.send_scan_event(
                    scan_id=str(scan_id),
                    event_type="scan_failed",
                    payload={"status": ScanStatus.FAILED.value, "error": str(exc)},
                )

    async def _analyze_scan_oneshot(
        self, scan_id: uuid.UUID, image_bytes: bytes, content_type: str | None
    ) -> None:
        with Session(engine) as session:
            scan = session.get(Scan, scan_id)
            if not scan:
                return

            try:
                if not image_bytes:
                    raise ValueError("Uploaded image was empty")
                if len(image_bytes) > settings.MAX_IMAGE_UPLOAD_BYTES:
                    raise ValueError("Uploaded image exceeded the maximum allowed size")

                scan.status = ScanStatus.IN_PROGRESS
                session.add(scan)
                session.commit()
                await manager.send_scan_event(
                    scan_id=str(scan_id),
                    event_type="scan_started",
                    payload={"status": ScanStatus.IN_PROGRESS.value},
                )

                analysis = analyze_image_bytes(
                    image_bytes=image_bytes,
                    content_type=content_type,
                    source_text=scan.source_text,
                )
                similar_scams = _search_similar_scams(self.vector_store, analysis)
                is_scam, risk_level = _finalize_verdict(analysis, similar_scams)

                refreshed_scan = session.get(Scan, scan_id)
                if not refreshed_scan:
                    return
                refreshed_scan.status = ScanStatus.COMPLETE
                refreshed_scan.summary = analysis.summary
                refreshed_scan.is_scam = is_scam
                refreshed_scan.risk_level = risk_level
                refreshed_scan.scam_type = analysis.scam_type
                refreshed_scan.impersonated_brand = analysis.impersonated_brand
                refreshed_scan.confidence_score = analysis.confidence_score
                refreshed_scan.detected_text = analysis.detected_text
                refreshed_scan.detected_urls = analysis.detected_urls
                refreshed_scan.evidence = analysis.evidence
                refreshed_scan.extracted_details = analysis.extracted_details
                refreshed_scan.similar_scams = similar_scams
                refreshed_scan.recommended_actions = analysis.recommended_actions
                session.add(refreshed_scan)
                session.commit()

                if is_scam:
                    self.vector_store.index_confirmed_scam(
                        scan_id=refreshed_scan.id,
                        session_id=refreshed_scan.session_id,
                        summary=analysis.summary,
                        detected_text=analysis.detected_text,
                        detected_urls=analysis.detected_urls,
                        scam_type=analysis.scam_type,
                        risk_level=risk_level,
                    )

                await manager.send_scan_event(
                    scan_id=str(scan_id),
                    event_type="scan_completed",
                    payload={
                        "status": ScanStatus.COMPLETE.value,
                        "summary": analysis.summary,
                        "is_scam": is_scam,
                        "risk_level": risk_level.value,
                        "scam_type": analysis.scam_type,
                        "impersonated_brand": analysis.impersonated_brand,
                        "confidence_score": analysis.confidence_score,
                        "detected_text": analysis.detected_text,
                        "detected_urls": analysis.detected_urls,
                        "evidence": analysis.evidence,
                        "similar_scams": similar_scams,
                        "recommended_actions": analysis.recommended_actions,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                failed_scan = session.get(Scan, scan_id)
                if failed_scan:
                    failed_scan.status = ScanStatus.FAILED
                    failed_scan.summary = str(exc)
                    session.add(failed_scan)
                    session.commit()
                await manager.send_scan_event(
                    scan_id=str(scan_id),
                    event_type="scan_failed",
                    payload={
                        "status": ScanStatus.FAILED.value,
                        "error": str(exc),
                    },
                )


_RISK_BY_VERDICT = {
    "scam": ScanRiskLevel.HIGH,
    "suspicious": ScanRiskLevel.MEDIUM,
    "safe": ScanRiskLevel.LOW,
}


def _result_to_scan_fields(result: AgentScanResult) -> dict:
    """Map the agent pipeline's ScanResult onto the Scan DB columns."""
    facts = result.facts
    research = result.research
    return {
        "status": ScanStatus.COMPLETE,
        "summary": result.advice,
        "is_scam": result.verdict == "scam",
        "risk_level": _RISK_BY_VERDICT.get(result.verdict, ScanRiskLevel.LOW),
        "confidence_score": result.risk_score,
        "scam_type": (result.similar_scams[0].category if result.similar_scams else "unknown"),
        "impersonated_brand": (facts.brand_claimed or None) if facts else None,
        "detected_text": (facts.raw_text if facts else ""),
        "detected_urls": (facts.links if facts else []),
        "evidence": [*result.reasons, *(research.scam_indicators if research else [])],
        "extracted_details": {
            "facts": facts.model_dump() if facts else {},
            "research": research.model_dump() if research else {},
            "trusted_sender": result.trusted_sender,
        },
        "similar_scams": [s.model_dump() for s in result.similar_scams],
        "recommended_actions": [
            f"{a.label}: {a.detail}" for a in result.suggested_actions
        ],
    }


def _search_similar_scams(
    vector_store: RedisScamVectorStore, analysis: VisionAnalysisResult
) -> list[dict[str, str | float | None]]:
    if not analysis.is_potential_scam:
        return []
    embedding = embed_text(
        "\n".join(
            [
                analysis.summary,
                analysis.detected_text,
                " ".join(analysis.detected_urls),
                analysis.scam_type,
            ]
        )
    )
    return vector_store.search_similar_scams(embedding=embedding)


def _finalize_verdict(
    analysis: VisionAnalysisResult, similar_scams: list[dict[str, str | float | None]]
) -> tuple[bool, ScanRiskLevel]:
    if analysis.confidence_score >= 0.8:
        return True, ScanRiskLevel.HIGH
    if analysis.confidence_score >= 0.55 and similar_scams:
        return True, ScanRiskLevel.HIGH
    if analysis.is_potential_scam:
        return False, ScanRiskLevel.MEDIUM
    return False, ScanRiskLevel.LOW
