from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.api_key import ApiKey
    from src.models.organization import Organization
    from src.models.permission import Permission


class ApiKeyPermission(Base):
    """
    Links organization-scoped API keys to global permissions.
    This is a junction table that connects api_keys to the permission table.
    """

    __tablename__ = "api_key_permission"

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
    api_key_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_key.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permission.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # Partial unique index - allows revoking and re-granting permissions
        Index(
            "uq_api_key_permission_active",
            "api_key_id",
            "permission_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="api_key_permissions"
    )
    api_key: Mapped[ApiKey] = relationship("ApiKey", back_populates="permissions")
    permission: Mapped[Permission] = relationship(
        "Permission", back_populates="api_key_permissions"
    )
