"""
Cron Job models for scheduled task management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class CronJobStatus(str, Enum):
    """Status values for cron job execution tracking."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class CronJobDefinition(Base):
    """
    Cron job definition with scheduling and configuration.

    Multi-tenancy: NULL organization_id = platform-wide job, UUID = org-scoped job.
    Platform-wide jobs run once globally, org-scoped jobs run per organization.
    """

    __tablename__ = "cron_job_definition"

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

    # Multi-tenancy: NULL = platform-wide, UUID = org-scoped
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Job identification
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # Unique identifier for job type

    # Scheduling
    schedule_expression: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # Cron syntax
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Configuration for new organizations
    is_enabled_by_default_for_new_orgs: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Job-specific parameters stored as JSON
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Execution tracking
    last_run_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CronJobStatus.PENDING.value
    )
    last_run_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped[Organization | None] = relationship("Organization")
    executions: Mapped[list[CronJobExecution]] = relationship(
        "CronJobExecution", back_populates="cron_job", cascade="all, delete-orphan"
    )

    # Composite indexes and constraints
    __table_args__ = (
        # Partial unique index on (code, organization_id) for active records only
        Index(
            "uq_cron_job_code_org_active",
            "code",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Index for scheduler queries (find active jobs due to run)
        Index("idx_cron_job_active_next_run", "is_active", "next_run_time"),
        # Index for org queries
        Index("idx_cron_job_org_active", "organization_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<CronJobDefinition {self.code} ({self.name})>"


class CronJobExecution(Base):
    """
    Individual execution record for a cron job.

    Tracks start time, completion time, status, and results/errors.
    Multi-tenancy: Inherits from parent job, NULL for platform-wide.
    """

    __tablename__ = "cron_job_execution"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Reference to job definition
    cron_job_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cron_job_definition.id"),
        nullable=False,
        index=True,
    )

    # Multi-tenancy: Denormalized from parent job for efficient querying
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Execution timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status and results
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CronJobStatus.RUNNING.value
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )  # Job-specific result data
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    cron_job: Mapped[CronJobDefinition] = relationship(
        "CronJobDefinition", back_populates="executions"
    )
    organization: Mapped[Organization | None] = relationship("Organization")

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_cron_execution_job_created", "cron_job_id", "created_time"),
        Index("idx_cron_execution_org_created", "organization_id", "created_time"),
        Index("idx_cron_execution_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<CronJobExecution {self.cron_job_id} {self.status}>"
