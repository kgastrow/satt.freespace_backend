"""
Report Schedule model for scheduled report generation.

Multi-tenancy: All schedules are organization-scoped and require organization_id filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.report import Report
    from src.models.user import User


class ReportSchedule(Base):
    """
    Report Schedule model for automated report generation.

    Multi-tenancy: All schedules are scoped to an organization.
    Schedules define when and how reports should be automatically generated.
    """

    __tablename__ = "report_schedule"

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
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy: Required organization scope
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Who created the schedule
    created_by_user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )

    # Schedule identification
    report_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # e.g., "users_report"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Scheduling configuration
    schedule_expression: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # Cron syntax, e.g., "0 9 * * 1" for every Monday at 9am
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Report-specific parameters/filters (stored as JSON)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Email recipients (list of email addresses)
    recipients: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Execution tracking
    last_run_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # pending, success, error
    last_run_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    created_by_user: Mapped[User | None] = relationship("User")
    reports: Mapped[list[Report]] = relationship(
        "Report", back_populates="schedule", cascade="all, delete-orphan"
    )

    # Composite indexes for common query patterns
    __table_args__ = (
        # Index for scheduler queries (find active schedules due to run)
        Index("idx_schedule_active_next_run", "is_active", "next_run_time"),
        Index("idx_schedule_org_active", "organization_id", "is_active"),
        Index("idx_schedule_org_type", "organization_id", "report_type"),
    )

    def __repr__(self) -> str:
        return f"<ReportSchedule {self.name} ({self.report_type}) - active={self.is_active}>"
