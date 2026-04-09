"""
Alerts — Layer 5: Slack webhook notifications.

Fires real-time Slack alerts for:
  - Tier 1 (HOT) prospect enrolled → #hot-leads
  - Positive reply detected → #hot-leads with reply text + Calendly link
  - Pipeline errors → #sdr-alerts

Wire SLACK_WEBHOOK_URL in .env to activate.
"""

from __future__ import annotations

import httpx
import structlog

from config.settings import settings
from models.prospect import Prospect

log = structlog.get_logger(__name__)


def alert_hot_lead(prospect: Prospect) -> None:
    """
    Fire a Slack alert when a Tier 1 HOT prospect is enrolled.
    Sent to SLACK_CHANNEL_HOT_LEADS.
    """
    message = _build_hot_lead_message(prospect)
    _post(message, channel=settings.slack_channel_hot_leads)


def alert_positive_reply(prospect: Prospect, reply_text: str) -> None:
    """
    Fire a Slack alert when a positive reply is detected.
    Includes contact details, reply excerpt, and Calendly link.
    """
    message = _build_reply_message(prospect, reply_text)
    _post(message, channel=settings.slack_channel_hot_leads)


def alert_error(error_message: str, context: str = "") -> None:
    """Fire a Slack alert for pipeline errors. Sent to SLACK_CHANNEL_ALERTS."""
    message = {
        "text": f":red_circle: *SDR Pipeline Error*\n{context}\n```{error_message}```"
    }
    _post(message, channel=settings.slack_channel_alerts)


def _build_hot_lead_message(prospect: Prospect) -> dict:
    return {
        "text": f":fire: *HOT Lead Enrolled* — Score {prospect.composite_score}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":fire: *HOT Lead Enrolled*\n"
                        f"*Name:* {prospect.full_name()}\n"
                        f"*Title:* {prospect.job_title or 'N/A'}\n"
                        f"*Company:* {prospect.company_name}\n"
                        f"*Score:* {prospect.composite_score} "
                        f"(Firmographic: {prospect.firmographic_score} | "
                        f"Intent: {prospect.intent_score})\n"
                        f"*Triggers:* {', '.join(t.value for t in prospect.triggers) or 'None'}\n"
                        f"*Persona:* {prospect.persona.value}\n"
                        f"*LinkedIn:* {prospect.linkedin_url or 'N/A'}"
                    ),
                },
            }
        ],
    }


def _build_reply_message(prospect: Prospect, reply_text: str) -> dict:
    excerpt = reply_text[:300] + ("..." if len(reply_text) > 300 else "")
    return {
        "text": f":mega: *Positive Reply* from {prospect.full_name()} at {prospect.company_name}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":mega: *Positive Reply Detected*\n"
                        f"*From:* {prospect.full_name()} ({prospect.email})\n"
                        f"*Company:* {prospect.company_name}\n"
                        f"*Title:* {prospect.job_title or 'N/A'}\n"
                        f"*Reply:*\n>{excerpt}\n"
                        f"*Book a call:* {settings.calendly_link or '[Set CALENDLY_LINK in .env]'}"
                    ),
                },
            }
        ],
    }


def _post(message: dict, channel: str) -> None:
    """Post a message to Slack via incoming webhook."""
    if not settings.slack_webhook_url:
        log.warning("slack_webhook_not_configured")
        return

    try:
        response = httpx.post(
            settings.slack_webhook_url,
            json={**message, "channel": channel},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:
        log.error("slack_post_failed", error=str(exc))
