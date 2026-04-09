"""
GPT-4o prompt templates for personalized outreach openers.

One system prompt per persona. The opener is injected into Instantly
as the {{personalOpener}} custom variable, replacing the first 2–3
sentences of Day 1 email.
"""

from __future__ import annotations

from models.prospect import Persona

SYSTEM_PROMPT_BASE = """
You are a world-class B2B sales copywriter. Write a 2–3 sentence personalized
email opener for a cold outreach email. The opener must:
- Reference a specific, real detail about their company or role (not generic)
- Connect that detail to the pain of AI tool sprawl, unclear ROI, or workforce change
- Sound like it was written by a peer, not a vendor — direct, no fluff
- Never mention "AI advisor" or "consulting" — just the problem
- End with no question; the rest of the email handles the ask

Return ONLY the opener. No subject line. No greeting. No sign-off.
""".strip()

PERSONA_CONTEXT: dict[Persona, str] = {
    Persona.CEO: (
        "The recipient is the CEO or Founder. They care about ROI, competitive positioning, "
        "and whether AI investments are paying off. They are time-poor and skeptical of vendors. "
        "Speak operator to operator."
    ),
    Persona.COO: (
        "The recipient is a COO, Head of Operations, or Chief of Staff. They are dealing with "
        "tool sprawl, overlapping platforms, and failed implementation projects. They own the budget "
        "and feel the pain daily. Be specific about operational inefficiency."
    ),
    Persona.VP_PEOPLE: (
        "The recipient is a VP People, CHRO, or Head of People. They are navigating the board-level "
        "AI and workforce question — caught between advocating for automation and protecting their team. "
        "Frame the opener around getting ahead of that conversation, not reacting to it."
    ),
}

USER_PROMPT_TEMPLATE = """
Prospect details:
- Name: {first_name} {last_name}
- Title: {job_title}
- Company: {company_name}
- Industry: {industry}
- Headcount: {headcount}
- Funding stage: {funding_stage}
- Recent trigger: {trigger_summary}
- Recent news: {recent_news}
- LinkedIn post excerpt: {linkedin_post}

Write the personalized opener.
""".strip()


def build_prompt(
    first_name: str,
    last_name: str,
    job_title: str | None,
    company_name: str,
    industry: str | None,
    headcount: int | None,
    funding_stage: str,
    trigger_summary: str,
    recent_news: str | None,
    linkedin_post: str | None,
    persona: Persona,
) -> tuple[str, str]:
    """
    Return (system_prompt, user_prompt) for the GPT-4o call.
    """
    persona_context = PERSONA_CONTEXT.get(persona, "")
    system = f"{SYSTEM_PROMPT_BASE}\n\n{persona_context}"

    user = USER_PROMPT_TEMPLATE.format(
        first_name=first_name,
        last_name=last_name,
        job_title=job_title or "Unknown",
        company_name=company_name,
        industry=industry or "Unknown",
        headcount=headcount or "Unknown",
        funding_stage=funding_stage,
        trigger_summary=trigger_summary or "None detected",
        recent_news=recent_news or "None available",
        linkedin_post=linkedin_post or "None available",
    )

    return system, user
