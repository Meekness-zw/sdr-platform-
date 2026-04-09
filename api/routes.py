"""
REST API routes for the SDR dashboard UI.
All endpoints return JSON consumed by the frontend.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse

from crm.database import get_all_prospects, get_conn, init_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api")


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats():
    """Dashboard summary stats."""
    init_db()
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
        hot = conn.execute("SELECT COUNT(*) FROM prospects WHERE tier='tier_1_hot'").fetchone()[0]
        warm = conn.execute("SELECT COUNT(*) FROM prospects WHERE tier='tier_2_warm'").fetchone()[0]
        cool = conn.execute("SELECT COUNT(*) FROM prospects WHERE tier='tier_3_cool'").fetchone()[0]
        disq = conn.execute("SELECT COUNT(*) FROM prospects WHERE tier='disqualified'").fetchone()[0]
        enrolled = conn.execute(
            "SELECT COUNT(*) FROM prospects WHERE sequence_status='enrolled'"
        ).fetchone()[0]
        positive = conn.execute(
            "SELECT COUNT(*) FROM prospects WHERE sequence_status='positive_reply'"
        ).fetchone()[0]
        avg_score = conn.execute(
            "SELECT ROUND(AVG(composite_score),1) FROM prospects WHERE composite_score > 0"
        ).fetchone()[0] or 0

    return {
        "total": total,
        "hot": hot,
        "warm": warm,
        "cool": cool,
        "disqualified": disq,
        "enrolled": enrolled,
        "positive_replies": positive,
        "avg_score": avg_score,
    }


# ── Prospects ─────────────────────────────────────────────────────────────────

@router.get("/prospects")
def get_prospects(tier: Optional[str] = None, search: Optional[str] = None):
    """Return all prospects, optionally filtered by tier or search query."""
    init_db()
    with get_conn() as conn:
        query = "SELECT * FROM prospects"
        params = []
        conditions = []

        if tier and tier != "all":
            conditions.append("tier = ?")
            params.append(tier)

        if search:
            conditions.append(
                "(first_name LIKE ? OR last_name LIKE ? OR company_name LIKE ? OR job_title LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY composite_score DESC"
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


@router.get("/prospects/{prospect_id}")
def get_prospect(prospect_id: int):
    """Return a single prospect by ID."""
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return dict(row)


@router.get("/prospects/{prospect_id}/activity")
def get_prospect_activity(prospect_id: int):
    """Return activity log for a prospect."""
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log WHERE prospect_id = ? ORDER BY logged_at DESC",
            (prospect_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Activity Log ──────────────────────────────────────────────────────────────

@router.get("/activity")
def get_activity(limit: int = 50):
    """Return recent pipeline activity across all prospects."""
    init_db()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT a.*, p.first_name, p.last_name, p.company_name
            FROM activity_log a
            LEFT JOIN prospects p ON a.prospect_id = p.id
            ORDER BY a.logged_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ── CSV Upload & Pipeline Trigger ─────────────────────────────────────────────

_pipeline_status = {"running": False, "message": "", "processed": 0, "total": 0}


@router.get("/pipeline/status")
def pipeline_status():
    return _pipeline_status


@router.post("/pipeline/upload-csv")
async def upload_csv(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload an Apollo CSV and run the full pipeline in the background.
    Poll /api/pipeline/status to track progress.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    if _pipeline_status["running"]:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    # Save uploaded file to a temp location
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    content = await file.read()
    tmp.write(content)
    tmp.flush()
    tmp_path = tmp.name
    tmp.close()

    background_tasks.add_task(_run_pipeline_bg, tmp_path)
    return {"message": f"Pipeline started for {file.filename}", "status": "running"}


def _run_pipeline_bg(csv_path: str) -> None:
    """Background task: run full pipeline on uploaded CSV."""
    global _pipeline_status
    _pipeline_status = {"running": True, "message": "Loading CSV...", "processed": 0, "total": 0}

    try:
        from sourcing.csv_loader import load_from_csv
        from scoring import score_prospect
        from personalization import generate_opener
        from sequencing.gmail import send_outreach_email
        from crm.hubspot import sync_prospect
        from alerts.slack import alert_hot_lead
        from models.prospect import Tier

        init_db()
        prospects = load_from_csv(csv_path)
        total = len(prospects)
        _pipeline_status["total"] = total
        _pipeline_status["message"] = f"Processing {total} prospects..."

        for i, prospect in enumerate(prospects):
            prospect = score_prospect(prospect)

            if prospect.is_qualified():
                try:
                    prospect = generate_opener(prospect)
                except Exception as exc:
                    log.warning("opener_failed", error=str(exc))

            prospect = sync_prospect(prospect)

            # Enroll qualified prospects in multi-touch sequence
            if prospect.is_qualified() and prospect.hubspot_contact_id:
                try:
                    from sequencing.sequence_scheduler import enroll_prospect_sequence
                    persona = prospect.persona.value if prospect.persona else "CEO"
                    enroll_prospect_sequence(int(prospect.hubspot_contact_id), persona)
                except Exception as exc:
                    log.warning("sequence_enrollment_failed", error=str(exc))

            if prospect.tier == Tier.HOT:
                try:
                    alert_hot_lead(prospect)
                except Exception as exc:
                    log.warning("slack_alert_failed", error=str(exc))

            _pipeline_status["processed"] = i + 1
            _pipeline_status["message"] = f"Processed {i + 1}/{total}: {prospect.full_name()}"

        _pipeline_status["running"] = False
        _pipeline_status["message"] = f"Done. {total} prospects processed."

    except Exception as exc:
        _pipeline_status["running"] = False
        _pipeline_status["message"] = f"Error: {str(exc)}"
        log.error("pipeline_bg_failed", error=str(exc))
    finally:
        Path(csv_path).unlink(missing_ok=True)


@router.get("/prospects/{prospect_id}/touches")
def get_prospect_touches(prospect_id: int):
    """Return all sequence touches for a prospect."""
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sequence_touches WHERE prospect_id = ? ORDER BY touch_day ASC",
            (prospect_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/prospects/{prospect_id}/enroll")
def enroll_prospect(prospect_id: int):
    """Enroll a prospect in their persona sequence."""
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT persona FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")

    from sequencing.sequence_scheduler import enroll_prospect_sequence
    persona = row["persona"] or "CEO"
    created = enroll_prospect_sequence(prospect_id, persona)
    return {"enrolled": created, "persona": persona}


@router.get("/prospects/{prospect_id}/meddic")
def get_meddic(prospect_id: int):
    """Return MEDDIC score for a prospect."""
    init_db()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM meddic_scores WHERE prospect_id = ?", (prospect_id,)
        ).fetchone()
    return dict(row) if row else {}


@router.post("/prospects/{prospect_id}/meddic")
async def save_meddic(prospect_id: int, request: Request):
    """Save MEDDIC discovery call scores."""
    init_db()
    data = await request.json()
    fields = ["metrics_score", "economic_buyer", "decision_criteria",
              "decision_process", "identify_pain", "champion", "notes"]
    scores = {f: data.get(f, 0) for f in fields}
    total = sum(int(scores[f]) for f in fields if f != "notes")
    handoff = 1 if total >= 4 else 0
    now = datetime.utcnow().isoformat()

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO meddic_scores
              (prospect_id, metrics_score, economic_buyer, decision_criteria,
               decision_process, identify_pain, champion, total_score, notes,
               handoff_ready, scored_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(prospect_id) DO UPDATE SET
              metrics_score=excluded.metrics_score,
              economic_buyer=excluded.economic_buyer,
              decision_criteria=excluded.decision_criteria,
              decision_process=excluded.decision_process,
              identify_pain=excluded.identify_pain,
              champion=excluded.champion,
              total_score=excluded.total_score,
              notes=excluded.notes,
              handoff_ready=excluded.handoff_ready,
              updated_at=excluded.updated_at
        """, (
            prospect_id,
            scores["metrics_score"], scores["economic_buyer"], scores["decision_criteria"],
            scores["decision_process"], scores["identify_pain"], scores["champion"],
            total, scores["notes"], handoff, now, now,
        ))
        if handoff:
            conn.execute(
                "UPDATE prospects SET sequence_status='qualified_for_handoff', updated_at=? WHERE id=?",
                (now, prospect_id),
            )
            from crm.database import log_activity
            log_activity(prospect_id, "meddic_handoff_ready", f"total_score={total}")

    return {"total_score": total, "handoff_ready": bool(handoff)}


