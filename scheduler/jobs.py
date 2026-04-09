"""
Scheduler — Job definitions for the SDR pipeline.

Uses APScheduler to run recurring pipeline jobs:
  - Daily sourcing: Apollo + LinkedIn pulls at 7 AM
  - Funding signals: Crunchbase poll every 60 minutes
  - Monthly re-scoring: Re-score Tier 3 prospects on the 1st Monday of each month

The scheduler runs as a background thread alongside the webhook server.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import CRUNCHBASE_POLL_INTERVAL_MIN, SOURCING_CRON_HOUR

log = structlog.get_logger(__name__)


def run_daily_sourcing() -> None:
    """
    Daily job: Pull prospects from Apollo and LinkedIn.
    Each new prospect flows through the full pipeline:
    enrichment → scoring → personalization → sequencing → CRM sync.
    """
    log.info("job_start", job="daily_sourcing")
    # Import here to avoid circular imports at module load time
    from main import run_pipeline_for_new_prospects
    try:
        run_pipeline_for_new_prospects()
    except Exception as exc:
        from alerts.slack import alert_error
        alert_error(str(exc), context="daily_sourcing job")
        log.error("job_failed", job="daily_sourcing", error=str(exc))


def run_funding_signal_poll() -> None:
    """
    Interval job: Poll Crunchbase for new funding rounds every 60 minutes.
    Matching companies are immediately scored and enrolled if Tier 1/2.
    """
    log.info("job_start", job="funding_signal_poll")
    from main import run_pipeline_for_funding_signals
    try:
        run_pipeline_for_funding_signals()
    except Exception as exc:
        from alerts.slack import alert_error
        alert_error(str(exc), context="funding_signal_poll job")
        log.error("job_failed", job="funding_signal_poll", error=str(exc))


def run_sequence_touches() -> None:
    """
    Daily job: Send all pending sequence touches (emails) scheduled for today or earlier.
    LinkedIn touches are marked ready for manual send via the UI.
    """
    log.info("job_start", job="sequence_touches")
    from sequencing.sequence_scheduler import send_due_touches
    try:
        results = send_due_touches(dry_run=False)
        log.info("job_complete", job="sequence_touches", **results)
    except Exception as exc:
        log.error("job_failed", job="sequence_touches", error=str(exc))


def run_reply_check() -> None:
    """
    Interval job: Poll Gmail IMAP for replies from prospects every 15 minutes.
    Positive replies fire a Slack alert and create a deal record.
    """
    log.info("job_start", job="reply_check")
    from sequencing.reply_detector import check_for_replies
    try:
        results = check_for_replies()
        log.info("job_complete", job="reply_check", **results)
    except Exception as exc:
        log.error("job_failed", job="reply_check", error=str(exc))


def run_monthly_rescore() -> None:
    """
    Monthly job: Re-score all Tier 3 (COOL) prospects.
    Prospects that cross into Tier 2+ are enrolled in sequences.
    """
    log.info("job_start", job="monthly_rescore")
    # TODO: Implement — fetch Tier 3 contacts from HubSpot,
    # re-run scoring with refreshed trigger data, update tiers
    log.warning("monthly_rescore_not_implemented")


def start_scheduler() -> BackgroundScheduler:
    """
    Initialize and start the APScheduler background scheduler.
    Returns the scheduler instance (keep a reference to prevent GC).
    """
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        run_daily_sourcing,
        CronTrigger(hour=SOURCING_CRON_HOUR, minute=0),
        id="daily_sourcing",
        name="Daily Apollo + LinkedIn sourcing",
        replace_existing=True,
    )

    scheduler.add_job(
        run_funding_signal_poll,
        IntervalTrigger(minutes=CRUNCHBASE_POLL_INTERVAL_MIN),
        id="funding_signal_poll",
        name="Crunchbase funding signal poll",
        replace_existing=True,
    )

    scheduler.add_job(
        run_monthly_rescore,
        CronTrigger(day="1st mon", hour=8, minute=0),
        id="monthly_rescore",
        name="Monthly Tier 3 re-score",
        replace_existing=True,
    )

    scheduler.add_job(
        run_sequence_touches,
        CronTrigger(hour=8, minute=30),
        id="sequence_touches",
        name="Daily sequence touch sender",
        replace_existing=True,
    )

    scheduler.add_job(
        run_reply_check,
        IntervalTrigger(minutes=15),
        id="reply_check",
        name="Gmail reply detector (every 15 min)",
        replace_existing=True,
    )

    scheduler.start()
    log.info("scheduler_started", job_count=len(scheduler.get_jobs()))
    return scheduler
