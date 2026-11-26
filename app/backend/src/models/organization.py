from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.announcement import Announcement
    from src.models.api_key import ApiKey
    from src.models.api_key_permission import ApiKeyPermission
    from src.models.bulk_notification import BulkNotification
    from src.models.email_change_request import EmailChangeRequest
    from src.models.file import File
    from src.models.file_usage import FileUsage
    from src.models.help_center import HelpArticle, HelpFaq
    from src.models.notification import Notification
    from src.models.notification_category import NotificationCategory
    from src.models.notification_template import NotificationTemplate
    from src.models.organization_deletion_request import OrganizationDeletionRequest
    from src.models.organization_email_settings import OrganizationEmailSettings
    from src.models.organization_file_settings import OrganizationFileSettings
    from src.models.organization_notification_settings import (
        OrganizationNotificationSettings,
    )
    from src.models.organization_payment_settings import OrganizationPaymentSettings
    from src.models.organization_two_factor_settings import (
        OrganizationTwoFactorSettings,
    )
    from src.models.phone_verification import PhoneVerification
    from src.models.refresh_token import RefreshToken
    from src.models.user import User
    from src.models.user_onboarding_progress import UserOnboardingProgress
    from src.models.user_otp import UserOTP
    from src.models.user_role import UserRole
    from src.models.user_two_factor import UserTwoFactor
    from src.models.user_user_type import UserUserType


class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    # Organization details
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Physical address
    physical_address_line1: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    physical_address_line2: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state_province: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Contact information
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Logo reference
    logo_file_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file.id", use_alter=True), nullable=True
    )

    __table_args__ = (
        # Partial unique index - allows soft-deleted org slugs to be reused
        Index(
            "uq_organization_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Composite index for listing queries (filtering by deleted_time and ordering by created_time)
        Index("ix_organization_deleted_created", "deleted_time", "created_time"),
    )

    # Relationships
    users: Mapped[list[User]] = relationship("User", back_populates="organization")
    user_roles: Mapped[list[UserRole]] = relationship(
        "UserRole", back_populates="organization"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="organization"
    )
    user_otps: Mapped[list[UserOTP]] = relationship(
        "UserOTP", back_populates="organization"
    )

    # Notification relationships
    notification_templates: Mapped[list[NotificationTemplate]] = relationship(
        "NotificationTemplate", back_populates="organization"
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="organization"
    )
    bulk_notifications: Mapped[list[BulkNotification]] = relationship(
        "BulkNotification", back_populates="organization"
    )
    notification_settings: Mapped[OrganizationNotificationSettings | None] = (
        relationship(
            "OrganizationNotificationSettings",
            back_populates="organization",
            uselist=False,
        )
    )
    notification_categories: Mapped[list[NotificationCategory]] = relationship(
        "NotificationCategory", back_populates="organization"
    )

    # Announcement relationships
    announcements: Mapped[list[Announcement]] = relationship(
        "Announcement", back_populates="organization"
    )

    # Help Center relationships
    help_articles: Mapped[list[HelpArticle]] = relationship(
        "HelpArticle", back_populates="organization"
    )
    help_faqs: Mapped[list[HelpFaq]] = relationship(
        "HelpFaq", back_populates="organization"
    )

    # File relationships
    files: Mapped[list[File]] = relationship(
        "File", back_populates="organization", foreign_keys="[File.organization_id]"
    )
    file_usages: Mapped[list[FileUsage]] = relationship(
        "FileUsage", back_populates="organization"
    )
    file_settings: Mapped[OrganizationFileSettings | None] = relationship(
        "OrganizationFileSettings", back_populates="organization", uselist=False
    )
    logo_file: Mapped[File | None] = relationship("File", foreign_keys=[logo_file_id])

    # Deletion request relationship (one-to-one, nullable)
    deletion_request: Mapped[OrganizationDeletionRequest | None] = relationship(
        "OrganizationDeletionRequest", back_populates="organization", uselist=False
    )

    # API key relationships
    api_keys: Mapped[list[ApiKey]] = relationship(
        "ApiKey", back_populates="organization"
    )
    api_key_permissions: Mapped[list[ApiKeyPermission]] = relationship(
        "ApiKeyPermission", back_populates="organization"
    )

    # Two-Factor Authentication relationships
    two_factor_settings: Mapped[OrganizationTwoFactorSettings | None] = relationship(
        "OrganizationTwoFactorSettings", back_populates="organization", uselist=False
    )
    user_two_factors: Mapped[list[UserTwoFactor]] = relationship(
        "UserTwoFactor", back_populates="organization"
    )

    # Onboarding relationships
    user_user_types: Mapped[list[UserUserType]] = relationship(
        "UserUserType", back_populates="organization"
    )
    user_onboarding_progress: Mapped[list[UserOnboardingProgress]] = relationship(
        "UserOnboardingProgress", back_populates="organization"
    )
    phone_verifications: Mapped[list[PhoneVerification]] = relationship(
        "PhoneVerification", back_populates="organization"
    )
    email_change_requests: Mapped[list[EmailChangeRequest]] = relationship(
        "EmailChangeRequest", back_populates="organization"
    )

    # Payment relationships
    payment_settings: Mapped[OrganizationPaymentSettings | None] = relationship(
        "OrganizationPaymentSettings", back_populates="organization", uselist=False
    )

    # Email settings relationship
    email_settings: Mapped[OrganizationEmailSettings | None] = relationship(
        "OrganizationEmailSettings", back_populates="organization", uselist=False
    )
