"""
Enrichment: Clay API bridge.

Clay acts as a waterfall enrichment orchestrator — it pulls from
Apollo, Clearbit, LinkedIn, and other sources to fill:
  - email (verified)
  - LinkedIn URL
  - funding stage and amount
  - headcount
  - company domain

Wire CLAY_API_KEY in .env to activate.
"""

from __future__ import annotations

from models.prospect import Prospect


def enrich_via_clay(prospect: Prospect) -> Prospect:
    """
    Submit the prospect to Clay for waterfall enrichment.
    Updates email, linkedin_url, funding info, and headcount in place.
    """
    # TODO: Wire credentials and implement
    # POST to Clay table row via Clay API
    # Poll for enrichment completion, then read back enriched fields
    raise NotImplementedError("Wire CLAY_API_KEY and implement Clay enrichment")
