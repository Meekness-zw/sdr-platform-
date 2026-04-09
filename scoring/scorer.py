"""
Scoring engine — Layer 3 of the SDR pipeline.

Assigns a composite score (0–100) to each prospect based on:
  - Firmographic fit:  0–40 pts  (industry + headcount + funding stage)
  - Intent/triggers:  0–60 pts  (real-time trigger events detected)

Score thresholds:
  70–100  →  Tier 1 HOT        enroll in Triggered Sequence + Slack alert
  45–69   →  Tier 2 WARM       enroll in standard persona sequence within 48h
  25–44   →  Tier 3 COOL       nurture list only, re-score monthly
  0–24    →  DISQUALIFIED       archive in HubSpot, do not contact
"""

from __future__ import annotations

import structlog

from models.prospect import FundingStage, Persona, Prospect, Tier, TriggerEvent
from config.settings import (
    BOOTSTRAPPED_ARR_SCORE,
    BOOTSTRAPPED_ARR_THRESHOLD_USD,
    FUNDING_SCORE_DEFAULT,
    FUNDING_SCORES,
    HEADCOUNT_SCORE_DEFAULT,
    HEADCOUNT_SCORES,
    INDUSTRY_SCORE_DEFAULT,
    INDUSTRY_SCORES,
    PERSONA_TITLE_MAP,
    TIER_COOL_MIN,
    TIER_HOT_MIN,
    TIER_WARM_MIN,
    TRIGGER_SCORES,
)

log = structlog.get_logger(__name__)


# ── Firmographic Scoring (max 40 pts) ─────────────────────────────────────────

def _score_industry(industry: str | None) -> int:
    if not industry:
        return INDUSTRY_SCORE_DEFAULT
    normalized = industry.lower().strip()
    for key, points in INDUSTRY_SCORES.items():
        if key in normalized:
            return points
    return INDUSTRY_SCORE_DEFAULT


def _score_headcount(headcount: int | None) -> int:
    if headcount is None:
        return HEADCOUNT_SCORE_DEFAULT
    for (low, high), points in HEADCOUNT_SCORES:
        if low <= headcount <= high:
            return points
    return HEADCOUNT_SCORE_DEFAULT


def _score_funding(
    funding_stage: FundingStage,
    arr_signal_usd: float | None,
) -> int:
    if funding_stage == FundingStage.BOOTSTRAPPED:
        if arr_signal_usd and arr_signal_usd >= BOOTSTRAPPED_ARR_THRESHOLD_USD:
            return BOOTSTRAPPED_ARR_SCORE
        return FUNDING_SCORE_DEFAULT

    return FUNDING_SCORES.get(funding_stage.value, FUNDING_SCORE_DEFAULT)


def firmographic_score(prospect: Prospect) -> int:
    """Return firmographic score capped at 40 points."""
    score = (
        _score_industry(prospect.industry)
        + _score_headcount(prospect.headcount)
        + _score_funding(prospect.funding_stage, prospect.arr_signal_usd)
    )
    return min(score, 40)


# ── Intent / Trigger Scoring (max 60 pts) ─────────────────────────────────────

def intent_score(prospect: Prospect) -> int:
    """
    Sum trigger event points. Each trigger type can only score once
    (deduped via set). Capped at 60 points.
    """
    seen: set[str] = set()
    total = 0
    for trigger in prospect.triggers:
        if trigger.value not in seen:
            seen.add(trigger.value)
            total += TRIGGER_SCORES.get(trigger.value, 0)
    return min(total, 60)


# ── Persona Assignment ─────────────────────────────────────────────────────────

def assign_persona(prospect: Prospect) -> Persona:
    """
    Map job title to one of three outreach personas.
    Falls back to UNKNOWN if no match — UNKNOWN prospects are not enrolled
    in sequences until manually reviewed.
    """
    if not prospect.job_title:
        return Persona.UNKNOWN
    title_lower = prospect.job_title.lower()
    for persona_name, keywords in PERSONA_TITLE_MAP.items():
        if any(kw in title_lower for kw in keywords):
            return Persona(persona_name)
    return Persona.UNKNOWN


# ── Tier Assignment ────────────────────────────────────────────────────────────

def _assign_tier(composite: int) -> Tier:
    if composite >= TIER_HOT_MIN:
        return Tier.HOT
    if composite >= TIER_WARM_MIN:
        return Tier.WARM
    if composite >= TIER_COOL_MIN:
        return Tier.COOL
    return Tier.DISQUALIFIED


# ── Main Entry Point ──────────────────────────────────────────────────────────

def score_prospect(prospect: Prospect) -> Prospect:
    """
    Score a prospect in place and return it with updated scores and tier.

    Sets:
      prospect.firmographic_score
      prospect.intent_score
      prospect.composite_score
      prospect.tier
      prospect.persona
    """
    f_score = firmographic_score(prospect)
    i_score = intent_score(prospect)
    composite = f_score + i_score
    tier = _assign_tier(composite)
    persona = assign_persona(prospect)

    prospect.firmographic_score = f_score
    prospect.intent_score = i_score
    prospect.composite_score = composite
    prospect.tier = tier
    prospect.persona = persona

    if tier == Tier.DISQUALIFIED and not prospect.disqualified_reason:
        prospect.disqualified_reason = f"Score {composite} below threshold ({TIER_COOL_MIN})"

    log.info(
        "prospect_scored",
        name=prospect.full_name(),
        company=prospect.company_name,
        firmographic=f_score,
        intent=i_score,
        composite=composite,
        tier=tier.value,
        persona=persona.value,
    )

    return prospect
