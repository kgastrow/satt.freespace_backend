"""
User Identity model for tracking SSO provider links.

This model stores the relationship between users and their SSO provider identities,
enabling proper account linking and SSO login flows.
"""

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


class UserIdentity(Base):
    """
    Represents a user's identity from an SSO provider.

    Each record links a user to a specific provider identity (e.g., Google account).
    A user can have multiple identities from different providers.
    """

    __tablename__ = "user_identity"

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
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'google', 'microsoft', etc.
    provider_user_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # User's ID from the provider
    provider_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Email from provider (for reference)

    __table_args__ = (
        # Unique constraint: one provider identity per user per org
        Index(
            "uq_user_identity_user_provider_active",
            "organization_id",
            "user_id",
            "provider",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Unique constraint: provider_user_id is unique per provider per org
        # Prevents the same provider account from being linked to multiple users
        Index(
            "uq_user_identity_provider_user_id_active",
            "organization_id",
            "provider",
            "provider_user_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    user: Mapped[User] = relationship("User", back_populates="identities")
