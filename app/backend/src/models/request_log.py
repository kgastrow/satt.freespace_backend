"""
Request Log model for storing API request/response logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class RequestLog(Base):
    """
    Request log for storing API request/response data for debugging.

    Records HTTP request details including timing, status codes, and sanitized
    request/response bodies. Used for:
    - API debugging and troubleshooting
    - Performance monitoring
    - Request history tracking
    - Error investigation

    Note: organization_id and user_id are nullable to support logging of
    unauthenticated requests (e.g., /auth/login).
    """

    __tablename__ = "request_log"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy - nullable for unauthenticated requests
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # User who made the request (nullable for unauthenticated requests)
    user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )

    # Request details
    method: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Request/response bodies (JSON, sanitized)
    request_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # Supports IPv6
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Error tracking - stack trace for 500 errors
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped[Organization | None] = relationship("Organization")
    user: Mapped[User | None] = relationship("User")

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("idx_request_log_org_created", "organization_id", "created_time"),
        Index("idx_request_log_status_created", "status_code", "created_time"),
        Index("idx_request_log_user_created", "user_id", "created_time"),
    )

    def __repr__(self) -> str:
        return f"<RequestLog {self.method} {self.path} {self.status_code}>"
