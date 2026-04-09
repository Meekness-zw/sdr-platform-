"""
SDR Pipeline — Main Orchestrator

Wires all five layers together end-to-end:
  Layer 1: Sourcing    — Apollo, Crunchbase, LinkedIn
  Layer 2: Enrichment  — Clay, BuiltWith, GPT-4o news
  Layer 3: Scoring     — Composite firmographic + intent score
  Layer 4: Personalization + Sequencing — GPT-4o opener, Instantly, Expandi
  Layer 5: CRM Sync + Alerts — HubSpot, Slack

Run modes:
  python main.py              — start full pipeline (scheduler + webhook server)
  python main.py --score-test — run scoring engine on sample data, no APIs needed
"""

from __future__ import annotations

import argparse
import sys

import structlog

log = structlog.get_logger(__name__)


def run_pipeline_for_prospect(prospect):
    """
    Run a single prospect through all five pipeline layers.
    Each layer's failures are handled individually — a failure in
    enrichment does not block scoring, etc.
    """
    from alerts.slack import alert_hot_lead
    from crm.hubspot import sync_prospect
    from enrichment import enrich_prospect
    from models.prospect import Tier
    from personalization import generate_opener
    from scoring import score_prospect
    from sequencing import enroll_in_sequence, send_linkedin_connection
    from sequencing.expandi import build_connection_note

    log.info("pipeline_start", name=prospect.full_name(), company=prospect.company_name)

    # Layer 2: Enrichment
    try:
        prospect = enrich_prospect(prospect)
    except Exception as exc:
        log.warning("enrichment_failed", error=str(exc))

    # Layer 3: Scoring
    prospect = score_prospect(prospect)
    log.info(
        "pipeline_scored",
        name=prospect.full_name(),
        score=prospect.composite_score,
        tier=prospect.tier.value if prospect.tier else "none",
    )

    # Layer 4: Personalization (only for Tier 1 & 2)
    if prospect.is_qualified():
        try:
            prospect = generate_opener(prospect)
        except NotImplementedError:
            log.debug("opener_not_implemented")
        except Exception as exc:
            log.warning("opener_failed", error=str(exc))

    # Layer 4: Sequence enrollment
    if prospect.is_qualified():
        try:
            prospect = enroll_in_sequence(prospect)
        except NotImplementedError:
            log.debug("enrollment_not_implemented")
        except Exception as exc:
            log.warning("enrollment_failed", error=str(exc))

    # Layer 4: LinkedIn connection (Day 3 — queued, not sent immediately)
    if prospect.is_qualified() and prospect.linkedin_url:
        try:
            note = build_connection_note(prospect)
            send_linkedin_connection(prospect, message=note)
        except NotImplementedError:
            log.debug("linkedin_not_implemented")
        except Exception as exc:
            log.warning("linkedin_failed", error=str(exc))

    # Layer 5: CRM sync
    try:
        prospect = sync_prospect(prospect)
    except NotImplementedError:
        log.debug("hubspot_not_implemented")
    except Exception as exc:
        log.warning("hubspot_sync_failed", error=str(exc))

    # Layer 5: Slack alert for HOT leads
    if prospect.tier == Tier.HOT:
        try:
            alert_hot_lead(prospect)
        except Exception as exc:
            log.warning("slack_alert_failed", error=str(exc))

    log.info("pipeline_complete", name=prospect.full_name(), tier=prospect.tier.value if prospect.tier else "none")
    return prospect


def run_pipeline_for_new_prospects() -> None:
    """Pull new prospects from Apollo and LinkedIn and run each through the pipeline."""
    from sourcing import fetch_prospects_apollo, fetch_prospects_linkedin

    prospects: list[Prospect] = []

    try:
        prospects += fetch_prospects_apollo()
    except NotImplementedError:
        log.debug("apollo_not_implemented")

    try:
        prospects += fetch_prospects_linkedin()
    except NotImplementedError:
        log.debug("linkedin_sourcing_not_implemented")

    log.info("sourcing_complete", count=len(prospects))
    for prospect in prospects:
        run_pipeline_for_prospect(prospect)


def run_pipeline_for_funding_signals() -> None:
    """Poll Crunchbase for funding signals and run matched companies through the pipeline."""
    from sourcing import poll_funding_signals

    try:
        stubs = poll_funding_signals()
    except NotImplementedError:
        log.debug("crunchbase_not_implemented")
        return

    log.info("funding_signals_found", count=len(stubs))
    for stub in stubs:
        run_pipeline_for_prospect(stub)


