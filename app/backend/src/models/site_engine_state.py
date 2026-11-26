"""
Persisted rules-engine state, one row per site (BF-5, D6).

The row is created together with its site (see
``src/services/freespace/site_bootstrap.py``) so it is always there to be
locked: every evaluation begins with ``SELECT ... FOR UPDATE`` on it (D6).

Zone references are zone SLUGS (wire ``zoneId``), not zone row ids, because
the pure engine core works on slugs. Timestamps written here always come from
the injected Freespace clock (D8), never from column defaults.

Convert to/from the pure ``EngineStateData`` with
``src/services/freespace/loaders.py`` (``engine_state_from_row`` /
``apply_engine_state``); do not hand-copy fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid as uuid_module

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.constants.freespace import EngineState
from src.database import Base


class SiteEngineState(Base):
    """Engine state of one site."""

    __tablename__ = "site_engine_state"

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
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False, unique=True
    )

    # State machine (BF-52)
    state: Mapped[str] = mapped_column(
        String(10), nullable=False, default=EngineState.IDLE.value
    )
    state_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Start of the current continuous fresh run at/above T (BF-53)
    pending_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Alerting cycle (spec §3): new id when ACTIVE is entered, cleared on reset
    cycle_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Last-notified values (BF-54): advance only when an advisory is sent to
    # >= 1 device (or, in shadow mode, would have been - Q5b).
    last_notified_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_notified_zone_slug: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    last_notified_top_zones: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    last_sent_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Current (sticky) recommendation (BF-24) and since when it is current
    current_zone_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_zone_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Per-zone advisory state (BF-56):
    #   {"<zone slug>": {"above_since": "<iso>" | null, "advised": bool}}
    zone_advisory_state: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Staleness as of the last evaluation, for DATA_STALE / DATA_RECOVERED
    # transitions (BF-62).
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stale_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # D10 in-flight guard: the advisory currently being fanned out
    inflight_event_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    inflight_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Operator-alert bookkeeping owned by M9 (BF-82: each alert fires once per
    # transition), e.g. {"silent_alerted_at": "<iso>" | null}. The engine
    # never reads or writes it.
    ops_alert_state: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
