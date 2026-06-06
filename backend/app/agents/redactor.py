"""PrivacyRedactor agent.

Looks at the screen and decides whether sensitive info is present that should be
censored BEFORE the screenshot is reasoned about further. Privacy is a feature:
we never want passwords/SSNs/account numbers flowing through logs or Weave traces.

NOTE: this currently *describes* what is sensitive (the agent's structured output).
True pixel-level redaction (OCR + blur the regions) is a TODO — see README.
"""
from __future__ import annotations

import weave
from agents import Agent, Runner

from ..config import get_settings
from ..models import RedactionResult
from ._helpers import vision_input

redactor_agent = Agent(
    name="PrivacyRedactor",
    model=get_settings().openai_vision_model,
    instructions=(
        "You protect the user's privacy. Look at the screenshot and determine whether it "
        "contains SENSITIVE personal information such as passwords, full credit-card or bank "
        "account numbers, social-security numbers, 2FA codes, or private API keys.\n"
        "Set contains_sensitive accordingly and list the KINDS found (e.g. 'password', "
        "'ssn', 'card_number'). Do NOT echo the actual secret values back. Keep redaction_note "
        "short and non-sensitive."
    ),
    output_type=RedactionResult,
)


@weave.op()
async def redact(image_b64: str | None, context_text: str = "") -> RedactionResult:
    prompt = (
        "Inspect this screen for sensitive personal information. "
        f"Extra context from the app: {context_text or '(none)'}"
    )
    result = await Runner.run(redactor_agent, vision_input(prompt, image_b64))
    return result.final_output
