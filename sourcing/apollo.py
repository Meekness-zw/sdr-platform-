"""
Sourcing — Layer 1: Apollo.io

Pulls contacts from Apollo filtered by ICP criteria.
Free tier: 50 exports/month.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import (
    ICP_HEADCOUNT_MAX,
    ICP_HEADCOUNT_MIN,
    ICP_JOB_TITLES,
    settings,
)
from models.prospect import FundingStage, Prospect

log = structlog.get_logger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/v1"

# ICP industry keywords mapped to Apollo's organization_industry_tag_ids
# Apollo uses string-based industry names in their people search
ICP_APOLLO_INDUSTRIES = [
    "Information Technology and Services",
    "Computer Software",
    "Internet",
    "Financial Services",
    "Hospital & Health Care",
    "Health, Wellness and Fitness",
    "Management Consulting",
    "Marketing and Advertising",
    "E-Learning",
    "Retail",
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_prospects_apollo(
    max_results: int = 10,
    page: int = 1,
) -> list[Prospect]:
    """
    Pull contacts from Apollo matching ICP criteria.
    Returns a list of raw (unenriched, unscored) Prospect objects.
    """
    if not settings.apollo_api_key:
        raise RuntimeError("APOLLO_API_KEY not set in .env")

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }

    payload = {
        "api_key": settings.apollo_api_key,
        "page": page,
        "per_page": min(max_results, 25),
        "person_titles": ICP_JOB_TITLES,
        "organization_num_employees_ranges": [
            f"{ICP_HEADCOUNT_MIN},{ICP_HEADCOUNT_MAX}"
        ],
    }

    response = httpx.post(
        f"{APOLLO_BASE_URL}/mixed_people/search",
        headers=headers,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    people = data.get("people", [])
    log.info("apollo_fetch_complete", count=len(people), page=page)

    return [_map_apollo_person(p) for p in people if p.get("first_name")]


def _map_apollo_person(person: dict) -> Prospect:
    """Map a raw Apollo person dict to a Prospect model."""
    org = person.get("organization") or {}
    employment = person.get("employment_history", [])
    current_job = next((e for e in employment if e.get("current")), {})

    return Prospect(
        first_name=person.get("first_name", ""),
        last_name=person.get("last_name", ""),
        email=person.get("email"),
        linkedin_url=person.get("linkedin_url"),
        job_title=person.get("title") or current_job.get("title"),
        company_name=org.get("name") or person.get("organization_name", ""),
        company_domain=org.get("website_url") or org.get("primary_domain"),
        industry=org.get("industry"),
        headcount=_parse_headcount(org.get("estimated_num_employees")),
        funding_stage=_map_funding_stage(org.get("latest_funding_stage", "")),
        source="apollo",
    )


def _parse_headcount(raw) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.replace(",", "").strip())
        except ValueError:
            pass
    return None


def _map_funding_stage(raw: str) -> FundingStage:
    if not raw:
        return FundingStage.UNKNOWN
    mapping = {
        "series_a": FundingStage.SERIES_A,
        "series_b": FundingStage.SERIES_B,
        "series_c": FundingStage.SERIES_C,
        "series a": FundingStage.SERIES_A,
        "series b": FundingStage.SERIES_B,
        "series c": FundingStage.SERIES_C,
        "private_equity": FundingStage.PE_BACKED,
        "private equity": FundingStage.PE_BACKED,
        "bootstrapped": FundingStage.BOOTSTRAPPED,
        "seed": FundingStage.SEED,
        "pre_seed": FundingStage.PRE_SEED,
        "angel": FundingStage.SEED,
    }
    return mapping.get(raw.lower().strip(), FundingStage.UNKNOWN)
