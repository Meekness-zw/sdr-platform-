"""
Multi-touch sequence scheduler.

Builds all scheduled touches for a prospect based on their persona,
then sends due touches daily via Gmail.

Touch schedule per persona:
  CEO/Founder  : Email D1, LinkedIn D3, Email D5, LinkedIn DM D8, Email D14
  COO/Ops      : Email D1, LinkedIn D3, Email D5, LinkedIn DM D8, Email D12, Email D18
  VP People    : Email D1, LinkedIn D3, Email D5, LinkedIn DM D8, Email D14

Touch types: email | linkedin_connection | linkedin_dm
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import structlog

from crm.database import get_conn, log_activity, init_db
from models.prospect import Persona

log = structlog.get_logger(__name__)

SENDER_NAME = os.getenv("SENDER_NAME", "Your Name")
CALENDLY_LINK = os.getenv("CALENDLY_LINK", "[Calendly link]")

# ── Sequence templates ────────────────────────────────────────────────────────

SEQUENCES: dict[str, list[dict]] = {
    "CEO": [
        {"day": 1,  "type": "email",               "subject": "The AI evaluation problem",       "variant": "A"},
        {"day": 3,  "type": "linkedin_connection",  "subject": "Connection request",              "variant": "A"},
        {"day": 5,  "type": "email",               "subject": "Re: The AI evaluation problem",   "variant": "A"},
        {"day": 8,  "type": "linkedin_dm",          "subject": "LinkedIn DM",                     "variant": "A"},
        {"day": 14, "type": "email",               "subject": "Last note from me",               "variant": "A"},
    ],
    "COO": [
        {"day": 1,  "type": "email",               "subject": "Your AI tool overlap is probably costing you", "variant": "A"},
        {"day": 3,  "type": "linkedin_connection",  "subject": "Connection request",              "variant": "A"},
        {"day": 5,  "type": "email",               "subject": "The build vs. buy trap",          "variant": "A"},
        {"day": 8,  "type": "linkedin_dm",          "subject": "LinkedIn DM",                     "variant": "A"},
        {"day": 12, "type": "email",               "subject": "What we find in your industry",   "variant": "A"},
        {"day": 18, "type": "email",               "subject": "Closing the loop",                "variant": "A"},
    ],
    "VP_PEOPLE": [
        {"day": 1,  "type": "email",               "subject": "The workforce AI question your board will ask", "variant": "A"},
        {"day": 3,  "type": "linkedin_connection",  "subject": "Connection request",              "variant": "A"},
        {"day": 5,  "type": "email",               "subject": "What the proactive People leaders are doing", "variant": "A"},
        {"day": 8,  "type": "linkedin_dm",          "subject": "LinkedIn DM",                     "variant": "A"},
        {"day": 14, "type": "email",               "subject": "One last thought",                "variant": "A"},
    ],
}

EMAIL_BODIES: dict[str, dict[int, str]] = {
    "CEO": {
        5: """[OPENER]

A question worth sitting with: if you added up every AI and automation tool subscription in your business right now and measured actual ROI against what was promised — what would that number look like?

Most companies we talk to have 8–12 tools that collectively cost $80K–$200K annually. Fewer than half are delivering measurable returns.

We fix that. One audit, a clear prescription, a retainer to keep vendors accountable.

Happy to share what we typically find in companies at your stage.

{sender}""",
        14: """[OPENER]

I'll keep this short. We help [industry] companies at your stage figure out exactly which AI and automation plays will move the needle — not which ones look good in a demo.

If the timing is wrong, no problem. If you want to talk:
{calendly}

{sender}""",
    },
    "COO": {
        5: """[OPENER]

Following up. A pattern we see constantly: a company spends 3–6 months evaluating tools, buys something, spends another 3 months on implementation, and then the team doesn't use it because nobody owned adoption.

The problem isn't the tool selection. It's that evaluation and adoption are being done by the same team that's already running the operation.

Our audit separates the signal from the noise up front and delivers a recommendation that accounts for your team's actual capacity to absorb change. That's the part most consultants skip.

Happy to share a sample deliverable if it would be useful.

{sender}""",
        12: """[OPENER]

In [SaaS / fintech / health tech] companies at your size, the three areas where we most consistently find high-ROI AI opportunities: customer-facing workflows (support, onboarding), internal ops (finance, HR ops), and the sales/revenue stack.

Most have at least one significant tool overlap or gap in each.

If any of that maps to where you're feeling pressure, it's worth a conversation.
{calendly}

{sender}""",
        18: """[OPENER]

Last note. I know ops leaders are the most time-constrained people in any company — I won't keep filling your inbox.

If we're ever worth 20 minutes: {calendly}

{sender}""",
    },
    "VP_PEOPLE": {
        5: """[OPENER]

The CHROs and VP People I see navigating the AI conversation well have one thing in common: they run the audit before anyone asks them to.

They come to the board with a workforce AI readiness assessment, not a reaction. They've identified where automation creates capacity (and where it doesn't), and they've built a redeployment plan around it.

That's the deliverable we produce. A structured audit that gives you the language and the data to lead the conversation instead of being managed by it.

Happy to share more detail on what that looks like.

{sender}""",
        14: """[OPENER]

I'll wrap up with one question: does [Company] currently have a documented answer to what happens to your workforce as you automate more of your operations?

If not, that document is worth building now — before you need it.

If we can help you build it: {calendly}

