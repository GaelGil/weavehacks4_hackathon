"""Pydantic schemas shared across the API and the agents."""

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["safe", "suspicious", "scam"]


class ScanRequest(BaseModel):
    """A scan triggered from the Electron app."""

    image_b64: str | None = Field(
        default=None, description="Base64 PNG of the screen (no data: prefix)."
    )
    context_text: str = Field(
        default="",
        description="Optional OCR/text context or user note about the screen.",
    )
    source: Literal["manual", "interval"] = "manual"


class RedactionResult(BaseModel):
    """What the PrivacyRedactor found before classification."""

    contains_sensitive: bool = False
    sensitive_kinds: list[str] = Field(default_factory=list)  # e.g. ["password", "ssn"]
    redaction_note: str = ""


class ScreenFacts(BaseModel):
    """Stage 1 output: structured facts the CollectDataAgent reads off the screen.

    Pure observation — NO judgment about whether it's a scam. That's deliberate so the
    later agents reason over facts instead of re-guessing from raw pixels.
    """

    context: str = Field(
        default="",
        description="What app/screen this is, e.g. 'Gmail showing an opened email'.",
    )
    brand_claimed: str = Field(
        default="",
        description="Who the content claims to be from, e.g. 'Luma / Weights & Biases'.",
    )
    sender_name: str = ""
    sender_address: str = ""
    subject: str = ""
    body_summary: str = ""
    links: list[str] = Field(default_factory=list)
    call_to_actions: list[str] = Field(
        default_factory=list,
        description="Buttons/links urging action, e.g. 'View Event'.",
    )
    requests: list[str] = Field(
        default_factory=list,
        description="What it asks the user to do (download app, pay, log in...).",
    )
    urgency_signals: list[str] = Field(
        default_factory=list, description="Pressure tactics, deadlines, threats."
    )
    notable_observations: list[str] = Field(default_factory=list)
    raw_text: str = Field(
        default="", description="Key text for vector search / comparison."
    )


class SimilarExample(BaseModel):
    """A comparison message pulled from the Redis corpus."""

    text: str
    score: float
    label: Literal["scam", "legit"] = "scam"
    category: str = ""


# Back-compat alias used by the frontend (subset of fields).
SimilarScam = SimilarExample


class ResearchFindings(BaseModel):
    """Stage 2 output: the ResearchAgent's grounded comparison evidence."""

    domain_assessment: str = Field(
        default="", description="What research says about the sender domain/brand."
    )
    legitimacy_indicators: list[str] = Field(default_factory=list)
    scam_indicators: list[str] = Field(default_factory=list)
    web_findings: list[str] = Field(
        default_factory=list, description="Relevant facts found via web search."
    )
    research_notes: str = ""


class ScamVerdict(BaseModel):
    """Final structured decision from the Advisor (vision + facts + research)."""

    verdict: Verdict = "safe"
    risk_score: float = Field(0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    advice: str = Field(
        default="", description="Plain-language explanation for a non-technical user."
    )


class SuggestedAction(BaseModel):
    label: str  # shown on the button, e.g. "Don't click that link"
    detail: str  # plain-language explanation
    severity: Literal["info", "warn", "danger"] = "info"


class ScanResult(BaseModel):
    verdict: Verdict
    risk_score: float
    reasons: list[str]
    advice: str = ""
    redaction: RedactionResult
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    similar_scams: list[SimilarExample] = Field(default_factory=list)
    similar_legit: list[SimilarExample] = Field(default_factory=list)
    trusted_sender: bool | None = None  # True/False if the sender is on the trust list
    handled_by: str | None = None  # which specialist agent the triage routed to
    # Transparency: surface the intermediate stages (great for the demo + Weave).
    facts: ScreenFacts | None = None
    research: ResearchFindings | None = None


class AdvisorRequest(BaseModel):
    question: str
    scan: ScanResult | None = None


class ContactRequest(BaseModel):
    identifier: str = Field(
        description="Email address or domain, e.g. 'anna@luma-mail.com' or 'luma-mail.com'."
    )
    trusted: bool
