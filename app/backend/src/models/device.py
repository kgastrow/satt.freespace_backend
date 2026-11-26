"""
Freespace device (one app install) and its site selections (BF-6, D5).

NOT tenant data (D2): one phone may select sites of several customers, so
neither table has ``organization_id``. Device statistics are computed per site
and so stay tenant-scoped at query time.

Privacy (BF-35, D5):
- The raw ``deviceId`` is never stored. ``device_key_hash`` is
  SHA-256(deviceId) (``src/services/freespace/keys.hash_device_id``) and is the
  lookup key; ``id_suffix`` is the last 6 characters, for the test push of
  BF-74.
- ``DELETE /v1/devices/{id}`` (BF-34) nulls ``fcm_token``,
  ``device_key_hash`` and ``id_suffix``, hard-deletes the ``device_site`` rows
  and sets ``deleted_time``. The tombstone keeps platform, app version and
  dates only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Device(Base):
    """One installed copy of the Freespace app."""

    __tablename__ = "device"

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

    # SHA-256 hex of the deviceId; NULL on a tombstone. UNIQUE allows many
    # NULLs in both PostgreSQL and SQLite.
    device_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    id_suffix: Mapped[str | None] = mapped_column(String(6), nullable=True)
    # FCM registration tokens are ~160-200 chars; 512 keeps the unique btree
    # well under PostgreSQL's index row limit.
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("device_key_hash", name="uq_device_key_hash"),
        UniqueConstraint("fcm_token", name="uq_device_fcm_token"),
        Index("ix_device_id_suffix", "id_suffix"),
        Index("ix_device_last_seen", "last_seen"),
    )


class DeviceSite(Base):
    """A site selected by a device. Hard-deleted on opt-out (BF-34, D12)."""

    __tablename__ = "device_site"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    device_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("device_id", "site_id", name="uq_device_site"),
        Index("ix_device_site_site", "site_id"),
    )
