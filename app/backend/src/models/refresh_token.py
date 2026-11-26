from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, desc, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid_module.uuid4())
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Session metadata
    auth_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # email, google, etc.
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # IPv6 max
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Partial unique index - allows token reuse after soft delete
        Index(
            "uq_refresh_token_active",
            "token",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Composite index for user sessions queries (last login, active sessions)
        # Covers: WHERE user_id = X AND organization_id = X AND deleted_time IS NULL ORDER BY updated_time DESC
        Index(
            "ix_refresh_token_user_sessions",
            "user_id",
            "organization_id",
            "deleted_time",
            desc("updated_time"),
        ),
    )

    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="refresh_tokens"
    )
    user: Mapped[User] = relationship("User", backref="refresh_tokens")
