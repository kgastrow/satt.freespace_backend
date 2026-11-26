"""
Freespace site: one car park / one ParkIT installation (BF-1, §10.1, D13).

Tenant-scoped: ``organization_id`` is the customer (D2). ``slug`` is the wire
``siteId`` and is GLOBALLY unique among live rows, because the ingest and app
endpoints address a site by slug with no tenant context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.freespace import (
    DEFAULT_TIME_ZONE,
    SITE_DEFAULTS,
    default_notification_window,
)
from src.database import Base


if TYPE_CHECKING:
    from src.models.zone import Zone


class Site(Base):
    """A Freespace site. Settings are typed columns (D13, spec §10.1)."""

    __tablename__ = "site"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Identity (BF-1)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    time_zone: Mapped[str] = mapped_column(
        String(64), nullable=False, default=DEFAULT_TIME_ZONE
    )
    fcm_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    managed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=SITE_DEFAULTS["managed"]
    )
    listed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=SITE_DEFAULTS["listed"]
    )

    # Engine settings (§10.1). Percentages are whole points (1-100).
    trigger_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["trigger_pct"]
    )
    reset_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["reset_pct"]
    )
    change_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["change_points"]
    )
    change_direction: Mapped[str] = mapped_column(
        String(10), nullable=False, default=SITE_DEFAULTS["change_direction"]
    )
    stabilisation_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["stabilisation_s"]
    )
    recommendation_margin: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["recommendation_margin"]
    )
    stale_limit_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["stale_limit_s"]
    )
    partial_is_stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=SITE_DEFAULTS["partial_is_stale"]
    )
    recovery_push: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=SITE_DEFAULTS["recovery_push"]
    )
    zone_advisory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=SITE_DEFAULTS["zone_advisory"]
    )
    zone_reset_gap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["zone_reset_gap"]
    )
    # List of {"weekdays": [1..7], "start": "HH:MM", "end": "HH:MM"} in site
    # local time; [] = no window. Default Mon-Fri 06:00-10:00 (§15 Q4).
    notification_window: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=default_notification_window
    )
    # Used only when limit scope is DEVICE_PER_SITE (BF-63).
    cooldown_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["cooldown_s"]
    )
    daily_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["daily_cap"]
    )
    push_expiry_s: Mapped[int] = mapped_column(
        Integer, nullable=False, default=SITE_DEFAULTS["push_expiry_s"]
    )

    __table_args__ = (
        # siteId is globally unique among live sites (D2); soft-deleted slugs
        # may be reused.
        Index(
            "uq_site_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
            sqlite_where=text("deleted_time IS NULL"),
        ),
        Index("ix_site_org_active", "organization_id", "deleted_time"),
    )

    zones: Mapped[list[Zone]] = relationship(
        "Zone", back_populates="site", lazy="raise"
    )
