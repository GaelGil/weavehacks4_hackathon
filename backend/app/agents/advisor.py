"""Advisor agent.

Powers the CopilotKit chat. Given a scan verdict (and the user's question), it explains
what's happening in plain, reassuring language and proposes concrete safe actions.
Also used by the pipeline to generate the initial suggested actions.
"""
from __future__ import annotations

import json

import weave
from agents import Agent, Runner
from pydantic import BaseModel, Field

from ..models import ScamVerdict, SimilarScam, SuggestedAction


class AdvisorOutput(BaseModel):
    advice: str = Field(description="Plain-language explanation for a non-technical user.")
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)


advisor_agent = Agent(
    name="Advisor",
    model="gpt-4o",
    instructions=(
        "You are a calm, friendly safety assistant for a non-technical user. Based on a scam "
        "analysis, explain in simple, non-alarming language what is going on and what the user "
        "should do. Prefer short sentences. Then propose 2-4 concrete suggested_actions, each "
        "with a short label, a one-line detail, and a severity ('info', 'warn', 'danger'). "
        "Never tell the user to enter passwords or call phone numbers shown in a suspicious message."
    ),
    output_type=AdvisorOutput,
)


def _context_block(verdict: ScamVerdict, similar: list[SimilarScam]) -> str:
    sims = "\n".join(f"- ({s.score}) {s.text}" for s in similar) or "(none)"
    return (
        f"Verdict: {verdict.verdict} (risk {verdict.risk_score})\n"
        f"Reasons: {json.dumps(verdict.reasons)}\n"
        f"Text on screen: {verdict.detected_text}\n"
        f"Similar known scams:\n{sims}"
    )


@weave.op()
async def advise(verdict: ScamVerdict, similar: list[SimilarScam]) -> AdvisorOutput:
    """Generate the initial advice + suggested actions for a scan."""
    prompt = (
        "Here is the scam analysis of the user's screen. Explain it and suggest safe actions.\n\n"
        + _context_block(verdict, similar)
    )
    result = await Runner.run(advisor_agent, prompt)
    return result.final_output


# A lighter, free-form agent for the back-and-forth chat (no forced structure).
chat_agent = Agent(
    name="AdvisorChat",
    model="gpt-4o",
    instructions=advisor_agent.instructions
    + "\nIn chat, answer the user's question directly and conversationally.",
)


@weave.op()
async def chat(question: str, scan_context: str = "") -> str:
    prompt = question if not scan_context else f"{question}\n\nContext about their screen:\n{scan_context}"
    result = await Runner.run(chat_agent, prompt)
    return str(result.final_output)
