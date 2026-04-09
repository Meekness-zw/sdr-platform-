"""
Personalization — Layer 4 (part 1): GPT-4o opener generation.

Generates a 2–3 sentence personalized opener for each prospect
using enrichment data and persona-matched prompt templates.

The opener is stored in prospect.personal_opener and injected
into Instantly as {{personalOpener}}.

Wire OPENAI_API_KEY in .env to activate.
"""

from __future__ import annotations

import structlog

from config.settings import settings
from models.prospect import Persona, Prospect, TriggerEvent
from .prompts import build_prompt

log = structlog.get_logger(__name__)

_TRIGGER_LABELS: dict[str, str] = {
    TriggerEvent.FUNDING_ROUND.value: "recently announced a funding round",
    TriggerEvent.NEW_EXEC_HIRE.value: "recently hired a new executive",
    TriggerEvent.AI_JOB_POSTING.value: "is actively hiring for AI/automation roles",
    TriggerEvent.AI_STRATEGY_STATEMENT.value: "publicly discussed an AI strategy",
    TriggerEvent.LAYOFF_OR_RESTRUCTURE.value: "went through a recent layoff or restructure",
    TriggerEvent.EXEC_AI_POST.value: "posted about AI challenges on LinkedIn",
    TriggerEvent.MA_ACQUISITION.value: "was recently involved in an M&A event",
}


def generate_opener(prospect: Prospect) -> Prospect:
    """
    Call GPT-4o to generate a personalized opener for the prospect.
    Populates prospect.personal_opener.
    Skips if persona is UNKNOWN (no sequence to enroll in).
    """
    if prospect.persona == Persona.UNKNOWN:
        log.info("opener_skipped_unknown_persona", name=prospect.full_name())
        return prospect

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set — cannot generate opener")

    from openai import OpenAI

    trigger_summary = _summarize_triggers(prospect)
    system_prompt, user_prompt = build_prompt(
        first_name=prospect.first_name,
        last_name=prospect.last_name,
        job_title=prospect.job_title,
        company_name=prospect.company_name,
        industry=prospect.industry,
        headcount=prospect.headcount,
        funding_stage=prospect.funding_stage.value,
        trigger_summary=trigger_summary,
        recent_news=prospect.recent_news_summary,
        linkedin_post=prospect.recent_linkedin_post,
        persona=prospect.persona,
    )

    client = OpenAI(api_key=settings.openai_api_key)  # noqa: F821
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=150,
    )

    opener = response.choices[0].message.content.strip()
    prospect.personal_opener = opener

    log.info("opener_generated", name=prospect.full_name(), persona=prospect.persona.value)
    return prospect


def _summarize_triggers(prospect: Prospect) -> str:
    if not prospect.triggers:
        return "No specific trigger detected"
    labels = [_TRIGGER_LABELS.get(t.value, t.value) for t in prospect.triggers]
    return "; ".join(labels)
