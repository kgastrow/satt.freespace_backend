from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.api_key_permission import ApiKeyPermission
    from src.models.organization import Organization
    from src.models.user import User


class ApiKeyScope(str, Enum):
    """Scope of the API key - determines what context it was created in."""

    USER = "user"  # Created by a user for their own use
    ORGANIZATION = "organization"  # Created through org admin endpoint
    PLATFORM = "platform"  # Created through platform admin endpoint


class ApiKey(Base):
    __tablename__ = "api_key"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expiry_warning_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expiry_notice_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApiKeyScope.USER.value, index=True
    )

    __table_args__ = (
        # key_hash must be globally unique (security requirement)
        UniqueConstraint("key_hash", name="uq_api_key_hash"),
        # Partial unique index for name per org - allows recreating deleted API keys
        Index(
            "uq_api_key_org_name_active",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="api_keys"
    )
    created_by_user: Mapped[User] = relationship("User", foreign_keys=[created_by])
    permissions: Mapped[list[ApiKeyPermission]] = relationship(
        "ApiKeyPermission", back_populates="api_key", cascade="all, delete-orphan"
    )
