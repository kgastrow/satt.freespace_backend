"""
Report model for generated reports.

Multi-tenancy: All reports are organization-scoped and require organization_id filtering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.file import File
    from src.models.organization import Organization
    from src.models.report_schedule import ReportSchedule
    from src.models.user import User


class ReportStatus(str, Enum):
    """Status values for report generation."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Report(Base):
    """
    Report model for tracking generated reports.

    Multi-tenancy: All reports are scoped to an organization.
    Reports track the generation status, parameters used, and link to the output file.
    """

    __tablename__ = "report"

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

    # Who generated the report
    generated_by_user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )

    # Report identification
    report_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # e.g., "users_report"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Report-specific parameters/filters (stored as JSON)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReportStatus.PENDING.value, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Result data
    file_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id"), nullable=True
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional link to schedule (if generated from a schedule)
    schedule_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_schedule.id"), nullable=True, index=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    generated_by_user: Mapped[User | None] = relationship("User")
    file: Mapped[File | None] = relationship("File")
    schedule: Mapped[ReportSchedule | None] = relationship(
        "ReportSchedule", back_populates="reports"
    )

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("idx_report_org_created", "organization_id", "created_time"),
        Index("idx_report_org_status", "organization_id", "status"),
        Index("idx_report_org_type", "organization_id", "report_type"),
    )

    def __repr__(self) -> str:
        return f"<Report {self.name} ({self.report_type}) - {self.status}>"
