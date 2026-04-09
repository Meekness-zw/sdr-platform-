"""
Sequencing — Layer 4 (part 2): Instantly.ai email enrollment.

Enrolls prospects into the persona-matched campaign via Instantly API.
Injects {{personalOpener}} as a custom variable so GPT-4o openers
appear in Day 1 emails.

Campaign IDs are set in .env:
  INSTANTLY_CAMPAIGN_CEO
  INSTANTLY_CAMPAIGN_COO
  INSTANTLY_CAMPAIGN_VP_PEOPLE

Rate limits: 30–50 emails/day/inbox during warmup ramp.
Start with 2–3 warmed inboxes minimum.

Wire INSTANTLY_API_KEY in .env to activate.
"""

from __future__ import annotations

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from models.prospect import Persona, Prospect, SequenceStatus, Tier

log = structlog.get_logger(__name__)

INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v1"


def enroll_in_sequence(prospect: Prospect) -> Prospect:
    """
    Enroll a prospect in the Instantly campaign matched to their persona.

    Only enrolls Tier 1 (HOT) and Tier 2 (WARM) prospects.
    Tier 3 and DISQUALIFIED are skipped — added to HubSpot nurture only.

    Sets:
      prospect.instantly_contact_id
      prospect.sequence_status = ENROLLED
    """
    if prospect.tier not in (Tier.HOT, Tier.WARM):
        log.info(
            "enrollment_skipped",
            name=prospect.full_name(),
            tier=prospect.tier.value if prospect.tier else "none",
        )
        return prospect

    if prospect.persona == Persona.UNKNOWN:
        log.warning("enrollment_skipped_unknown_persona", name=prospect.full_name())
        return prospect

    campaign_id = settings.instantly_campaign_ids.get(prospect.persona.value, "")
    if not campaign_id:
        raise RuntimeError(
            f"No Instantly campaign ID configured for persona {prospect.persona.value}. "
            f"Set INSTANTLY_CAMPAIGN_{prospect.persona.value} in .env"
        )

    # TODO: Wire credentials and implement
    # POST {INSTANTLY_BASE_URL}/lead/add
    # {
    #   "api_key": settings.instantly_api_key,
    #   "campaign_id": campaign_id,
    #   "email": prospect.email,
    #   "first_name": prospect.first_name,
    #   "last_name": prospect.last_name,
    #   "company_name": prospect.company_name,
    #   "custom_variables": {"personalOpener": prospect.personal_opener or ""},
    # }
    raise NotImplementedError("Wire INSTANTLY_API_KEY and implement enrollment")


def _get_campaign_id(persona: Persona) -> str:
    return settings.instantly_campaign_ids.get(persona.value, "")
