from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class DeletionStatus(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DataDeletionRequest(Base):
    """
    Tracks user account deletion requests for GDPR compliance.

    Users can request account deletion which triggers immediate soft delete
    and schedules hard deletion after a 30-day grace period. Users can cancel
    the request during this window to recover their account.
    """

    __tablename__ = "data_deletion_request"

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
    status: Mapped[DeletionStatus] = mapped_column(
        Enum(
            DeletionStatus,
            native_enum=False,
            length=50,
            create_constraint=True,
            name="ck_data_deletion_request_status",
        ),
        nullable=False,
        default=DeletionStatus.PENDING,
        index=True,
    )

    # Deletion timeline
    scheduled_hard_delete_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hard_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cancellation details
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User")
    organization: Mapped[Organization] = relationship("Organization")

    __table_args__ = (
        # Only one active deletion request per user (excluding cancelled/completed)
        Index(
            "uq_data_deletion_request_user_active",
            "user_id",
            unique=True,
            postgresql_where=text(
                "deleted_time IS NULL AND status NOT IN ('cancelled', 'completed')"
            ),
        ),
    )
