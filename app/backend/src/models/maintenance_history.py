"""
MaintenanceHistory model for tracking maintenance periods.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.user import User


class MaintenanceStatus(str, Enum):
    """Status of a maintenance period."""

    SCHEDULED = "scheduled"  # Scheduled but not yet started
    ACTIVE = "active"  # Currently in maintenance
    COMPLETED = "completed"  # Maintenance ended normally
    CANCELLED = "cancelled"  # Scheduled maintenance was cancelled


class MaintenanceHistory(Base):
    """
    History of maintenance periods.

    Tracks both scheduled and actual maintenance times, who initiated/ended
    maintenance, and the message displayed to users.

    Note: This is a global model (no organization_id) - only super admins
    can access maintenance history.
    """

    __tablename__ = "maintenance_history"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Status of this maintenance period
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MaintenanceStatus.SCHEDULED.value,
        index=True,
    )

    # Scheduled times (as planned)
    scheduled_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Actual times (when maintenance really started/ended)
    actual_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Message displayed during maintenance
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who initiated the maintenance
    started_by_user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )

    # Who ended the maintenance
    ended_by_user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )

    # Relationships
    started_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[started_by_user_id]
    )
    ended_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[ended_by_user_id]
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_maintenance_history_status", "status"),
        Index("idx_maintenance_history_created", "created_time"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceHistory {self.id} status={self.status}>"
