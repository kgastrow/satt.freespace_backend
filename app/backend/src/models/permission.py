from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.api_key_permission import ApiKeyPermission
    from src.models.role_permission import RolePermission
    from src.models.user_type_permission import UserTypePermission


class Permission(Base):
    """
    Global permission definition.
    Permissions are platform-wide (no organization_id) and follow the format 'resource:action'.
    Example: 'users:read', 'users:write', 'roles:delete'
    """

    __tablename__ = "permission"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Permission identifier: "resource:action" format
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Human-readable metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Parsed components for UI grouping and filtering
    resource: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # e.g., "users", "roles"
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "read", "write", "delete"

    # Display ordering within resource groups
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Partial unique index - allows soft-deleted permission codes to be reused
        Index(
            "uq_permission_code_active",
            "code",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    role_permissions: Mapped[list[RolePermission]] = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )
    api_key_permissions: Mapped[list[ApiKeyPermission]] = relationship(
        "ApiKeyPermission", back_populates="permission", cascade="all, delete-orphan"
    )
    user_type_permissions: Mapped[list[UserTypePermission]] = relationship(
        "UserTypePermission", back_populates="permission", cascade="all, delete-orphan"
    )
