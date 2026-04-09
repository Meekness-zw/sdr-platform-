"""
CRM — Layer 5: Local SQLite (HubSpot replacement for MVP).

All prospect and deal activity is stored in sdr.db.
Swap this out for real HubSpot integration when ready to scale.
"""

from __future__ import annotations

import structlog

from models.prospect import Prospect, SequenceStatus
from .database import log_activity, upsert_prospect

log = structlog.get_logger(__name__)


def sync_prospect(prospect: Prospect) -> Prospect:
    """Upsert prospect into local SQLite database."""
    row_id = upsert_prospect(prospect)
    prospect.hubspot_contact_id = str(row_id)
    log.info("crm_synced", name=prospect.full_name(), db_id=row_id)
    log_activity(row_id, "synced", f"score={prospect.composite_score} tier={prospect.tier.value if prospect.tier else 'none'}")
    return prospect


def create_deal(prospect: Prospect) -> Prospect:
    """Log a deal creation event for a prospect."""
    if not prospect.hubspot_contact_id:
        return prospect
    log_activity(
        int(prospect.hubspot_contact_id),
        "deal_created",
        f"positive reply from {prospect.email}",
    )
    log.info("deal_created", name=prospect.full_name())
    return prospect


def update_sequence_stage(prospect: Prospect, status: SequenceStatus) -> None:
    """Update sequence status in local database."""
    if not prospect.hubspot_contact_id:
        return
    prospect.sequence_status = status
    upsert_prospect(prospect)
    log_activity(
        int(prospect.hubspot_contact_id),
        "status_updated",
        status.value,
    )
