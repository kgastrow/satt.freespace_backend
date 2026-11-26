"""
Audit Log model for tracking CRUD operations on tenant-scoped resources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class AuditAction(str, Enum):
    """Types of auditable actions."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    IMPERSONATE_START = "IMPERSONATE_START"
    IMPERSONATE_END = "IMPERSONATE_END"


class AuditLog(Base):
    """
    Audit log for tracking changes to tenant-scoped resources.

    Records who did what, when, and what changed. Used for:
    - Compliance and regulatory requirements
    - Security auditing
    - Debugging and troubleshooting
    - Activity history

    Note: AuditLog entries are never deleted (immutable audit trail).
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Multi-tenancy - which organization this audit belongs to
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Who performed the action (nullable for system actions)
    actor_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )

    # Who was impersonating when this action was performed (nullable if not impersonating)
    impersonated_by: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )

    # What action was performed
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # What resource was affected
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # What changed (JSON with old/new values)
    # Format: {"field_name": {"old": old_value, "new": new_value}, ...}
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Human-readable identifier for the resource (stored at audit time)
    resource_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # Additional context captured at audit time (e.g., extra resource details)
    resource_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Request context
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # Supports IPv6
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    actor: Mapped[User | None] = relationship("User", foreign_keys=[actor_id])
    impersonator: Mapped[User | None] = relationship(
        "User", foreign_keys=[impersonated_by]
    )

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("idx_audit_org_created", "organization_id", "created_time"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index(
            "idx_audit_org_actor_created",
            "organization_id",
            "actor_id",
            "created_time",
        ),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.resource_type}:{self.resource_id}>"
