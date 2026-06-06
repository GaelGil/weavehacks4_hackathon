import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import desc
from sqlmodel import Session, select

from app.api.scamdetect.contact_store import get_contacts, save_contacts
from app.api.websocket.ConnectionManager import manager
from app.core.config import settings
from app.database.db import engine
from app.database.models import Scan
from app.database.schemas.Scan import (
    ChatResponse,
    NotifyTrustedContactsResponse,
    ScamSearchRequest,
    ScamSearchResponse,
    ScamSearchResult,
    ScanCreate,
    ScanList,
    ScanRead,
    ScanRiskLevel,
    ScanStatus,
    TrustedContact,
    TrustedContactsResponse,
)
from app.utils import send_email


class ScanService:
    def __init__(self, session: Session):
        self.session = session
        self.manager = manager

    def create_scan(self, scan_in: ScanCreate) -> ScanRead:
        scan = Scan.model_validate(scan_in, update={"status": ScanStatus.PENDING})
        self.session.add(scan)
        self.session.commit()
        self.session.refresh(scan)
        return ScanRead.model_validate(scan)

    def list_scans(self) -> ScanList:
        scans = self.session.exec(select(Scan).order_by(desc(Scan.created_at))).all()
        return ScanList(scans=[ScanRead.model_validate(scan) for scan in scans])

    def get_scan(self, scan_id: uuid.UUID) -> ScanRead:
        scan = self.session.get(Scan, scan_id)
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        return ScanRead.model_validate(scan)

    def search_scams(self, search_in: ScamSearchRequest) -> ScamSearchResponse:
        query = search_in.query.lower()
        scans = self.session.exec(select(Scan).order_by(desc(Scan.created_at))).all()
        matches = []
        for scan in scans:
            haystack = " ".join(
                part
                for part in [scan.summary, scan.source_text, scan.scam_type]
                if part is not None
            ).lower()
            if query in haystack:
                matches.append(scan)
            if len(matches) >= search_in.limit:
                break
        return ScamSearchResponse(
            matches=[
                ScamSearchResult(
                    id=match.id,
                    session_id=match.session_id,
                    summary=match.summary,
                    scam_type=match.scam_type,
                    risk_level=match.risk_level,
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

    @staticmethod
    async def analyze_scan(scan_id: uuid.UUID) -> None:
        with Session(engine) as session:
            scan = session.get(Scan, scan_id)
            if not scan:
                return

            scan.status = ScanStatus.IN_PROGRESS
            session.add(scan)
            session.commit()
            await manager.send_scan_event(
                scan_id=str(scan_id),
                event_type="scan_started",
                payload={"status": ScanStatus.IN_PROGRESS.value},
            )

            summary, is_scam, risk_level, scam_type, evidence, actions = _analyze_content(
                source_text=scan.source_text,
                image_url=scan.image_url,
            )

            refreshed_scan = session.get(Scan, scan_id)
            if not refreshed_scan:
                return
            refreshed_scan.status = ScanStatus.COMPLETE
            refreshed_scan.summary = summary
            refreshed_scan.is_scam = is_scam
            refreshed_scan.risk_level = risk_level
            refreshed_scan.scam_type = scam_type
            refreshed_scan.evidence = evidence
            refreshed_scan.recommended_actions = actions
            session.add(refreshed_scan)
            session.commit()

            await manager.send_scan_event(
                scan_id=str(scan_id),
                event_type="scan_completed",
                payload={
                    "status": ScanStatus.COMPLETE.value,
                    "summary": summary,
                    "is_scam": is_scam,
                    "risk_level": risk_level.value,
                    "scam_type": scam_type,
                    "evidence": evidence,
                    "recommended_actions": actions,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )


def _analyze_content(
    source_text: str | None, image_url: str | None
) -> tuple[str, bool, ScanRiskLevel, str, list[str], list[str]]:
    content = f"{source_text or ''} {image_url or ''}".lower()
    suspicious_keywords = [
        "urgent",
        "gift card",
        "wire transfer",
        "verify account",
        "password",
        "social security",
        "click here",
    ]
    evidence = [
        f"Matched suspicious phrase: {keyword}"
        for keyword in suspicious_keywords
        if keyword in content
    ]

    if evidence:
        return (
            "This looks like a likely scam or phishing attempt based on urgent language and credential or payment requests.",
            True,
            ScanRiskLevel.HIGH,
            "phishing",
            evidence,
            [
                "Do not click links or call the number shown in the message.",
                "Do not share passwords, codes, or payment details.",
                "Contact a trusted relative or institution using a known phone number.",
            ],
        )

    return (
        "No strong scam indicators were detected yet, but the user should still verify the sender and avoid sharing personal information.",
        False,
        ScanRiskLevel.LOW,
        "unknown",
        ["No high-risk keywords matched in the current scan."],
        [
            "Verify the sender or website independently.",
            "Avoid sharing personal or financial details until confirmed safe.",
        ],
    )
