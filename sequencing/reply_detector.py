"""
Reply detector — polls Gmail IMAP for replies from prospects.

Runs on a scheduled interval (every 15 minutes by default).
For each unread reply found:
  1. Matches sender email to a prospect in the database
  2. Classifies sentiment with GPT-4o (positive/negative/neutral)
  3. If positive: fires Slack alert, creates deal record, marks prospect
  4. Logs all replies to activity_log

Requires same Gmail credentials as the sender:
  GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env
"""

from __future__ import annotations

import email
import imaplib
import os
from datetime import datetime

import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger(__name__)

GMAIL_ADDRESS     = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
IMAP_HOST         = "imap.gmail.com"
IMAP_PORT         = 993


def check_for_replies() -> dict:
    """
    Poll Gmail inbox for unread replies from prospects.
    Returns summary: {checked, positive, negative, neutral, errors}
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        log.warning("reply_detector_not_configured")
        return {"checked": 0, "positive": 0, "negative": 0, "neutral": 0, "errors": 0}

    results = {"checked": 0, "positive": 0, "negative": 0, "neutral": 0, "errors": 0}

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        # Search unread emails
        _, msg_ids = mail.search(None, "UNSEEN")
        ids = msg_ids[0].split()

        log.info("imap_unread_found", count=len(ids))

        for msg_id in ids:
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                sender_email = _extract_email(msg.get("From", ""))
                subject      = msg.get("Subject", "")
                body         = _extract_body(msg)

                if not sender_email or not body:
                    continue

                prospect = _find_prospect_by_email(sender_email)
                if not prospect:
                    # Not one of our prospects — leave unread / skip
                    mail.store(msg_id, "-FLAGS", "\\Seen")
                    continue

                results["checked"] += 1
                sentiment = _classify_sentiment(body)
                results[sentiment] += 1

                _handle_reply(prospect, body, sentiment, subject)
                log.info("reply_processed", sender=sender_email, sentiment=sentiment)

            except Exception as exc:
                log.error("reply_parse_failed", error=str(exc))
                results["errors"] += 1

        mail.logout()

    except Exception as exc:
        log.error("imap_connection_failed", error=str(exc))
        results["errors"] += 1

    return results


def _extract_email(from_header: str) -> str:
    """Extract plain email address from 'Name <email>' format."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].strip().lower()
    return from_header.strip().lower()


def _extract_body(msg) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except Exception:
            pass
    return ""


def _find_prospect_by_email(email_addr: str) -> dict | None:
    from crm.database import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM prospects WHERE LOWER(email) = ?", (email_addr,)
        ).fetchone()
    return dict(row) if row else None


def _classify_sentiment(reply_text: str) -> str:
    """Classify reply as positive/negative/neutral using GPT-4o."""
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        return "neutral"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": (
                    "Classify this cold email reply as exactly one word: "
                    "positive (interested, wants to meet, asking questions), "
                    "negative (not interested, unsubscribe, stop contacting), "
                    "neutral (out of office, unclear, one word). "
                    "Reply with ONLY the single word."
                )},
                {"role": "user", "content": reply_text[:1000]},
            ],
            temperature=0, max_tokens=5,
        )
        result = resp.choices[0].message.content.strip().lower()
        return result if result in ("positive", "negative", "neutral") else "neutral"
    except Exception as exc:
        log.warning("sentiment_classification_failed", error=str(exc))
        return "neutral"


def _handle_reply(prospect: dict, body: str, sentiment: str, subject: str) -> None:
    from crm.database import get_conn, log_activity
    from datetime import datetime

    pid = prospect["id"]
    now = datetime.utcnow().isoformat()

    new_status = {
        "positive": "positive_reply",
        "negative": "replied",
        "neutral":  "replied",
    }.get(sentiment, "replied")

    with get_conn() as conn:
        conn.execute(
            "UPDATE prospects SET sequence_status=?, updated_at=? WHERE id=?",
            (new_status, now, pid)
        )
        conn.execute(
            "INSERT INTO email_events (prospect_id, touch_id, event_type, logged_at) VALUES (?,?,?,?)",
            (pid, None, f"reply_{sentiment}", now)
        )

    log_activity(pid, f"reply_{sentiment}", subject[:100])

    if sentiment == "positive":
        _handle_positive_reply(prospect, body)


def _handle_positive_reply(prospect: dict, body: str) -> None:
    """Fire Slack alert and create deal record for positive reply."""
    from crm.database import get_conn, log_activity
    from datetime import datetime

    pid = prospect["id"]

    # Slack alert
    try:
        from alerts.slack import alert_positive_reply
        from models.prospect import Prospect, Persona, FundingStage, SequenceStatus
        p = Prospect(
            first_name=prospect.get("first_name") or "",
            last_name=prospect.get("last_name") or "",
            email=prospect.get("email"),
            job_title=prospect.get("job_title"),
            company_name=prospect.get("company_name") or "",
            hubspot_contact_id=str(pid),
        )
        alert_positive_reply(p, body)
    except Exception as exc:
        log.warning("slack_alert_failed", error=str(exc))

    # Log deal created
    log_activity(pid, "deal_created", "positive reply detected via Gmail IMAP")
    log.info("positive_reply_handled", prospect_id=pid)
