from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.permission import Permission
    from src.models.user import User
    from src.models.user_type import UserType


class UserTypePermission(Base):
    """
    Links global user types to global permissions.
    This is a junction table that grants permissions based on user type.
    Unlike RolePermission which inherits tenant scope through the role,
    UserTypePermission is entirely global (like UserType itself).
    """

    __tablename__ = "user_type_permission"

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

    # Links global user type to global permission
    user_type_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_type.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permission.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Audit trail
    granted_by: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    granted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        # Partial unique index - only enforced for non-deleted records
        # Allows soft-deleted records to be recreated
        Index(
            "uq_user_type_permission_active",
            "user_type_id",
            "permission_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    user_type: Mapped[UserType] = relationship(
        "UserType", back_populates="user_type_permissions"
    )
    permission: Mapped[Permission] = relationship(
        "Permission", back_populates="user_type_permissions"
    )
    granted_by_user: Mapped[User | None] = relationship(
        "User", foreign_keys=[granted_by]
    )
