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
    from src.models.role import Role
    from src.models.user import User


class UserRole(Base):
    __tablename__ = "user_role"

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
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    role_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )

    __table_args__ = (
        # Partial unique index - prevents duplicate role assignments
        # Only enforced for non-deleted records
        Index(
            "uq_user_role_active",
            "organization_id",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="user_roles"
    )
    user: Mapped[User] = relationship(
        "User", foreign_keys=[user_id], back_populates="user_roles"
    )
    role: Mapped[Role] = relationship("Role", back_populates="user_roles")
    assigned_by_user: Mapped[User | None] = relationship(
        "User", foreign_keys=[assigned_by]
    )
