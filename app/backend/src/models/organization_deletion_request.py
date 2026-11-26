from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class OrganizationDeletionRequest(Base):
    """
    Tracks deletion requests for organizations.

    When an organization owner requests deletion, a record is created here.
    A super admin must approve and execute the actual deletion.
    Only one active deletion request can exist per organization.
    """

    __tablename__ = "organization_deletion_request"

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
        UUID(as_uuid=True),
        ForeignKey("organization.id"),
        nullable=False,
        index=True,
    )
    requested_by_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="deletion_request"
    )
    requested_by: Mapped[User] = relationship("User")

    __table_args__ = (
        Index(
            "uq_organization_deletion_request_org_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )
