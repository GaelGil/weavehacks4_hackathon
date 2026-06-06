"""Advisor (stage 3 — the decider).

Looks back at the screenshot ALONGSIDE the collected facts and the research findings, and
makes the final call: safe / suspicious / scam, with a risk score, plain-language reasons,
advice, and concrete suggested actions. Because it decides with grounded context (not raw
pixels), it stops over-flagging legitimate mail like transactional event emails.

Also exposes a free-form `chat` agent that powers the CopilotKit conversation.
"""
from __future__ import annotations

import weave
from agents import Agent, Runner
from pydantic import BaseModel, Field

from ..config import get_settings
from ..models import ResearchFindings, ScamVerdict, ScreenFacts, SimilarExample, SuggestedAction
from ._helpers import vision_input


class AdvisorDecision(BaseModel):
    verdict: ScamVerdict
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)


advisor_agent = Agent(
    name="Advisor",
    model=get_settings().openai_model,
    instructions=(
        "You are a calm, friendly safety assistant for a non-technical user (e.g. an elderly "
        "person). You are given: the screenshot, structured FACTS about it, and RESEARCH findings "
        "(legitimacy vs scam indicators, web research, similar known scams/legit messages).\n\n"
        "Weigh ALL of this and decide:\n"
        "- verdict: 'safe', 'suspicious', or 'scam'\n"
        "- risk_score: 0.0 (clearly safe) to 1.0 (clearly a scam)\n"
        "- reasons: short, plain-language bullets a layperson understands\n"
        "- advice: a short, reassuring explanation of what's going on and what to do\n\n"
        "IMPORTANT calibration:\n"
        "- Trust the research. If research shows the sender domain is a known/verified sender for the "
        "brand, do NOT mark it suspicious just because the address looks unusual.\n"
        "- If research POSITIVELY verified the sender/brand AND found the matching real event/page/product, "
        "treat it as SAFE (risk_score <= 0.2) unless there is concrete contradicting evidence.\n"
        "- NEVER count these as reasons to raise risk: 'couldn't confirm it exists', 'sender name not "
        "recognized', 'no information found', or an unfamiliar-but-unverified domain. Absence of evidence "
        "is NOT evidence of a scam. Do not invent red flags — every reason you give must be grounded in the "
        "facts or research provided.\n"
        "- Ordinary transactional, newsletter, and event emails are SAFE even if they contain links "
        "or app-download buttons. Reserve 'scam'/'suspicious' for real red flags: credential/payment "
        "requests, mismatched/spoofed domains, threats, urgency to bypass normal channels, lookalike "
        "brands, or close matches to known scams.\n"
        "- A trusted-contacts note is only a SOFT prior. NEVER mark something safe just because the sender "
        "is trusted — a trusted account can be hacked or its display name spoofed. Always judge the actual "
        "content; real red flags override trust. An 'untrusted' note is a genuine negative signal.\n"
        "Then propose 2-4 suggested_actions (label, one-line detail, severity 'info'|'warn'|'danger'). "
        "For safe mail, actions should be light/informational. Never tell the user to enter passwords "
        "or call numbers shown in a suspicious message."
    ),
    output_type=AdvisorDecision,
)


def _context_block(facts: ScreenFacts, research: ResearchFindings,
                   similar_scams: list[SimilarExample], similar_legit: list[SimilarExample]) -> str:
    return (
        "FACTS:\n" + facts.model_dump_json(indent=2)
        + "\n\nRESEARCH:\n" + research.model_dump_json(indent=2)
        + "\n\nSIMILAR KNOWN SCAMS:\n"
        + ("\n".join(f"- ({s.score}) {s.text}" for s in similar_scams) or "(none)")
        + "\n\nSIMILAR KNOWN-LEGIT:\n"
        + ("\n".join(f"- ({s.score}) {s.text}" for s in similar_legit) or "(none)")
    )


@weave.op()
async def decide(
    image_b64: str | None,
    facts: ScreenFacts,
    research: ResearchFindings,
    similar_scams: list[SimilarExample],
    similar_legit: list[SimilarExample],
    trust_note: str = "",
) -> AdvisorDecision:
    prompt = (
        "Make the final scam assessment using the screenshot plus this context.\n\n"
        + _context_block(facts, research, similar_scams, similar_legit)
    )
    if trust_note:
        prompt += f"\n\nTRUSTED-CONTACTS: {trust_note}"
    result = await Runner.run(advisor_agent, vision_input(prompt, image_b64))
    return result.final_output


# ---- Free-form chat agent for the CopilotKit conversation ----
chat_agent = Agent(
    name="AdvisorChat",
    model=get_settings().openai_model,
    instructions=(
        "You are a calm, friendly safety assistant for a non-technical user. Answer their questions "
        "about whether something is a scam and what to do, conversationally and in simple language. "
        "Use any provided context about their latest screen scan."
    ),
)


@weave.op()
async def chat(question: str, scan_context: str = "") -> str:
    prompt = question if not scan_context else f"{question}\n\nContext about their screen:\n{scan_context}"
    result = await Runner.run(chat_agent, prompt)
    return str(result.final_output)
