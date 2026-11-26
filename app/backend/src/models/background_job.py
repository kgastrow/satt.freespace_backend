"""
Background Job Execution model for persistent tracking of ARQ task executions.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class BackgroundJobExecution(Base):
    """
    Individual execution record for a background (ARQ) task.

    Tracks start time, completion, status, duration, and errors.
    Not tenant-scoped — these are platform-wide system records.
    """

    __tablename__ = "background_job_execution"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Job identification
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)

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
        String(20), nullable=False
    )  # "success" | "failure" | "running"
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Error details
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_bg_job_exec_type_created", "job_type", "created_time"),
        Index("idx_bg_job_exec_created", "created_time"),
        Index("idx_bg_job_exec_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<BackgroundJobExecution {self.job_type} {self.status}>"