def run_score_test() -> None:
    """
    Run the scoring engine on a set of sample prospects.
    No API keys required. Use this to validate scoring logic.
    """
    from scoring.scorer import score_prospect
    from models.prospect import FundingStage, Prospect, TriggerEvent

    samples = [
        Prospect(
            first_name="Sarah",
            last_name="Chen",
            job_title="COO",
            company_name="Acme SaaS",
            industry="SaaS",
            headcount=150,
            funding_stage=FundingStage.SERIES_B,
            triggers=[TriggerEvent.FUNDING_ROUND, TriggerEvent.NEW_EXEC_HIRE],
        ),
        Prospect(
            first_name="James",
            last_name="Okafor",
            job_title="CEO",
            company_name="HealthBridge",
            industry="Health Tech",
            headcount=90,
            funding_stage=FundingStage.SERIES_A,
            triggers=[TriggerEvent.AI_JOB_POSTING],
        ),
        Prospect(
            first_name="Maria",
            last_name="Lopez",
            job_title="VP People",
            company_name="Retail Co",
            industry="E-Commerce",
            headcount=400,
            funding_stage=FundingStage.UNKNOWN,
            triggers=[],
        ),
        Prospect(
            first_name="Tom",
            last_name="Burke",
            job_title="Founder",
            company_name="Tiny Startup",
            industry="Other",
            headcount=10,
            funding_stage=FundingStage.PRE_SEED,
            triggers=[],
        ),
    ]

    print("\n── SDR Scoring Test ─────────────────────────────────────────────")
    print(f"{'Name':<20} {'Company':<18} {'Firm':>5} {'Intent':>7} {'Total':>6} {'Tier':<20} {'Persona'}")
    print("─" * 90)

    for p in samples:
        p = score_prospect(p)
        print(
            f"{p.full_name():<20} {p.company_name:<18} "
            f"{p.firmographic_score:>5} {p.intent_score:>7} {p.composite_score:>6} "
            f"{p.tier.value:<20} {p.persona.value}"
        )

    print("─" * 90)
    print("Tiers: HOT ≥70 | WARM 45–69 | COOL 25–44 | DISQUALIFIED <25\n")


def _process_prospects(prospects: list, dry_run: bool = True) -> None:
    """Score, personalize, save, email-preview, and alert for a list of prospects."""
    from crm.database import print_prospects_table
    from scoring import score_prospect
    from personalization import generate_opener
    from sequencing.gmail import send_outreach_email
    from crm.hubspot import sync_prospect
    from alerts.slack import alert_hot_lead
    from models.prospect import Tier

    hot_count = 0
    warm_count = 0

    for prospect in prospects:
        # Score
        prospect = score_prospect(prospect)

        # Personalize (only Tier 1 & 2)
        if prospect.is_qualified():
            try:
                prospect = generate_opener(prospect)
            except Exception as exc:
                log.warning("opener_failed", error=str(exc))

        # Save to DB
        prospect = sync_prospect(prospect)

        # Enroll in multi-touch sequence
        if prospect.is_qualified() and prospect.hubspot_contact_id:
            try:
                from sequencing.sequence_scheduler import enroll_prospect_sequence
                persona = prospect.persona.value if prospect.persona else "CEO"
                enroll_prospect_sequence(int(prospect.hubspot_contact_id), persona)
            except Exception as exc:
                log.warning("sequence_enrollment_failed", error=str(exc))

        # Email preview / send
        if prospect.is_qualified():
            send_outreach_email(prospect, dry_run=dry_run)

        # Slack alert for HOT
        if prospect.tier == Tier.HOT:
            hot_count += 1
            try:
                alert_hot_lead(prospect)
            except Exception as exc:
                log.warning("slack_alert_failed", error=str(exc))
        elif prospect.tier and prospect.tier.value == "tier_2_warm":
            warm_count += 1

    print(f"\nDone. HOT: {hot_count} | WARM: {warm_count} | Total: {len(prospects)}")
    if hot_count > 0:
        print("Slack alerts fired for HOT prospects — check #hot-leads.")
    print_prospects_table()


def run_pipeline(max_results: int = 10, dry_run: bool = True) -> None:
    """Pull from Apollo API and run full pipeline."""
    from crm.database import init_db
    from sourcing.apollo import fetch_prospects_apollo

    init_db()
    print(f"\nFetching up to {max_results} prospects from Apollo...")
    prospects = fetch_prospects_apollo(max_results=max_results)
    print(f"Fetched {len(prospects)} prospects.\n")
    _process_prospects(prospects, dry_run=dry_run)


def run_pipeline_from_csv(filepath: str, dry_run: bool = True) -> None:
    """Load prospects from Apollo CSV export and run full pipeline."""
    from crm.database import init_db
    from sourcing.csv_loader import load_from_csv

    init_db()
    print(f"\nLoading prospects from {filepath}...")
    prospects = load_from_csv(filepath)
    print(f"Loaded {len(prospects)} prospects from CSV.\n")
    _process_prospects(prospects, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="SDR Pipeline")
    parser.add_argument(
        "--score-test",
        action="store_true",
        help="Run scoring engine on sample data (no API keys required)",
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Pull real prospects from Apollo and run full pipeline",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Max prospects to pull from Apollo (default: 10)",
    )
    parser.add_argument(
        "--send-emails",
        action="store_true",
        help="Actually send emails via Gmail (default is dry-run preview only)",
    )
    parser.add_argument(
        "--show-db",
        action="store_true",
        help="Print all prospects stored in the local database",
    )
    parser.add_argument(
        "--from-csv",
        type=str,
        metavar="FILE",
        help="Load prospects from an Apollo CSV export and run full pipeline",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the web dashboard at http://localhost:8000",
    )
    args = parser.parse_args()

    if args.score_test:
        run_score_test()
        return

    if args.show_db:
        from crm.database import init_db, print_prospects_table
        init_db()
        print_prospects_table()
        return

    if args.from_csv:
        run_pipeline_from_csv(args.from_csv, dry_run=not args.send_emails)
        return

    if args.run_pipeline:
        run_pipeline(max_results=args.max_results, dry_run=not args.send_emails)
        return

    # Dashboard server mode
    import uvicorn
    from webhooks.server import app

    if args.serve:
        print("\n🚀 SDR Agent dashboard starting...")
        print("   Open: http://localhost:8000\n")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
        return

    # Full mode: scheduler + server
    from scheduler import start_scheduler
    scheduler = start_scheduler()
    log.info("sdr_pipeline_starting", mode="full")
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
