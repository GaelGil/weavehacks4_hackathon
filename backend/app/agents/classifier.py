"""ScamClassifier agent.

A vision agent that looks at the (privacy-checked) screenshot plus any context and
returns a STRUCTURED verdict: safe / suspicious / scam, a 0-1 risk score, reasons,
and the key text it read off the screen (which we feed into Redis vector search).
"""
from __future__ import annotations

import weave
from agents import Agent, Runner

from ..models import ScamVerdict
from ._helpers import vision_input

classifier_agent = Agent(
    name="ScamClassifier",
    model="gpt-4o",
    instructions=(
        "You are a scam-detection expert helping protect a non-technical user (e.g. an "
        "elderly person). Examine the screenshot and any provided context. Decide whether "
        "what is on screen is a phishing attempt, scam, malicious download, fake support "
        "popup, or other harmful content.\n\n"
        "Return:\n"
        "- verdict: 'safe', 'suspicious', or 'scam'\n"
        "- risk_score: 0.0 (clearly safe) to 1.0 (clearly a scam)\n"
        "- reasons: short, plain-language bullet points a layperson understands "
        "(e.g. 'The sender address is not really from your bank')\n"
        "- detected_text: the most relevant text visible on screen (sender, subject, "
        "links, urgent language) so it can be compared to known scams.\n\n"
        "Be cautious but avoid crying wolf on ordinary, legitimate screens."
    ),
    output_type=ScamVerdict,
)


@weave.op()
async def classify(image_b64: str | None, context_text: str = "") -> ScamVerdict:
    prompt = (
        "Analyze this screen for scams or harmful content. "
        f"Extra context: {context_text or '(none)'}"
    )
    result = await Runner.run(classifier_agent, vision_input(prompt, image_b64))
    return result.final_output
