from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Persona(str, Enum):
    CEO = "CEO"
    COO = "COO"
    VP_PEOPLE = "VP_PEOPLE"
    UNKNOWN = "UNKNOWN"


class FundingStage(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    PE_BACKED = "pe_backed"
    BOOTSTRAPPED = "bootstrapped"
    UNKNOWN = "unknown"


class Tier(str, Enum):
    HOT = "tier_1_hot"
    WARM = "tier_2_warm"
    COOL = "tier_3_cool"
    DISQUALIFIED = "disqualified"


class TriggerEvent(str, Enum):
    FUNDING_ROUND = "funding_round"           # 25 pts — Crunchbase, last 30 days
    NEW_EXEC_HIRE = "new_exec_hire"           # 22 pts — LinkedIn, last 60 days
    AI_JOB_POSTING = "ai_job_posting"        # 18 pts — LinkedIn Jobs, active
    AI_STRATEGY_STATEMENT = "ai_strategy"    # 15 pts — Google Alerts / Clay
    LAYOFF_OR_RESTRUCTURE = "layoff"         # 15 pts — news monitoring
    EXEC_AI_POST = "exec_ai_post"            # 12 pts — LinkedIn Sales Nav / manual
    MA_ACQUISITION = "ma_acquisition"        # 10 pts — Crunchbase / news


class SequenceStatus(str, Enum):
    NOT_ENROLLED = "not_enrolled"
    ENROLLED = "enrolled"
    REPLIED = "replied"
    POSITIVE_REPLY = "positive_reply"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"


class Prospect(BaseModel):
    # ── Identity ──────────────────────────────────────────────────────────────
    id: Optional[str] = None
    first_name: str
    last_name: str
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    job_title: Optional[str] = None
    persona: Persona = Persona.UNKNOWN

    # ── Company ───────────────────────────────────────────────────────────────
    company_name: str
    company_domain: Optional[str] = None
    industry: Optional[str] = None
    headcount: Optional[int] = None
    funding_stage: FundingStage = FundingStage.UNKNOWN
    funding_amount_usd: Optional[float] = None
    arr_signal_usd: Optional[float] = None      # bootstrapped ARR signal

    # ── Enrichment ────────────────────────────────────────────────────────────
    tech_stack: list[str] = Field(default_factory=list)
    recent_news_summary: Optional[str] = None
    recent_linkedin_post: Optional[str] = None

    # ── Trigger Events ────────────────────────────────────────────────────────
    triggers: list[TriggerEvent] = Field(default_factory=list)
    funding_announced_at: Optional[datetime] = None
    exec_hire_announced_at: Optional[datetime] = None

    # ── Scoring ───────────────────────────────────────────────────────────────
    firmographic_score: int = 0
    intent_score: int = 0
    composite_score: int = 0
    tier: Optional[Tier] = None

    # ── Personalization ───────────────────────────────────────────────────────
    personal_opener: Optional[str] = None       # GPT-4o generated

    # ── Sequence & CRM ────────────────────────────────────────────────────────
    sequence_status: SequenceStatus = SequenceStatus.NOT_ENROLLED
    instantly_contact_id: Optional[str] = None
    hubspot_contact_id: Optional[str] = None
    hubspot_deal_id: Optional[str] = None
    disqualified_reason: Optional[str] = None

    # ── Source ────────────────────────────────────────────────────────────────
    source: Optional[str] = None                # "apollo", "crunchbase", "linkedin"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def is_qualified(self) -> bool:
        return self.tier in (Tier.HOT, Tier.WARM)
