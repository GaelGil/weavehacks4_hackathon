"""Pydantic schemas shared across the API and the agents."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

Verdict = Literal["safe", "suspicious", "scam"]


class ScanRequest(BaseModel):
    """A scan triggered from the Electron app."""
    image_b64: Optional[str] = Field(
        default=None, description="Base64 PNG of the screen (no data: prefix)."
    )
    context_text: str = Field(
        default="", description="Optional OCR/text context or user note about the screen."
    )
    source: Literal["manual", "interval"] = "manual"


class RedactionResult(BaseModel):
    """What the PrivacyRedactor found before classification."""
    contains_sensitive: bool = False
    sensitive_kinds: list[str] = Field(default_factory=list)  # e.g. ["password", "ssn"]
    redaction_note: str = ""


class ScamVerdict(BaseModel):
    """Structured output of the ScamClassifier vision agent."""
    verdict: Verdict = "safe"
    risk_score: float = Field(0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    detected_text: str = Field(
        default="", description="Key text the agent read off the screen (used for vector search)."
    )


class SimilarScam(BaseModel):
    text: str
    score: float
    category: str = ""


class SuggestedAction(BaseModel):
    label: str           # shown on the button, e.g. "Don't click that link"
    detail: str          # plain-language explanation
    severity: Literal["info", "warn", "danger"] = "info"


class ScanResult(BaseModel):
    verdict: Verdict
    risk_score: float
    reasons: list[str]
    redaction: RedactionResult
    similar_scams: list[SimilarScam] = Field(default_factory=list)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    advice: str = ""


class AdvisorRequest(BaseModel):
    question: str
    scan: Optional[ScanResult] = None
