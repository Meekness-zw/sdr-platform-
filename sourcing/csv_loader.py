"""
Sourcing — CSV loader (Apollo free tier workaround).

Reads a CSV exported from Apollo.io and maps each row to a Prospect.

How to export from Apollo:
  1. Log into app.apollo.io
  2. Search People with filters:
       - Job Titles: CEO, Founder, COO, Chief Operating Officer,
                     VP People, CHRO, Head of People, Chief of Staff
       - # Employees: 50–350
       - Industry: Computer Software, Information Technology,
                   Financial Services, Hospital & Health Care, etc.
  3. Select all results → click Export → CSV
  4. Save the file into this project folder (e.g. prospects.csv)
  5. Run: python main.py --from-csv prospects.csv

Apollo CSV columns we use (others are ignored):
  First Name, Last Name, Email, Title, Company, Website,
  Industry, # Employees, LinkedIn Url, City, State, Country
"""

from __future__ import annotations

import csv
from pathlib import Path

import structlog

from models.prospect import FundingStage, Prospect

log = structlog.get_logger(__name__)

# Map Apollo CSV column headers to our field names
APOLLO_COLUMN_MAP = {
    "first name": "first_name",
    "last name": "last_name",
    "email": "email",
    "title": "job_title",
    "company": "company_name",
    "company name": "company_name",
    "website": "company_domain",
    "industry": "industry",
    "# employees": "headcount",
    "employees": "headcount",
    "number of employees": "headcount",
    "linkedin url": "linkedin_url",
    "person linkedin url": "linkedin_url",
    "technologies": "tech_stack",
    "latest funding": "funding_stage",
    "total funding": "funding_amount",
    "keywords": "keywords",
}


def load_from_csv(filepath: str | Path, max_rows: int = 200) -> list[Prospect]:
    """
    Load prospects from an Apollo CSV export.
    Skips rows missing both first name and company name.
    Returns a list of raw (unscored) Prospect objects.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    prospects = []

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # Normalize column headers to lowercase for flexible matching
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        normalized_headers = {h.lower().strip(): h for h in reader.fieldnames}

        for i, row in enumerate(reader):
            if i >= max_rows:
                break

            # Remap columns using normalized headers
            mapped = {}
            for norm_key, field_name in APOLLO_COLUMN_MAP.items():
                if norm_key in normalized_headers:
                    original_key = normalized_headers[norm_key]
                    mapped[field_name] = row.get(original_key, "").strip()

            first_name = mapped.get("first_name", "")
            last_name = mapped.get("last_name", "")
            company = mapped.get("company_name", "")

            if not first_name and not company:
                continue

            headcount = _parse_headcount(mapped.get("headcount"))
            tech_stack = _parse_tech_stack(mapped.get("tech_stack", ""))
            funding_stage = _map_funding_stage(mapped.get("funding_stage", ""))
            funding_amount = _parse_funding_amount(mapped.get("funding_amount", ""))

            prospects.append(Prospect(
                first_name=first_name,
                last_name=last_name,
                email=mapped.get("email") or None,
                job_title=mapped.get("job_title") or None,
                company_name=company,
                company_domain=mapped.get("company_domain") or None,
                industry=mapped.get("industry") or None,
                headcount=headcount,
                linkedin_url=mapped.get("linkedin_url") or None,
                tech_stack=tech_stack,
                funding_stage=funding_stage,
                funding_amount_usd=funding_amount,
                source="apollo_csv",
            ))

    log.info("csv_loaded", file=str(path), count=len(prospects))
    return prospects


def _parse_tech_stack(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_funding_amount(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.replace(",", "").replace("$", "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def _map_funding_stage(raw: str) -> FundingStage:
    if not raw:
        return FundingStage.UNKNOWN
    r = raw.lower().strip()
    mapping = {
        "series a": FundingStage.SERIES_A,
        "series_a": FundingStage.SERIES_A,
        "series b": FundingStage.SERIES_B,
        "series_b": FundingStage.SERIES_B,
        "series c": FundingStage.SERIES_C,
        "series_c": FundingStage.SERIES_C,
        "private equity": FundingStage.PE_BACKED,
        "pe": FundingStage.PE_BACKED,
        "bootstrapped": FundingStage.BOOTSTRAPPED,
        "seed": FundingStage.SEED,
        "angel": FundingStage.SEED,
        "pre-seed": FundingStage.PRE_SEED,
        "pre_seed": FundingStage.PRE_SEED,
    }
    return mapping.get(r, FundingStage.UNKNOWN)


def _parse_headcount(raw: str | None) -> int | None:
    if not raw:
        return None
    # Handle ranges like "51-200" — take the midpoint
    raw = raw.replace(",", "").strip()
    if "-" in raw:
        parts = raw.split("-")
        try:
            low = int(parts[0].strip())
            high = int(parts[1].strip())
            return (low + high) // 2
        except ValueError:
            pass
    # Handle "1,001-5,000" style
    try:
        return int(raw)
    except ValueError:
        pass
    return None
