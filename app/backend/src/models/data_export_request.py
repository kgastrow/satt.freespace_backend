from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class ExportStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class DataExportRequest(Base):
    """
    Tracks user data export requests for GDPR compliance.

    Users can request exports of their personal data. Exports are generated
    asynchronously and stored in S3 with a 30-day expiration period.
    """

    __tablename__ = "data_export_request"

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

    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # native_enum=False stores the uppercase member NAME as VARCHAR. Two
    # things this column used to get wrong, fixed together:
    #   * length: it was sized to the exact longest name of the day, so adding
    #     any longer member silently produced a StringDataRightTruncation (or
    #     worse, a truncated value) in production. 50 is the width used for
    #     every non-native enum in this codebase - roughly 4x the longest
    #     current member - and varchar(n) costs nothing extra in PostgreSQL.
    #   * create_constraint: SQLAlchemy 2.0 defaults it to False, so the column
    #     was a free-text VARCHAR. An out-of-range value was accepted on write
    #     and only blew up later on READ, as a LookupError deep in the ORM.
    #     True emits a CHECK so the database rejects it at the point of writing.
    status: Mapped[ExportStatus] = mapped_column(
        Enum(
            ExportStatus,
            native_enum=False,
            length=50,
            create_constraint=True,
            name="ck_data_export_request_status",
        ),
        nullable=False,
        default=ExportStatus.PENDING,
        index=True,
    )

    # S3 file details
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Download tracking
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Composite index for user data exports queries
        # Covers: WHERE user_id = X AND organization_id = X AND deleted_time IS NULL ORDER BY created_time DESC
        Index(
            "ix_data_export_user_org_created",
            "user_id",
            "organization_id",
            "deleted_time",
            desc("created_time"),
        ),
    )

    # Relationships
    user: Mapped[User] = relationship("User")
    organization: Mapped[Organization] = relationship("Organization")
