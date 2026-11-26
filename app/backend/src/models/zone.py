"""
Freespace zone: a floor or area within a site (BF-2, §10.2).

``slug`` is the wire ``zoneId``, unique within its site among live rows.
Capacity is NOT stored here: it arrives with every snapshot (BF-2).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.constants.freespace import ZONE_DEFAULTS
from src.database import Base


if TYPE_CHECKING:
    from src.models.site import Site


class Zone(Base):
    """A zone of a site. Settings are typed columns (D13)."""

    __tablename__ = "zone"

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
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False, index=True
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=ZONE_DEFAULTS["display_order"]
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=ZONE_DEFAULTS["enabled"]
    )
    recommendable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=ZONE_DEFAULTS["recommendable"]
    )
    preferred: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=ZONE_DEFAULTS["preferred"]
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=ZONE_DEFAULTS["priority"]
    )
    limited_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=ZONE_DEFAULTS["limited_pct"]
    )
    full_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=ZONE_DEFAULTS["full_pct"]
    )
    full_min_free: Mapped[int] = mapped_column(
        Integer, nullable=False, default=ZONE_DEFAULTS["full_min_free"]
    )
    unknown_limit_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=ZONE_DEFAULTS["unknown_limit_pct"]
    )
    # NULL = no zone advisory for this zone (BF-56)
    advisory_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Staff-only free text, never sent to the app (§10.2)
    note: Mapped[str] = mapped_column(
        Text, nullable=False, default=ZONE_DEFAULTS["note"]
    )
    # True when created by intake and not yet reviewed (BF-14)
    discovered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index(
            "uq_zone_site_slug_active",
            "site_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
            sqlite_where=text("deleted_time IS NULL"),
        ),
    )

    site: Mapped[Site] = relationship("Site", back_populates="zones", lazy="raise")
