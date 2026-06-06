import uuid
from enum import Enum

from pydantic import EmailStr, Field as PydanticField
from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class ScanStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


class ScanRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ScanEventType(str, Enum):
    SCAN_STATUS = "scan_status"
    CHAT_CHUNK = "chat_chunk"


class ScanBase(SQLModel):
    session_id: str = Field(index=True, max_length=255)
    source_type: str = Field(default="text", max_length=50)
    source_text: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    image_url: str | None = Field(default=None, max_length=2048)
    status: ScanStatus = Field(default=ScanStatus.PENDING, nullable=False)
    is_scam: bool | None = Field(default=None, nullable=True)
    risk_level: ScanRiskLevel | None = Field(default=None, nullable=True)
    scam_type: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    evidence: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    recommended_actions: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )


class ScanCreate(SQLModel):
    session_id: str = Field(max_length=255)
    source_type: str = Field(default="text", max_length=50)
    source_text: str | None = Field(default=None, max_length=10000)
    image_url: str | None = Field(default=None, max_length=2048)


class ScanRead(ScanBase):
    id: uuid.UUID


class ScanList(SQLModel):
    scans: list[ScanRead]


class ScamSearchRequest(SQLModel):
    query: str = Field(min_length=3, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class ScamSearchResult(SQLModel):
    id: uuid.UUID
    session_id: str
    summary: str | None
    scam_type: str | None
    risk_level: ScanRiskLevel | None


class ScamSearchResponse(SQLModel):
    matches: list[ScamSearchResult]


class ChatRequest(SQLModel):
    session_id: str = Field(max_length=255)
    scan_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(SQLModel):
    response: str


class TrustedContact(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    relationship: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)


class TrustedContactsRequest(SQLModel):
    session_id: str = Field(max_length=255)
    contacts: list[TrustedContact] = PydanticField(default_factory=list)


class TrustedContactsResponse(SQLModel):
    session_id: str
    contacts: list[TrustedContact]


class NotifyTrustedContactsRequest(SQLModel):
    session_id: str = Field(max_length=255)
    scan_id: uuid.UUID


class NotifyTrustedContactsResponse(SQLModel):
    session_id: str
    notified_contacts: list[str]
    message: str
