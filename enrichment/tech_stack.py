"""
Enrichment: BuiltWith tech stack detection.

Detects the technology stack for a company domain.
Useful for identifying prospects using legacy tools we can displace,
or validating tech-forward companies in our ICP.

Wire BUILTWITH_API_KEY in .env to activate.
"""

from __future__ import annotations

from models.prospect import Prospect

BUILTWITH_BASE_URL = "https://api.builtwith.com/v21/api.json"


def enrich_tech_stack(prospect: Prospect) -> Prospect:
    """
    Fetch tech stack for prospect.company_domain and populate prospect.tech_stack.
    Skips if company_domain is not set.
    """
    if not prospect.company_domain:
        return prospect

    # TODO: Wire credentials and implement
    # GET {BUILTWITH_BASE_URL}?KEY={api_key}&LOOKUP={domain}
    # Parse response["Results"][0]["Result"]["Paths"] for technology names
    raise NotImplementedError("Wire BUILTWITH_API_KEY and implement tech stack fetch")
