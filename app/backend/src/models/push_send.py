"""
Send history: one row per (advisory event, device) (BF-7, D10).

The at-most-once guarantee (BF-52, BT-02) rests on the unique constraint
``(event_id, device_id)``: the fan-out inserts the row with outcome
``PENDING`` and commits BEFORE calling FCM, then updates the outcome. A
resumed fan-out skips every device that already has a row.

Suppressed devices (BF-58) also get a row, with the reason as ``outcome`` and
no FCM call. Cooldown / daily-cap counting (BF-58, BF-60, BF-63) reads this
table: TEST rows never count, RECOVERY rows do
(``LIMIT_COUNTED_ADVISORY_TYPES``).

``organization_id`` is denormalised from the site so tenant-scoped admin
statistics follow CLAUDE.md rule 1. No ``deleted_time``: the 35-day retention
purge hard-deletes (D12).
"""

from __future__ import annotations

from datetime import datetime
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class PushSend(Base):
    """Outcome of one advisory for one device."""

    __tablename__ = "push_send"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False
    )
    event_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site_event.id"), nullable=False
    )
    device_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device.id"), nullable=False
    )
    site_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=False
    )
    # AdvisoryType value
    advisory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # DeviceOutcome value
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    # When the row was written (Freespace clock) - the time cooldown and the
    # daily cap are measured against.
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When FCM accepted the message (outcome SENT); "accepted by FCM", never
    # "delivered" (BF-69).
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # FCM error code for SEND_FAILED / TOKEN_INVALID (e.g. "UNREGISTERED")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("event_id", "device_id", name="uq_push_send_event_device"),
        Index("ix_push_send_device_queued", "device_id", "queued_at"),
        Index("ix_push_send_device_site_queued", "device_id", "site_id", "queued_at"),
        Index("ix_push_send_queued", "queued_at"),
        Index("ix_push_send_site", "site_id"),
    )
