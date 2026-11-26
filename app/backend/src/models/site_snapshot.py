"""
Latest snapshot per site and per zone (BF-3).

One row per site (``site_snapshot``) and one per zone (``zone_snapshot``),
overwritten on each accepted submission. ``health`` is the EFFECTIVE health
used by the engine (BF-12 may downgrade OK -> PARTIAL on a sum mismatch);
``reported_health`` is what ParkIT sent. ``received_at`` is the backend clock
and is what staleness is judged on (BF-13); ``measured_at`` is ParkIT's clock.

Not soft-deleted: a snapshot is state, not a config entity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid as uuid_module

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SiteSnapshot(Base):
    """Latest site totals as computed by ParkIT (never summed from zones)."""

    __tablename__ = "site_snapshot"

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

    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    occupied: Mapped[int] = mapped_column(Integer, nullable=False)
    free_usable: Mapped[int] = mapped_column(Integer, nullable=False)
    free_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_disabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health: Mapped[str] = mapped_column(String(10), nullable=False)
    reported_health: Mapped[str] = mapped_column(String(10), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # {"product": ..., "version": ..., "instance": ...} as received
    publisher: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ZoneSnapshot(Base):
    """Latest figures for one zone."""

    __tablename__ = "zone_snapshot"

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
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False, index=True
    )
    zone_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zone.id"), nullable=False, unique=True
    )

    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    occupied: Mapped[int] = mapped_column(Integer, nullable=False)
    free_usable: Mapped[int] = mapped_column(Integer, nullable=False)
    free_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_disabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health: Mapped[str] = mapped_column(String(10), nullable=False)
    reported_health: Mapped[str] = mapped_column(String(10), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
