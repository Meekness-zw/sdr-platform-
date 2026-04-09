"""
Local SQLite database — replaces HubSpot for MVP testing.

Stores all prospect activity in sdr.db in the project root.
Same fields that would go to HubSpot are stored here instead.

Schema is created automatically on first run.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "sdr.db"


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prospects (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name            TEXT,
                last_name             TEXT,
                email                 TEXT,
                linkedin_url          TEXT,
                job_title             TEXT,
                persona               TEXT,
                company_name          TEXT,
                company_domain        TEXT,
                industry              TEXT,
                headcount             INTEGER,
                funding_stage         TEXT,
                tech_stack            TEXT,
                recent_news_summary   TEXT,
                triggers              TEXT,
                firmographic_score    INTEGER DEFAULT 0,
                intent_score          INTEGER DEFAULT 0,
                composite_score       INTEGER DEFAULT 0,
                tier                  TEXT,
                personal_opener       TEXT,
                sequence_status       TEXT DEFAULT 'not_enrolled',
                disqualified_reason   TEXT,
                source                TEXT,
                created_at            TEXT,
                updated_at            TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id  INTEGER,
                event        TEXT,
                detail       TEXT,
                logged_at    TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sequence_touches (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id     INTEGER,
                persona         TEXT,
                touch_day       INTEGER,
                touch_type      TEXT,
                subject         TEXT,
                body            TEXT,
                variant         TEXT DEFAULT 'A',
                scheduled_at    TEXT,
                sent_at         TEXT,
                status          TEXT DEFAULT 'pending'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id  INTEGER,
                touch_id     INTEGER,
                event_type   TEXT,
                logged_at    TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meddic_scores (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id         INTEGER UNIQUE,
                metrics_score       INTEGER DEFAULT 0,
                economic_buyer      INTEGER DEFAULT 0,
                decision_criteria   INTEGER DEFAULT 0,
                decision_process    INTEGER DEFAULT 0,
                identify_pain       INTEGER DEFAULT 0,
                champion            INTEGER DEFAULT 0,
                total_score         INTEGER DEFAULT 0,
                notes               TEXT,
                handoff_ready       INTEGER DEFAULT 0,
                scored_at           TEXT,
                updated_at          TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_variants (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                persona      TEXT,
                touch_day    INTEGER,
                variant      TEXT,
                subject      TEXT,
                sent         INTEGER DEFAULT 0,
                opens        INTEGER DEFAULT 0,
                replies      INTEGER DEFAULT 0,
                created_at   TEXT
            )
        """)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_prospect(prospect) -> int:
    """
    Insert or update a prospect. Matches on email if available,
    otherwise on (first_name, last_name, company_name).
    Returns the row id.
    """
    now = datetime.utcnow().isoformat()

    with get_conn() as conn:
        # Check if prospect already exists
        if prospect.email:
            row = conn.execute(
                "SELECT id FROM prospects WHERE email = ?", (prospect.email,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM prospects WHERE first_name=? AND last_name=? AND company_name=?",
                (prospect.first_name, prospect.last_name, prospect.company_name),
            ).fetchone()

        data = (
            prospect.first_name,
            prospect.last_name,
            prospect.email,
            prospect.linkedin_url,
            prospect.job_title,
            prospect.persona.value if prospect.persona else None,
            prospect.company_name,
            prospect.company_domain,
            prospect.industry,
            prospect.headcount,
            prospect.funding_stage.value if prospect.funding_stage else None,
            ", ".join(prospect.tech_stack) if prospect.tech_stack else None,
            prospect.recent_news_summary,
            ", ".join(t.value for t in prospect.triggers) if prospect.triggers else None,
            prospect.firmographic_score,
            prospect.intent_score,
            prospect.composite_score,
            prospect.tier.value if prospect.tier else None,
            prospect.personal_opener,
            prospect.sequence_status.value if prospect.sequence_status else "not_enrolled",
            prospect.disqualified_reason,
            prospect.source,
            now,
        )

        if row:
            conn.execute("""
                UPDATE prospects SET
                    first_name=?, last_name=?, email=?, linkedin_url=?, job_title=?,
                    persona=?, company_name=?, company_domain=?, industry=?, headcount=?,
                    funding_stage=?, tech_stack=?, recent_news_summary=?, triggers=?,
                    firmographic_score=?, intent_score=?, composite_score=?, tier=?,
                    personal_opener=?, sequence_status=?, disqualified_reason=?, source=?,
                    updated_at=?
                WHERE id=?
            """, (*data, row["id"]))
            return row["id"]
        else:
            cursor = conn.execute("""
                INSERT INTO prospects (
                    first_name, last_name, email, linkedin_url, job_title,
                    persona, company_name, company_domain, industry, headcount,
                    funding_stage, tech_stack, recent_news_summary, triggers,
                    firmographic_score, intent_score, composite_score, tier,
                    personal_opener, sequence_status, disqualified_reason, source,
                    updated_at, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (*data, now))
            return cursor.lastrowid


def log_activity(prospect_id: int, event: str, detail: str = "") -> None:
    """Log a pipeline event for a prospect."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_log (prospect_id, event, detail, logged_at) VALUES (?,?,?,?)",
            (prospect_id, event, detail, datetime.utcnow().isoformat()),
        )


def get_all_prospects(tier: str | None = None) -> list[sqlite3.Row]:
    """Fetch all prospects, optionally filtered by tier."""
    with get_conn() as conn:
        if tier:
            return conn.execute(
                "SELECT * FROM prospects WHERE tier=? ORDER BY composite_score DESC",
                (tier,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM prospects ORDER BY composite_score DESC"
        ).fetchall()


def print_prospects_table() -> None:
    """Print a summary table of all stored prospects."""
    rows = get_all_prospects()
    if not rows:
        print("No prospects in database yet.")
        return

    print(f"\n── SDR Prospect Database ({len(rows)} records) ───────────────────────────────")
    print(f"{'Name':<22} {'Company':<20} {'Score':>5} {'Tier':<22} {'Status'}")
    print("─" * 90)
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}"
        print(
            f"{name:<22} {r['company_name']:<20} {r['composite_score']:>5} "
            f"{r['tier'] or 'none':<22} {r['sequence_status']}"
        )
    print("─" * 90 + "\n")
