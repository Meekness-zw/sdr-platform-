"""
Enrichment — Layer 2 of the SDR pipeline.

Fills gaps in prospect data by calling enrichment sources in sequence:
  1. Clay     — waterfall email + LinkedIn URL + funding info
  2. BuiltWith — tech stack
  3. GPT-4o + Google News — recent news summary (last 30 days)

The enricher runs each step and updates the Prospect in place.
"""

from __future__ import annotations

import structlog

from models.prospect import Prospect
from .clay import enrich_via_clay
from .tech_stack import enrich_tech_stack
from .news import enrich_news_summary

log = structlog.get_logger(__name__)


def enrich_prospect(prospect: Prospect) -> Prospect:
    """
    Run all enrichment steps on a prospect.
    Steps are additive — each fills fields not already populated.
    Failures in individual steps are logged and skipped, not raised.
    """
    log.info("enrichment_start", name=prospect.full_name(), company=prospect.company_name)

    for step_name, step_fn in [
        ("clay", enrich_via_clay),
        ("tech_stack", enrich_tech_stack),
        ("news", enrich_news_summary),
    ]:
        try:
            prospect = step_fn(prospect)
            log.info("enrichment_step_complete", step=step_name, name=prospect.full_name())
        except NotImplementedError:
            log.debug("enrichment_step_not_implemented", step=step_name)
        except Exception as exc:
            log.warning("enrichment_step_failed", step=step_name, error=str(exc))

    return prospect
