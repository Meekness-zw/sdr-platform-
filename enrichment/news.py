"""
Enrichment: Recent news summary via GPT-4o + Google News RSS.

Searches Google News for company mentions in the last 30 days,
then uses GPT-4o to produce a 2–3 sentence summary.
The summary is stored in prospect.recent_news_summary and used
as input to the personalization engine.

Wire OPENAI_API_KEY in .env to activate.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from models.prospect import Prospect

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def enrich_news_summary(prospect: Prospect) -> Prospect:
    """
    Fetch recent news for the prospect's company and summarize with GPT-4o.
    Populates prospect.recent_news_summary if news is found.
    """
    if not prospect.company_name:
        return prospect

    # TODO: Wire credentials and implement
    # 1. Fetch Google News RSS for company name (last 30 days)
    # 2. Extract top 3–5 headlines + snippets
    # 3. Call GPT-4o to summarize into 2–3 sentences relevant to sales context
    raise NotImplementedError("Wire OPENAI_API_KEY and implement news enrichment")


def _fetch_google_news(company_name: str) -> list[dict]:
    """Return list of {title, snippet, published_at} from Google News RSS."""
    # TODO: Parse RSS XML with httpx + xml.etree.ElementTree
    raise NotImplementedError


def _summarize_news(company_name: str, headlines: list[dict]) -> str:
    """Use GPT-4o to summarize news headlines into a sales-relevant summary."""
    from openai import OpenAI
    # TODO: Build prompt and call OpenAI API
    raise NotImplementedError
