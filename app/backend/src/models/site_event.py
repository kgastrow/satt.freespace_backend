"""
Freespace event log (BF-8, BF-62, D11).

Every engine decision, intake rejection, config change, test push and
announcement is one row. Per-device outcomes live in ``push_send`` (BF-7),
never here; ``counts`` holds the per-reason device totals of an advisory.

Write rows ONLY through ``src/services/freespace/events.py`` so the D11
repeat-collapse rule (``repeat_count`` / ``last_seen_at``) is applied
consistently.

No ``deleted_time``: the 365-day retention purge hard-deletes (D12, BF-73).
No device id or FCM token may ever be stored in any column here (BF-35).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid as uuid_module

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SiteEvent(Base):
    """One event of one site."""

    __tablename__ = "site_event"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )

    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False
    )

    # When it happened (Freespace clock) and, for collapsed repeats, when it
    # was last seen again (D11).
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # EventType value
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Reason code: SuppressionReason / StateChangeReason / IngestRejectReason /
    # IngestInconsistencyReason / FcmErrorReason / ConfigChangeReason value
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # AdvisoryType value for CANDIDATE / ADVISORY / TEST_PUSH events
    advisory_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Zone the event is about (ZONE_DISCOVERED, ZONE_ADVISORY, ...), by slug
    zone_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Engine cycle the event belongs to, when any
    cycle_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Site and zone figures at that moment, and the recommendation (BF-62):
    #   {"site": {...counts, "health", "occupancyPct", "stale"},
    #    "zones": {"<slug>": {...counts, "health", "status"}}}
    figures: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recommended_zone_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Advisory content (BF-62)
    rendered_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rendered_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Fan-out bookkeeping (D7, D10). fanout_status NULL = never fans out.
    # counts: {DeviceOutcome value: int}
    counts: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    fanout_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    fanout_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fanout_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fcm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Free-form, small, non-personal context: ingest warnings, config
    # before/after, actor user id, topic of a topic send, ...
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_site_event_site_occurred", "site_id", "occurred_at"),
        Index("ix_site_event_org_occurred", "organization_id", "occurred_at"),
        Index("ix_site_event_occurred", "occurred_at"),
        Index("ix_site_event_site_type", "site_id", "type"),
        # Engine tick looks for unfinished fan-outs (D7)
        Index(
            "ix_site_event_fanout_open",
            "fanout_status",
            postgresql_where=text("fanout_status IN ('PENDING', 'RUNNING')"),
            sqlite_where=text("fanout_status IN ('PENDING', 'RUNNING')"),
        ),
    )
