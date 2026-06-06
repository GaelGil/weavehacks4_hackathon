"""CollectDataAgent (stage 1).

Scours the screenshot and extracts STRUCTURED FACTS — sender, subject, links, calls to
action, requests, urgency signals, etc. It deliberately makes NO judgment about whether
something is a scam; its only job is faithful observation so later agents reason over
organized data instead of re-guessing from raw pixels.
"""
from __future__ import annotations

import weave
from agents import Agent, Runner

from ..config import get_settings
from ..models import ScreenFacts
from ._helpers import vision_input

collector_agent = Agent(
    name="CollectDataAgent",
    model=get_settings().openai_vision_model,
    instructions=(
        "You are an observation agent. Look at the screenshot and extract the facts into the "
        "structured fields. Be precise and literal — transcribe exactly what you see.\n"
        "- context: which app/screen this is (e.g. 'Gmail showing an opened email').\n"
        "- brand_claimed: who the content claims to be from.\n"
        "- sender_name / sender_address: exactly as shown, including the full email address.\n"
        "- subject, body_summary: faithful summary, do not embellish.\n"
        "- links: any visible URLs or where buttons appear to lead.\n"
        "- call_to_actions: buttons/links urging action (e.g. 'View Event', 'Download App').\n"
        "- requests: what the user is asked to DO (download, pay, log in, call a number...).\n"
        "- urgency_signals: deadlines, threats, pressure language. Empty list if none.\n"
        "- notable_observations: anything else relevant (logos, formatting, typos).\n"
        "- raw_text: the most important text verbatim (sender + subject + key lines).\n"
        "Do NOT decide if it is a scam. Just report what is there."
    ),
    output_type=ScreenFacts,
)


@weave.op()
async def collect(image_b64: str | None, context_text: str = "") -> ScreenFacts:
    prompt = (
        "Extract the structured facts from this screen. "
        f"Extra context from the app: {context_text or '(none)'}"
    )
    result = await Runner.run(collector_agent, vision_input(prompt, image_b64))
    return result.final_output
