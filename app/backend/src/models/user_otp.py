from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class OTPType(str, Enum):
    """Types of OTP/token that can be generated."""

    VERIFICATION = "verification"
    PASSWORD_RESET = "password_reset"


class UserOTP(Base):
    """
    Stores OTPs for email verification and password reset tokens.

    The otp_type field distinguishes between:
    - VERIFICATION: 4-digit codes for email verification (10 min expiry)
    - PASSWORD_RESET: 32-char tokens for password reset (1 hour expiry)
    """

    __tablename__ = "user_otp"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    otp_code: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # Increased to support 32-char reset tokens
    otp_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OTPType.VERIFICATION.value, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempts_count: Mapped[int] = mapped_column(
        default=0, server_default="0", nullable=False
    )  # Track failed verification attempts for brute-force protection
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="user_otps"
    )
