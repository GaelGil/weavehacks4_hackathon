"""Supervisor / triage pattern for the decision stage.

Instead of one generic Advisor making the final call, a TriageAgent inspects the
facts + research + screenshot and HANDS OFF (OpenAI Agents SDK handoffs) to the single
best scam specialist, who produces the final verdict + tailored advice/actions.

Trace tree in Weave:  collect -> research -> TriageAgent --handoff--> <Specialist>

Every specialist shares the same calibration (advisor.DECISION_GUIDELINES) so verdicts
stay consistent; each adds domain-specific patterns and tailored suggested actions.
"""
from __future__ import annotations

import weave
from agents import Agent, Runner

from ..config import get_settings
from ..models import ResearchFindings, ScreenFacts, SimilarExample
from ._helpers import vision_input
from .advisor import COMMON_INTRO, DECISION_GUIDELINES, AdvisorDecision, _context_block


def _make_specialist(name: str, specialty: str) -> Agent:
    return Agent(
        name=name,
        model=get_settings().openai_model,
        instructions=(
            f"You are a fraud specialist focused on {specialty}\n\n"
            + COMMON_INTRO
            + "Apply your specialist expertise for this category, then follow the rules below.\n\n"
            + DECISION_GUIDELINES
        ),
        output_type=AdvisorDecision,
    )


# --- Specialist roster ---
phishing_specialist = _make_specialist(
    "PhishingEmailSpecialist",
    "PHISHING EMAILS that steal credentials. Hallmarks: spoofed/lookalike sender domains, "
    "'your account is locked / verify now' urgency, fake login pages, mismatched link targets, "
    "requests to confirm passwords or banking details. Tailor actions to: don't click links, "
    "navigate to the real site manually, change password if already entered.",
)
tech_support_specialist = _make_specialist(
    "TechSupportScamSpecialist",
    "FAKE TECH-SUPPORT / VIRUS-ALERT scams. Hallmarks: full-screen 'your computer is infected' "
    "pop-ups, fake Microsoft/Apple warnings, a phone number to call, demands to install remote-access "
    "tools (AnyDesk, TeamViewer), browser lock pages. Tailor actions to: do NOT call the number, do "
    "not install remote tools, force-close the browser/tab, run a real AV scan.",
)
crypto_specialist = _make_specialist(
    "CryptoScamSpecialist",
    "CRYPTOCURRENCY scams. Hallmarks: 'send X get 2X back' giveaways, fake investment/trading "
    "platforms, romance/'pig-butchering' lures, requests for wallet seed phrases or to connect a "
    "wallet to an unknown site. Tailor actions to: never share a seed phrase, never send crypto to "
    "'double' it, disconnect the wallet.",
)
malicious_download_specialist = _make_specialist(
    "MaliciousDownloadSpecialist",
    "MALICIOUS DOWNLOADS / LINKS. Hallmarks: fake software updates ('your Flash/Java is outdated'), "
    "cracked-software or fake installer sites, unexpected .exe/.dmg/.zip downloads, suspicious "
    "attachments, shortened/obfuscated URLs. Tailor actions to: don't open the file, delete the "
    "download, only update software from official sources.",
)
advance_fee_specialist = _make_specialist(
    "AdvanceFeeScamSpecialist",
    "ADVANCE-FEE / 419 scams. Hallmarks: an inheritance, lottery, or large sum you can 'unlock' by "
    "first paying a fee/tax/processing charge; foreign official or 'prince' narratives. Tailor "
    "actions to: never pay upfront to receive money, stop contact.",
)
lottery_specialist = _make_specialist(
    "LotterySweepstakesSpecialist",
    "LOTTERY / SWEEPSTAKES / PRIZE scams. Hallmarks: 'you won' a prize you never entered, claim by "
    "paying fees/taxes or handing over personal/banking info. Tailor actions to: legitimate lotteries "
    "never require upfront payment; do not share details.",
)
employment_specialist = _make_specialist(
    "FakeEmploymentSpecialist",
    "FAKE JOB / EMPLOYMENT scams. Hallmarks: unsolicited too-good offers, upfront payment for "
    "'equipment/training', overpayment check-cashing or money-mule tasks, vague recruiters using "
    "personal email. Tailor actions to: never pay to get a job, never forward money, verify the "
    "employer independently.",
)
# Fallback: handles legitimate/safe content AND scams that don't fit a specific category.
general_specialist = _make_specialist(
    "GeneralAdvisor",
    "GENERAL content assessment — legitimate/benign screens, or suspicious content that does not "
    "clearly fit a single scam category (e.g. impersonation, grandparent/emergency scams, romance "
    "scams, package-delivery fee scams). Give a balanced verdict and sensible actions.",
)

