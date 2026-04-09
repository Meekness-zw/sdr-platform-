"""
Sourcing — Layer 1: LinkedIn via PhantomBuster

LinkedIn Sales Navigator has no official automation API.
We use PhantomBuster's "LinkedIn Search Export" phantom to export
leads from saved Sales Nav searches within LinkedIn's daily limits:
  - ~100 profile views/day
  - ~20 connection requests/day

PhantomBuster docs: https://phantombuster.com/automations/linkedin

Wire PHANTOMBUSTER_API_KEY in .env to activate.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from models.prospect import Prospect, TriggerEvent

PHANTOMBUSTER_BASE_URL = "https://api.phantombuster.com/api/v2"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_prospects_linkedin(
    phantom_id: str | None = None,
) -> list[Prospect]:
    """
    Launch a PhantomBuster LinkedIn Search Export phantom and return results.

    phantom_id: the PhantomBuster agent ID for the Sales Nav search export.
    Returns raw Prospect objects sourced from LinkedIn.
    """
    # TODO: Wire credentials and implement
    # POST /agents/launch  { "id": phantom_id }
    # Then GET /agents/output { "id": phantom_id } to retrieve CSV/JSON results
    raise NotImplementedError("Wire PHANTOMBUSTER_API_KEY and configure phantom_id")


def detect_new_hire_triggers(prospects: list[Prospect]) -> list[Prospect]:
    """
    For each prospect, check if they started in their current role
    within the last 60 days. If so, attach TriggerEvent.NEW_EXEC_HIRE.

    Called after PhantomBuster exports include start_date field.
    """
    # TODO: Implement — check prospect.exec_hire_announced_at against 60-day window
    raise NotImplementedError("Implement new hire trigger detection")


def _map_linkedin_person(row: dict) -> Prospect:
    """Map a PhantomBuster LinkedIn export row to a Prospect model."""
    return Prospect(
        first_name=row.get("firstName", ""),
        last_name=row.get("lastName", ""),
        linkedin_url=row.get("linkedInProfileUrl"),
        job_title=row.get("title"),
        company_name=row.get("companyName", ""),
        company_domain=row.get("companyWebsite"),
        industry=row.get("companyIndustry"),
        headcount=_parse_headcount(row.get("companyStaffCount", "")),
        source="linkedin",
    )


def _parse_headcount(raw: str | int | None) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        raw = raw.replace(",", "").strip()
        try:
            return int(raw)
        except ValueError:
            pass
    return None
