"""
Sequencing — Layer 4 (part 3): LinkedIn automation via Expandi.

Sends LinkedIn connection requests coordinated with email sequences:
  - Email Day 1  →  LinkedIn connection request Day 3
  - Email Day 5  →  LinkedIn DM Day 8 (if connected)

Daily LinkedIn limits (enforced by Expandi): ~20 connection requests/day.
Do not exceed LinkedIn's daily action limits to avoid account restriction.

Wire EXPANDI_API_KEY in .env to activate.
"""

from __future__ import annotations

import structlog

from config.settings import settings
from models.prospect import Prospect

log = structlog.get_logger(__name__)


def send_linkedin_connection(prospect: Prospect, message: str | None = None) -> bool:
    """
    Queue a LinkedIn connection request for the prospect via Expandi.

    message: the personalized connection note (160 char limit on LinkedIn).
    Returns True if queued successfully.
    """
    if not prospect.linkedin_url:
        log.warning("linkedin_skipped_no_url", name=prospect.full_name())
        return False

    # TODO: Wire credentials and implement
    # POST to Expandi campaign API to add the prospect as a lead
    # with the connection note pre-filled
    raise NotImplementedError("Wire EXPANDI_API_KEY and implement LinkedIn connection")


def build_connection_note(prospect: Prospect) -> str:
    """
    Generate a short LinkedIn connection note (≤160 chars) for the prospect.
    References their company or industry for relevance.
    """
    base = (
        f"{prospect.first_name} — I work with {prospect.industry or 'growth-stage'} "
        f"companies on AI stack advisory. Would love to connect."
    )
    return base[:160]
