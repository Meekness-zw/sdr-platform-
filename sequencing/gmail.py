"""
Sequencing — Gmail SMTP sender.

Handles Day 1 outreach and all follow-up sequence touches.
Injects open-tracking pixel into every email.

Setup (one-time):
  1. myaccount.google.com/security → enable 2-Step Verification
  2. Search "App passwords" → create one named "SDR Pipeline"
  3. Add to .env:
       GMAIL_ADDRESS=you@gmail.com
       GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
       SENDER_NAME=Your Name
       BASE_URL=http://localhost:8000   (or your public URL)
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog
from dotenv import load_dotenv

load_dotenv()
log = structlog.get_logger(__name__)

GMAIL_ADDRESS    = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
SENDER_NAME      = os.getenv("SENDER_NAME", "Your Name")
BASE_URL         = os.getenv("BASE_URL", "http://localhost:8000")
CALENDLY_LINK    = os.getenv("CALENDLY_LINK", "[Calendly link]")

# ── Day 1 templates (from spec 2.5) ──────────────────────────────────────────

DAY1_TEMPLATES: dict[str, dict] = {
    "CEO": {
        "subject": "The AI evaluation problem",
        "body": """{opener}

Your competitors are buying AI tools. So are you, probably. Most of it isn't working.

Not because the tools are bad — some are excellent. It's because no one has the time or context to figure out which 3 of the 47 options actually fit your specific business and will get adopted by your team.

We're a workforce advisory firm that does exactly one thing: audit how your org operates, identify the highest-ROI AI and automation plays for your situation, and prescribe the exact stack to get there. No vendor relationships. No broad transformation pitch. Surgical.

Our team has operated inside Slack, Brex, and growth-stage SaaS companies across fintech and health tech. We know what adoption looks like from the inside.

Worth 20 minutes?

{sender}""",
    },
    "COO": {
        "subject": "Your AI tool overlap is probably costing you",
        "body": """{opener}

I'll be direct. Most ops leaders I talk to have inherited (or purchased) a stack with 20–30% functional overlap, tools bought for use cases that changed, and point solutions a single better platform would replace.

We do AI and automation audits for growth-stage companies — reviewing how the org operates, what's in the stack, and what the actual ROI picture looks like. Then we prescribe. No vendor agenda. Specific, defensible recommendations.

I came from ops-adjacent roles at Brex and Slack. I know what it looks like when a 200-person company is running on the wrong infrastructure.

Do you have 20 minutes in the next couple of weeks?

{sender}""",
    },
    "VP_PEOPLE": {
        "subject": "The workforce AI question your board will ask",
        "body": """{opener}

At some point in the next 6–12 months — if it hasn't happened already — your board or CEO will ask: what is our plan for AI and the workforce?

Most People leaders are caught between two uncomfortable positions: advocating for AI adoption that could reduce headcount (hard to champion internally) or watching from the sidelines while the conversation happens without them.

We help HR and People leaders get ahead of that conversation. We do an operational audit, identify where AI and automation create capacity your org can absorb without disruption, and deliver a roadmap you can present with confidence.

Our team has worked inside Slack and Brex during high-growth and pre-acquisition phases. We know how workforce decisions get made under pressure.

Would it be worth 20 minutes?

{sender}""",
    },
}


# ── Send Day 1 outreach ───────────────────────────────────────────────────────

def send_outreach_email(prospect, dry_run: bool = False) -> bool:
    """Send Day 1 email to a prospect."""
    if not prospect.email:
        log.warning("email_skipped_no_address", name=prospect.full_name())
        return False

    persona = prospect.persona.value if prospect.persona else "CEO"
    tpl = DAY1_TEMPLATES.get(persona, DAY1_TEMPLATES["CEO"])
    opener = prospect.personal_opener or ""
    body = tpl["body"].format(opener=opener, sender=SENDER_NAME).strip()
    subject = tpl["subject"]

    if dry_run:
        _print_preview(prospect.email, prospect.full_name(), subject, persona, body)
        return True

    return _send(prospect.email, subject, body, prospect_id=getattr(prospect, "hubspot_contact_id", None))


# ── Send sequence touch ───────────────────────────────────────────────────────

def send_sequence_touch(touch: dict, dry_run: bool = False) -> bool:
    """Send a scheduled sequence touch email."""
    email = touch.get("email")
    if not email:
        return False

    first_name = touch.get("first_name", "")
    opener = touch.get("personal_opener") or ""
    body = (touch.get("body") or "").replace("[OPENER]", opener).strip()
    subject = touch.get("subject", "Following up")
    prospect_id = touch.get("prospect_id")

    if dry_run:
        _print_preview(email, f"{first_name} {touch.get('last_name','')}", subject, touch.get("persona",""), body)
        return True

    return _send(email, subject, body, prospect_id=prospect_id, touch_id=touch.get("id"))


# ── Core send ─────────────────────────────────────────────────────────────────

def _send(
    to_email: str,
    subject: str,
    body: str,
    prospect_id=None,
    touch_id=None,
) -> bool:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env to send emails."
        )

    # Inject open tracking pixel
    pixel = ""
    if prospect_id:
        pid = prospect_id
        tid = touch_id or ""
        pixel = f'\n\n<img src="{BASE_URL}/track/open?pid={pid}&tid={tid}" width="1" height="1" style="display:none" />'

    html_body = body.replace("\n", "<br>") + pixel

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{SENDER_NAME} <{GMAIL_ADDRESS}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())
        log.info("email_sent", to=to_email, subject=subject)

        # Log email_sent event
        if prospect_id:
            from crm.database import get_conn
            from datetime import datetime
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO email_events (prospect_id, touch_id, event_type, logged_at) VALUES (?,?,?,?)",
                    (prospect_id, touch_id, "sent", datetime.utcnow().isoformat())
                )
        return True
    except Exception as exc:
        log.error("email_send_failed", to=to_email, error=str(exc))
        return False


def _print_preview(email: str, name: str, subject: str, persona: str, body: str) -> None:
    print("\n" + "─" * 64)
    print(f"TO:      {email}  ({name})")
    print(f"SUBJECT: {subject}")
    print(f"PERSONA: {persona}")
    print("─" * 64)
    print(body[:800] + ("..." if len(body) > 800 else ""))
    print("─" * 64 + "\n")
