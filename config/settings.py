from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


# ── Scoring Weights ────────────────────────────────────────────────────────────
# Firmographic max: 40 pts  |  Intent/Trigger max: 60 pts  |  Total max: 100 pts

INDUSTRY_SCORES: dict[str, int] = {
    "saas": 15,
    "tech": 15,
    "software": 15,
    "fintech": 15,
    "financial technology": 15,
    "health tech": 12,
    "healthtech": 12,
    "digital health": 12,
    "professional services": 8,
    "e-commerce": 8,
    "ecommerce": 8,
}
INDUSTRY_SCORE_DEFAULT = 0

HEADCOUNT_SCORES: list[tuple[tuple[int, int], int]] = [
    ((80, 250), 15),
    ((50, 79), 10),
    ((251, 350), 10),
]
HEADCOUNT_SCORE_DEFAULT = 0

FUNDING_SCORES: dict[str, int] = {
    "series_a": 10,
    "series_b": 10,
    "series_c": 10,
    "pe_backed": 10,
    "bootstrapped": 0,   # overridden to 7 if ARR signal >= 5_000_000
}
FUNDING_SCORE_DEFAULT = 0
BOOTSTRAPPED_ARR_THRESHOLD_USD = 5_000_000
BOOTSTRAPPED_ARR_SCORE = 7

TRIGGER_SCORES: dict[str, int] = {
    "funding_round": 25,
    "new_exec_hire": 22,
    "ai_job_posting": 18,
    "ai_strategy": 15,
    "layoff": 15,
    "exec_ai_post": 12,
    "ma_acquisition": 10,
}

# ── Tier Thresholds ───────────────────────────────────────────────────────────
TIER_HOT_MIN = 70
TIER_WARM_MIN = 45
TIER_COOL_MIN = 25

# ── ICP Sourcing Filters ──────────────────────────────────────────────────────
ICP_INDUSTRIES = [
    "saas", "software", "tech", "fintech", "financial technology",
    "health tech", "healthtech", "digital health",
    "professional services", "e-commerce", "ecommerce",
]
ICP_HEADCOUNT_MIN = 50
ICP_HEADCOUNT_MAX = 350
ICP_FUNDING_STAGES = [
    "series_a", "series_b", "series_c", "pe_backed", "bootstrapped",
]
ICP_JOB_TITLES = [
    "CEO", "Founder", "Co-Founder",
    "COO", "Chief Operating Officer", "Head of Operations", "VP Operations",
    "VP People", "CHRO", "Chief People Officer", "Head of People",
    "Chief of Staff", "COS",
]

# ── Persona → Job Title Mapping ───────────────────────────────────────────────
PERSONA_TITLE_MAP: dict[str, list[str]] = {
    "CEO": ["ceo", "chief executive", "founder", "co-founder"],
    "COO": ["coo", "chief operating", "head of operations", "vp operations", "chief of staff", "cos"],
    "VP_PEOPLE": ["vp people", "chro", "chief people", "head of people", "chief human resources"],
}

# ── Instantly Campaign IDs (set after credentials wired) ─────────────────────
INSTANTLY_CAMPAIGN_IDS: dict[str, str] = {
    "CEO": os.getenv("INSTANTLY_CAMPAIGN_CEO", ""),
    "COO": os.getenv("INSTANTLY_CAMPAIGN_COO", ""),
    "VP_PEOPLE": os.getenv("INSTANTLY_CAMPAIGN_VP_PEOPLE", ""),
}

# ── Scheduling ────────────────────────────────────────────────────────────────
SOURCING_CRON_HOUR = 7           # run sourcing job at 7 AM daily
CRUNCHBASE_POLL_INTERVAL_MIN = 60  # poll Crunchbase every 60 minutes
RESCORE_CRON_DAY = "1st mon"     # re-score Tier 3 monthly

# ── API Keys ──────────────────────────────────────────────────────────────────
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
CRUNCHBASE_API_KEY = os.getenv("CRUNCHBASE_API_KEY", "")
PHANTOMBUSTER_API_KEY = os.getenv("PHANTOMBUSTER_API_KEY", "")
CLAY_API_KEY = os.getenv("CLAY_API_KEY", "")
BUILTWITH_API_KEY = os.getenv("BUILTWITH_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "")
EXPANDI_API_KEY = os.getenv("EXPANDI_API_KEY", "")
HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
HUBSPOT_PIPELINE_ID = os.getenv("HUBSPOT_PIPELINE_ID", "")
HUBSPOT_DEAL_STAGE_NEW = os.getenv("HUBSPOT_DEAL_STAGE_NEW", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL_HOT_LEADS = os.getenv("SLACK_CHANNEL_HOT_LEADS", "#hot-leads")
SLACK_CHANNEL_ALERTS = os.getenv("SLACK_CHANNEL_ALERTS", "#sdr-alerts")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8000"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
CALENDLY_LINK = os.getenv("CALENDLY_LINK", "")


class _Settings:
    """Single settings object imported across the codebase."""
    apollo_api_key = APOLLO_API_KEY
    crunchbase_api_key = CRUNCHBASE_API_KEY
    phantombuster_api_key = PHANTOMBUSTER_API_KEY
    clay_api_key = CLAY_API_KEY
    builtwith_api_key = BUILTWITH_API_KEY
    openai_api_key = OPENAI_API_KEY
    openai_model = OPENAI_MODEL
    instantly_api_key = INSTANTLY_API_KEY
    instantly_campaign_ids = INSTANTLY_CAMPAIGN_IDS
    expandi_api_key = EXPANDI_API_KEY
    hubspot_access_token = HUBSPOT_ACCESS_TOKEN
    hubspot_pipeline_id = HUBSPOT_PIPELINE_ID
    hubspot_deal_stage_new = HUBSPOT_DEAL_STAGE_NEW
    slack_webhook_url = SLACK_WEBHOOK_URL
    slack_channel_hot_leads = SLACK_CHANNEL_HOT_LEADS
    slack_channel_alerts = SLACK_CHANNEL_ALERTS
    webhook_host = WEBHOOK_HOST
    webhook_port = WEBHOOK_PORT
    webhook_secret = WEBHOOK_SECRET
    calendly_link = CALENDLY_LINK


settings = _Settings()
