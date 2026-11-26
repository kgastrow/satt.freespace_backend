from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class UserInvitation(Base):
    """
    Tenant-scoped invitation for a user to join an organization.

    Tracks pending invitations with optional pre-assigned roles and user types.
    Invitations expire after 7 days and are accepted during registration.
    """

    __tablename__ = "user_invitation"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    invited_by_user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    # JSON arrays of UUIDs (stored as text); nullable means none pre-assigned
    role_ids: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    user_type_ids: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    __table_args__ = (
        # Prevent duplicate pending invitations per email per org
        Index(
            "uq_user_invitation_active",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_time IS NULL AND accepted_at IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", foreign_keys=[organization_id]
    )
    invited_by: Mapped[User] = relationship("User", foreign_keys=[invited_by_user_id])
