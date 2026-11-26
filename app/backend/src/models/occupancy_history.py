"""
Occupancy history, at most one point per minute per site and per zone (BF-4, D14).

``zone_id IS NULL`` is the site row. Uniqueness is enforced by two partial
unique indexes, because a plain UNIQUE (site_id, zone_id, bucket_minute) does
not hold for NULL zone_id in PostgreSQL. Upserts (last value in the minute
wins) must target the matching index:

    site row:  ON CONFLICT (site_id, bucket_minute) WHERE zone_id IS NULL
    zone row:  ON CONFLICT (zone_id, bucket_minute) WHERE zone_id IS NOT NULL

Retention purge (BF-73) hard-deletes in batches by ``bucket_minute`` (D12);
hence no ``deleted_time``. The primary key is a BIGINT identity rather than a
UUID because of the expected volume (~57 M rows at 180 days, D14).
"""

from __future__ import annotations

from datetime import datetime
import uuid as uuid_module

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class OccupancyHistory(Base):
    """One minute bucket of figures for a site (zone_id NULL) or a zone."""

    __tablename__ = "occupancy_history"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False
    )
    zone_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zone.id"), nullable=True
    )
    # Start of the minute (seconds and microseconds zeroed), UTC
    bucket_minute: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    occupied: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    free_usable: Mapped[int] = mapped_column(Integer, nullable=False)
    health: Mapped[str] = mapped_column(String(10), nullable=False)

    __table_args__ = (
        Index(
            "uq_occupancy_history_site_minute",
            "site_id",
            "bucket_minute",
            unique=True,
            postgresql_where=text("zone_id IS NULL"),
            sqlite_where=text("zone_id IS NULL"),
        ),
        Index(
            "uq_occupancy_history_zone_minute",
            "zone_id",
            "bucket_minute",
            unique=True,
            postgresql_where=text("zone_id IS NOT NULL"),
            sqlite_where=text("zone_id IS NOT NULL"),
        ),
        # Chart query and purge (D14)
        Index("ix_occupancy_history_site_minute", "site_id", "bucket_minute"),
        Index("ix_occupancy_history_bucket_minute", "bucket_minute"),
        Index("ix_occupancy_history_org", "organization_id"),
    )