@router.get("/linkedin/due")
def get_linkedin_due():
    """Return LinkedIn touches ready for manual send."""
    init_db()
    from sequencing.sequence_scheduler import get_linkedin_touches_due
    return get_linkedin_touches_due()


@router.post("/linkedin/{touch_id}/mark-sent")
def mark_linkedin_sent(touch_id: int):
    """Mark a LinkedIn touch as manually sent."""
    init_db()
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        row = conn.execute("SELECT prospect_id FROM sequence_touches WHERE id=?", (touch_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Touch not found")
        conn.execute(
            "UPDATE sequence_touches SET status='sent', sent_at=? WHERE id=?",
            (now, touch_id),
        )
    from crm.database import log_activity
    log_activity(row["prospect_id"], "linkedin_sent", f"touch_id={touch_id}")
    return {"status": "sent"}


@router.get("/stats/email")
def get_email_stats():
    """Return email event counts (sent, opened, replies) for KPI dashboard."""
    init_db()
    with get_conn() as conn:
        sent = conn.execute(
            "SELECT COUNT(*) FROM email_events WHERE event_type='sent'"
        ).fetchone()[0]
        opened = conn.execute(
            "SELECT COUNT(*) FROM email_events WHERE event_type='opened'"
        ).fetchone()[0]
        replies = conn.execute(
            "SELECT COUNT(*) FROM email_events WHERE event_type LIKE 'reply_%'"
        ).fetchone()[0]
        positive = conn.execute(
            "SELECT COUNT(*) FROM email_events WHERE event_type='reply_positive'"
        ).fetchone()[0]
        linkedin_sent = conn.execute(
            "SELECT COUNT(*) FROM sequence_touches WHERE touch_type IN ('linkedin_connection','linkedin_dm') AND status='sent'"
        ).fetchone()[0]

    open_rate = round(opened / sent * 100, 1) if sent else 0
    reply_rate = round(replies / sent * 100, 1) if sent else 0
    positive_rate = round(positive / replies * 100, 1) if replies else 0

    return {
        "emails_sent": sent,
        "emails_opened": opened,
        "open_rate_pct": open_rate,
        "replies": replies,
        "reply_rate_pct": reply_rate,
        "positive_replies": positive,
        "positive_reply_rate_pct": positive_rate,
        "linkedin_touches_sent": linkedin_sent,
    }


@router.get("/stats/ab")
def get_ab_stats():
    """Return A/B variant performance by persona and touch day."""
    init_db()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                t.persona,
                t.touch_day,
                t.variant,
                COUNT(*) as sent,
                SUM(CASE WHEN e.event_type='opened' THEN 1 ELSE 0 END) as opens,
                SUM(CASE WHEN e.event_type LIKE 'reply_%' THEN 1 ELSE 0 END) as replies
            FROM sequence_touches t
            LEFT JOIN email_events e ON t.id = e.touch_id
            WHERE t.touch_type = 'email'
            GROUP BY t.persona, t.touch_day, t.variant
            ORDER BY t.persona, t.touch_day, t.variant
        """).fetchall()
    return [dict(r) for r in rows]


@router.post("/pipeline/send-touches")
def trigger_send_touches():
    """Manually trigger sending of all due sequence touches."""
    from sequencing.sequence_scheduler import send_due_touches
    results = send_due_touches(dry_run=False)
    return results


@router.post("/pipeline/check-replies")
def trigger_check_replies():
    """Manually trigger Gmail IMAP reply check."""
    from sequencing.reply_detector import check_for_replies
    results = check_for_replies()
    return results


@router.post("/prospects/{prospect_id}/generate-opener")
def regenerate_opener(prospect_id: int):
    """Regenerate the GPT-4o opener for a specific prospect."""
    init_db()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")

    from models.prospect import Prospect, Persona, FundingStage, SequenceStatus
    from personalization import generate_opener
    from crm.hubspot import sync_prospect

    p = Prospect(
        first_name=row["first_name"] or "",
        last_name=row["last_name"] or "",
        email=row["email"],
        job_title=row["job_title"],
        company_name=row["company_name"] or "",
        industry=row["industry"],
        headcount=row["headcount"],
        persona=Persona(row["persona"]) if row["persona"] else Persona.UNKNOWN,
        funding_stage=FundingStage(row["funding_stage"]) if row["funding_stage"] else FundingStage.UNKNOWN,
        recent_news_summary=row["recent_news_summary"],
        composite_score=row["composite_score"] or 0,
    )
    p.hubspot_contact_id = str(prospect_id)

    try:
        p = generate_opener(p)
        sync_prospect(p)
        return {"opener": p.personal_opener}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
