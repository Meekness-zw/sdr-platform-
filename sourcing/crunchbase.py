"""
Sourcing — Layer 1: Crunchbase Signal Monitor

Polls Crunchbase for new funding rounds matching ICP criteria.
Detected rounds attach TriggerEvent.FUNDING_ROUND to the prospect (25 pts).

API docs: https://data.crunchbase.com/docs
Rate limits: 200 calls/day (Basic $29/mo) — schedule outside peak hours.

Wire CRUNCHBASE_API_KEY in .env to activate.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from models.prospect import FundingStage, Prospect, TriggerEvent

CRUNCHBASE_BASE_URL = "https://api.crunchbase.com/api/v4"
FUNDING_LOOKBACK_DAYS = 30


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def poll_funding_signals(
    industries: list[str] | None = None,
) -> list[Prospect]:
    """
    Poll Crunchbase for companies that received funding in the last 30 days.

    Returns Prospect stubs with:
      - company_name, funding_stage, funding_amount_usd
      - triggers = [TriggerEvent.FUNDING_ROUND]
      - funding_announced_at

    These stubs are passed to enrichment to fill contact details.
    """
    # TODO: Wire credentials and implement
    # GET /searches/funding_rounds with filters:
    # {
    #   "field_ids": ["funded_organization_identifier", "announced_on",
    #                 "investment_type", "money_raised"],
    #   "predicate_values": [
    #     { "field_id": "announced_on", "operator_id": "gte",
    #       "values": [since_date.isoformat()] }
    #   ]
    # }
    raise NotImplementedError("Wire CRUNCHBASE_API_KEY and implement funding poll")


def _map_funding_round(round_data: dict) -> Prospect:
    """Map a Crunchbase funding round dict to a Prospect stub."""
    org = round_data.get("funded_organization_identifier", {})
    stage = round_data.get("investment_type", "")
    amount = round_data.get("money_raised", {}).get("value_usd")
    announced = round_data.get("announced_on")

    return Prospect(
        first_name="",
        last_name="",
        company_name=org.get("value", ""),
        funding_stage=_map_crunchbase_stage(stage),
        funding_amount_usd=amount,
        triggers=[TriggerEvent.FUNDING_ROUND],
        funding_announced_at=datetime.fromisoformat(announced) if announced else None,
        source="crunchbase",
    )


def _map_crunchbase_stage(raw: str) -> FundingStage:
    mapping = {
        "series_a": FundingStage.SERIES_A,
        "series_b": FundingStage.SERIES_B,
        "series_c": FundingStage.SERIES_C,
        "private_equity": FundingStage.PE_BACKED,
        "angel": FundingStage.SEED,
        "seed": FundingStage.SEED,
        "pre_seed": FundingStage.PRE_SEED,
    }
    return mapping.get(raw.lower(), FundingStage.UNKNOWN)