SPECIALISTS = [
    phishing_specialist,
    tech_support_specialist,
    crypto_specialist,
    malicious_download_specialist,
    advance_fee_specialist,
    lottery_specialist,
    employment_specialist,
    general_specialist,
]


triage_agent = Agent(
    name="TriageAgent",
    model=get_settings().openai_model,
    instructions=(
        "You are a triage router for a scam-detection system. Look at the screenshot, the structured "
        "FACTS, and the RESEARCH findings, then HAND OFF to the single most appropriate specialist. "
        "Do NOT analyze or answer yourself — your only job is to route.\n\n"
        "Routing guide:\n"
        "- Phishing email stealing credentials / fake login / 'verify your account' -> PhishingEmailSpecialist\n"
        "- Fake virus alert / tech-support pop-up / 'call Microsoft' / remote-access -> TechSupportScamSpecialist\n"
        "- Crypto giveaway / investment / wallet seed-phrase -> CryptoScamSpecialist\n"
        "- Fake update / suspicious download / malicious link or attachment -> MaliciousDownloadSpecialist\n"
        "- Pay a fee to unlock a large sum / inheritance / 419 -> AdvanceFeeScamSpecialist\n"
        "- 'You won' a lottery/prize/sweepstakes -> LotterySweepstakesSpecialist\n"
        "- Too-good job offer / upfront equipment payment / money-mule -> FakeEmploymentSpecialist\n"
        "- Anything that looks LEGITIMATE/benign, or a scam that doesn't fit the above "
        "(impersonation, grandparent emergency, romance, package-fee, etc.) -> GeneralAdvisor\n\n"
        "Always hand off to exactly one specialist."
    ),
    handoffs=SPECIALISTS,
)


def _build_prompt(
    facts: ScreenFacts,
    research: ResearchFindings,
    similar_scams: list[SimilarExample],
    similar_legit: list[SimilarExample],
    trust_note: str,
) -> str:
    prompt = (
        "Route this screen to the right specialist, who will make the final scam assessment "
        "using the screenshot plus this context.\n\n"
        + _context_block(facts, research, similar_scams, similar_legit)
    )
    if trust_note:
        prompt += f"\n\nTRUSTED-CONTACTS: {trust_note}"
    return prompt


@weave.op()
async def decide_via_triage(
    image_b64: str | None,
    facts: ScreenFacts,
    research: ResearchFindings,
    similar_scams: list[SimilarExample],
    similar_legit: list[SimilarExample],
    trust_note: str = "",
) -> tuple[AdvisorDecision, str]:
    """Run triage -> specialist handoff. Returns (decision, specialist_name)."""
    prompt = _build_prompt(facts, research, similar_scams, similar_legit, trust_note)
    inp = vision_input(prompt, image_b64)

    result = await Runner.run(triage_agent, inp)
    decision = result.final_output
    handled_by = getattr(result.last_agent, "name", triage_agent.name)

    # Safety net: if triage answered instead of handing off, run the general specialist.
    if not isinstance(decision, AdvisorDecision):
        fallback = await Runner.run(general_specialist, inp)
        decision = fallback.final_output
        handled_by = general_specialist.name

    return decision, handled_by
