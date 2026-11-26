from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class EmailChangeStatus(str, Enum):
    """Status of an email change request."""

    PENDING_VERIFICATION = "pending_verification"
    PENDING_OTP = "pending_otp"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class IdentityVerificationMethod(str, Enum):
    """Method used to verify the user's identity."""

    PASSWORD = "password"
    TOTP = "totp"
    SMS_2FA = "sms_2fa"


class EmailChangeRequest(Base):
    """
    Tenant-scoped email change request model.
    Stores email change requests with multi-step verification flow.
    """

    __tablename__ = "email_change_request"

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

    old_email: Mapped[str] = mapped_column(String(255), nullable=False)
    new_email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=EmailChangeStatus.PENDING_VERIFICATION.value
    )

    # Identity verification fields
    identity_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    identity_verification_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # OTP fields
    otp_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    otp_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_resend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Expiry and completion
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="email_change_requests"
    )
    user: Mapped[User] = relationship("User", back_populates="email_change_requests")

    __table_args__ = (
        Index(
            "ix_email_change_request_user_active",
            "user_id",
            postgresql_where=(
                "deleted_time IS NULL AND status IN ('pending_verification', 'pending_otp')"
            ),
            unique=True,
        ),
    )