{sender}""",
    },
}

LINKEDIN_COPY: dict[str, dict[str, str]] = {
    "CEO": {
        "connection": "{first_name} — I sent you a note earlier this week about AI stack advisory. We work with founders in {industry} on cutting through the noise. Would love to connect.",
        "dm": "{first_name} — saw you're building {company_note}. We're working with a few founders in {industry} on getting real ROI from their AI stack. The problem is almost never the tools — it's the fit and adoption plan. Happy to share what we're seeing if useful.",
    },
    "COO": {
        "connection": "{first_name} — ops leader in {industry}, curious about your experience evaluating AI tools at {company}. Would love to connect and share what we're seeing.",
        "dm": "{first_name} — noticed {company} recently {trigger_note}. That's usually the moment when ops leaders are most in the weeds on tool and process evaluation. We've helped a few companies at that stage move faster with a structured audit. Happy to share if relevant.",
    },
    "VP_PEOPLE": {
        "connection": "{first_name} — People leader at {company}. I work with HR and Ops leaders on AI workforce strategy. Would love to connect — sharing some thinking on how CHROs are approaching the board conversation on AI.",
        "dm": "{first_name} — curious whether the AI workforce planning conversation has hit {company} yet. We're seeing it surface at board level for most Series B+ companies right now. Happy to share what we're hearing if it would be useful context.",
    },
}


# ── Enroll prospect in sequence ───────────────────────────────────────────────

def enroll_prospect_sequence(prospect_id: int, persona: str, enrolled_at: Optional[datetime] = None) -> int:
    """
    Create all scheduled touches for a prospect.
    Returns number of touches created.
    """
    if persona not in SEQUENCES:
        log.warning("unknown_persona_for_sequence", persona=persona)
        return 0

    base = enrolled_at or datetime.utcnow()
    touches = SEQUENCES[persona]
    created = 0

    with get_conn() as conn:
        # Check if already enrolled
        existing = conn.execute(
            "SELECT COUNT(*) FROM sequence_touches WHERE prospect_id = ?",
            (prospect_id,)
        ).fetchone()[0]
        if existing > 0:
            log.info("prospect_already_enrolled", prospect_id=prospect_id)
            return 0

        for touch in touches:
            scheduled = base + timedelta(days=touch["day"] - 1)
            body = _get_body(persona, touch["day"], touch["type"])
            conn.execute("""
                INSERT INTO sequence_touches
                  (prospect_id, persona, touch_day, touch_type, subject, body, variant, scheduled_at, status)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                prospect_id, persona, touch["day"], touch["type"],
                touch["subject"], body, touch["variant"],
                scheduled.isoformat(), "pending"
            ))
            created += 1

    log_activity(prospect_id, "sequence_enrolled", f"persona={persona} touches={created}")
    log.info("sequence_enrolled", prospect_id=prospect_id, persona=persona, touches=created)
    return created


def _get_body(persona: str, day: int, touch_type: str) -> str:
    if touch_type == "email":
        body = EMAIL_BODIES.get(persona, {}).get(day, "")
        return body.format(sender=SENDER_NAME, calendly=CALENDLY_LINK)
    if touch_type == "linkedin_connection":
        return LINKEDIN_COPY.get(persona, {}).get("connection", "")
    if touch_type == "linkedin_dm":
        return LINKEDIN_COPY.get(persona, {}).get("dm", "")
    return ""


# ── Send due touches ──────────────────────────────────────────────────────────

def send_due_touches(dry_run: bool = False) -> dict:
    """
    Find all pending touches scheduled for today or earlier and send them.
    Returns summary dict with counts.
    """
    from sequencing.gmail import send_sequence_touch

    init_db()
    now = datetime.utcnow().isoformat()
    results = {"emails_sent": 0, "linkedin_shown": 0, "errors": 0, "skipped": 0}

    with get_conn() as conn:
        due = conn.execute("""
            SELECT t.*, p.first_name, p.last_name, p.email, p.company_name,
                   p.industry, p.personal_opener, p.linkedin_url
            FROM sequence_touches t
            JOIN prospects p ON t.prospect_id = p.id
            WHERE t.status = 'pending' AND t.scheduled_at <= ?
            ORDER BY t.scheduled_at ASC
        """, (now,)).fetchall()

    log.info("due_touches_found", count=len(due))

    for touch in due:
        touch = dict(touch)
        try:
            if touch["touch_type"] == "email":
                success = send_sequence_touch(touch, dry_run=dry_run)
                if success:
                    _mark_sent(touch["id"], touch["prospect_id"], "email_sent")
                    results["emails_sent"] += 1
                else:
                    results["skipped"] += 1

            elif touch["touch_type"] in ("linkedin_connection", "linkedin_dm"):
                # LinkedIn touches shown in UI for manual send — log for visibility
                _mark_sent(touch["id"], touch["prospect_id"], "linkedin_copy_ready")
                results["linkedin_shown"] += 1

        except Exception as exc:
            log.error("touch_send_failed", touch_id=touch["id"], error=str(exc))
            results["errors"] += 1

    return results


def _mark_sent(touch_id: int, prospect_id: int, event: str) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE sequence_touches SET status='sent', sent_at=? WHERE id=?",
            (now, touch_id)
        )
    log_activity(prospect_id, event, f"touch_id={touch_id}")


def get_linkedin_touches_due() -> list[dict]:
    """Return all LinkedIn touches that are ready for manual send."""
    init_db()
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT t.*, p.first_name, p.last_name, p.company_name, p.industry,
                   p.linkedin_url, p.personal_opener
            FROM sequence_touches t
            JOIN prospects p ON t.prospect_id = p.id
            WHERE t.touch_type IN ('linkedin_connection','linkedin_dm')
              AND t.status = 'pending'
              AND t.scheduled_at <= ?
            ORDER BY t.scheduled_at ASC
        """, (now,)).fetchall()
    return [dict(r) for r in rows]
