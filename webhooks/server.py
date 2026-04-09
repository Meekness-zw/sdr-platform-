"""
SDR Web Server — FastAPI app serving the dashboard UI + API + webhooks.

Run with:
  python main.py --serve
  Then open: http://localhost:8000
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.routes import router as api_router
from config.settings import settings
from crm.database import init_db
from models.prospect import Prospect, SequenceStatus

log = structlog.get_logger(__name__)

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="SDR Agent")

# Mount API routes
app.include_router(api_router)

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup():
    init_db()
    log.info("sdr_server_started")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard UI."""
    html_file = TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
    return HTMLResponse(html_file.read_text())


@app.get("/health")
async def health():
    return {"status": "ok"}


# 1x1 transparent GIF
_TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@app.get("/track/open")
async def track_open(pid: Optional[int] = None, tid: Optional[int] = None):
    """
    Email open tracking pixel.
    Called when prospect loads the HTML email.
    Logs an 'opened' event to email_events and returns a 1x1 GIF.
    """
    if pid:
        try:
            from crm.database import get_conn
            now = datetime.utcnow().isoformat()
            with get_conn() as conn:
                # Avoid duplicate open events within same touch
                existing = conn.execute(
                    "SELECT id FROM email_events WHERE prospect_id=? AND touch_id IS ? AND event_type='opened'",
                    (pid, tid),
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO email_events (prospect_id, touch_id, event_type, logged_at) VALUES (?,?,?,?)",
                        (pid, tid, "opened", now),
                    )
            log.info("email_open_tracked", prospect_id=pid, touch_id=tid)
        except Exception as exc:
            log.warning("open_tracking_failed", error=str(exc))

    return Response(content=_TRACKING_PIXEL, media_type="image/gif")


# ── Instantly reply webhook ───────────────────────────────────────────────────

class InstantlyReplyPayload(BaseModel):
    email: str
    campaign_id: str
    reply_text: str
    prospect_id: Optional[str] = None
    timestamp: Optional[str] = None


@app.post("/webhooks/reply")
async def handle_reply(request: Request) -> dict:
    body = await request.body()
    _verify_signature(request, body)
    payload = InstantlyReplyPayload.model_validate(await request.json())
    log.info("reply_received", email=payload.email, campaign=payload.campaign_id)

    prospect = _lookup_prospect_by_email(payload.email)
    if not prospect:
        return {"status": "ignored", "reason": "prospect not found"}

    sentiment = _classify_sentiment(payload.reply_text)
    if sentiment == "positive":
        prospect.sequence_status = SequenceStatus.POSITIVE_REPLY
        try:
            from alerts.slack import alert_positive_reply
            from crm.hubspot import create_deal, update_sequence_stage
            alert_positive_reply(prospect, payload.reply_text)
            create_deal(prospect)
            update_sequence_stage(prospect, SequenceStatus.POSITIVE_REPLY)
        except Exception as exc:
            log.warning("reply_handler_error", error=str(exc))
    else:
        try:
            from crm.hubspot import update_sequence_stage
            update_sequence_stage(prospect, SequenceStatus.REPLIED)
        except Exception:
            pass

    return {"status": "ok", "sentiment": sentiment}


def _classify_sentiment(reply_text: str) -> str:
    if not settings.openai_api_key:
        return "neutral"
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": (
                "Classify the sentiment of this cold email reply as exactly one of: "
                "positive, negative, neutral. Reply with ONLY the single word."
            )},
            {"role": "user", "content": reply_text},
        ],
        temperature=0, max_tokens=5,
    )
    result = response.choices[0].message.content.strip().lower()
    return result if result in ("positive", "negative", "neutral") else "neutral"


def _verify_signature(request: Request, body: bytes) -> None:
    if not settings.webhook_secret:
        return
    signature = request.headers.get("X-Instantly-Signature", "")
    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _lookup_prospect_by_email(email: str) -> Prospect | None:
    from crm.database import get_conn
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM prospects WHERE email = ?", (email,)).fetchone()
    if not row:
        return None
    return Prospect(
        first_name=row["first_name"] or "",
        last_name=row["last_name"] or "",
        email=row["email"],
        job_title=row["job_title"],
        company_name=row["company_name"] or "",
        hubspot_contact_id=str(row["id"]),
    )
