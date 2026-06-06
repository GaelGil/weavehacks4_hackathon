"""ResearchAgent (stage 2).

Takes the structured facts and gathers GROUNDED comparison evidence so the final
decision isn't a vibe check:
  - Redis vector search for the most similar KNOWN SCAMS and KNOWN-LEGIT messages.
  - Live web search to vet the sender domain / brand (is luma-mail.com really Luma?).

It outputs ResearchFindings (legitimacy vs scam indicators), and we also return the raw
comparison lists so the UI and the Advisor can use them.
"""
from __future__ import annotations

import json

import weave
from agents import Agent, Runner

from ..config import get_settings
from ..models import ResearchFindings, ScreenFacts, SimilarExample
from ..services.redis_store import get_store

# Web search is a hosted tool; not every account/model exposes it. Degrade gracefully.
try:
    from agents import WebSearchTool

    _WEB_TOOLS = [WebSearchTool()]
except Exception:  # noqa: BLE001
    _WEB_TOOLS = []


def _build_agent(with_web: bool) -> Agent:
    return Agent(
        name="ResearchAgent",
        model=get_settings().openai_model,
        tools=_WEB_TOOLS if with_web else [],
        instructions=(
            "You are a research agent vetting whether on-screen content is legitimate or a scam. "
            "You are given structured FACTS plus comparison examples of known scams and known-legit "
            "messages.\n\n"
            "If you have web search, you MUST actually use it before concluding. Run these searches:\n"
            "  a. The EXACT subject line / headline (e.g. the email subject) — this often surfaces the "
            "real event, product, or announcement page.\n"
            "  b. The sender name AND the brand/organization together (e.g. 'Anna Shive Weights & Biases') "
            "to check whether the named sender is a real, associated person/organizer.\n"
            "  c. The sender's DOMAIN to confirm whether it's a known, official sending domain. Many "
            "LEGITIMATE services send from odd-looking transactional subdomains (e.g. user.luma-mail.com "
            "for Luma) — never treat an unfamiliar-looking domain as scam evidence without verifying it.\n\n"
            "Then:\n"
            "- If a search POSITIVELY finds the matching event/page and a matching sender/host, record that "
            "as a strong legitimacy_indicator and quote what you found in web_findings.\n"
            "- Compare the facts to the scam vs legit examples and note which patterns match.\n"
            "- Fill legitimacy_indicators and scam_indicators with specific, evidence-based points.\n\n"
            "CRITICAL: Only list something as a scam_indicator if you have POSITIVE evidence for it (e.g. a "
            "search shows the brand warns about this, or the domain is a known lookalike). NEVER write "
            "'could not confirm X exists', 'sender not recognized', or 'no information found' as a "
            "scam_indicator — absence of evidence is NOT evidence of a scam. If you couldn't verify "
            "something, just say so neutrally in research_notes.\n"
            "Be balanced — list real evidence on BOTH sides. Do not output a final verdict; that is the "
            "Advisor's job."
        ),
        output_type=ResearchFindings,
    )


_research_agent = _build_agent(with_web=bool(_WEB_TOOLS))
_research_agent_no_web = _build_agent(with_web=False)


def _query_text(facts: ScreenFacts) -> str:
    return facts.raw_text or " ".join(
        x for x in [facts.brand_claimed, facts.sender_address, facts.subject, facts.body_summary] if x
    )


@weave.op()
async def research(
    facts: ScreenFacts,
) -> tuple[ResearchFindings, list[SimilarExample], list[SimilarExample]]:
    store = get_store()
    q = _query_text(facts)
    similar_scams = store.search_examples(q, k=3, label="scam") if q else []
    similar_legit = store.search_examples(q, k=3, label="legit") if q else []

    # Spell out the exact searches so the agent grounds instead of guessing.
    suggested_searches = [s for s in [
        facts.subject,
        f"{facts.sender_name} {facts.brand_claimed}".strip(),
        facts.sender_address.split("@")[-1] if "@" in facts.sender_address else facts.sender_address,
    ] if s]

    prompt = (
        "FACTS observed on screen:\n"
        + facts.model_dump_json(indent=2)
        + "\n\nRUN WEB SEARCHES for (at minimum):\n"
        + "\n".join(f"  - {q}" for q in suggested_searches)
        + "\n\nMost similar KNOWN SCAMS:\n"
        + (json.dumps([s.model_dump() for s in similar_scams], indent=2) or "(none)")
        + "\n\nMost similar KNOWN-LEGIT messages:\n"
        + (json.dumps([s.model_dump() for s in similar_legit], indent=2) or "(none)")
        + "\n\nSearch the web for the items above, then produce balanced, evidence-based findings."
    )

    try:
        result = await Runner.run(_research_agent, prompt)
    except Exception as e:  # noqa: BLE001 - web tool can fail; retry without it
        print(f"[researcher] web-enabled run failed ({e}); retrying without web search.")
        result = await Runner.run(_research_agent_no_web, prompt)

    return result.final_output, similar_scams, similar_legit
