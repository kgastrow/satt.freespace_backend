"""
ApiKeyRateLimit model for configurable rate limits per permission type.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid as uuid_module

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class ApiKeyRateLimit(Base):
    """
    Global rate limit configuration per permission type.

    Rate limits are system-wide defaults that apply to all API keys
    regardless of organization. Super admins can configure rate limits
    for specific permission codes to prevent abuse.

    Example: Set 'users:read' to 100 requests/minute with burst of 20.
    """

    __tablename__ = "api_key_rate_limit"

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

    # Permission code this rate limit applies to (e.g., "users:read")
    permission_code: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    # Maximum requests allowed per minute
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)

    # Maximum burst requests allowed (above steady rate)
    burst_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        # Partial unique index - only one active rate limit per permission code
        Index(
            "uq_api_key_rate_limit_permission_code_active",
            "permission_code",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ApiKeyRateLimit {self.permission_code}: {self.requests_per_minute}/min, burst={self.burst_limit}>"
