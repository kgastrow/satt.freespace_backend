from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, desc, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.email_change_request import EmailChangeRequest
    from src.models.file import File
    from src.models.file_usage import FileUsage
    from src.models.notification import Notification
    from src.models.organization import Organization
    from src.models.phone_verification import PhoneVerification
    from src.models.user_identity import UserIdentity
    from src.models.user_notification import UserNotification
    from src.models.user_notification_preference import UserNotificationPreference
    from src.models.user_onboarding_progress import UserOnboardingProgress
    from src.models.user_role import UserRole
    from src.models.user_two_factor import UserTwoFactor
    from src.models.user_user_type import UserUserType


class SuspensionStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class CreatedVia(str, enum.Enum):
    """Enum for tracking how a user account was created."""

    EMAIL = "email"
    GOOGLE = "google"
    # Future providers can be added here
    # MICROSOFT = "microsoft"
    # GITHUB = "github"


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Nullable for SSO-only users
    # native_enum=False stores the uppercase member NAME as VARCHAR. Two
    # things this column used to get wrong, fixed together:
    #   * length: it was sized to the exact longest name of the day, so adding
    #     any longer member silently produced a StringDataRightTruncation (or
    #     worse, a truncated value) in production. 50 is the width used for
    #     every non-native enum in this codebase - roughly 4x the longest
    #     current member - and varchar(n) costs nothing extra in PostgreSQL.
    #   * create_constraint: SQLAlchemy 2.0 defaults it to False, so the column
    #     was a free-text VARCHAR. An out-of-range value was accepted on write
    #     and only blew up later on READ, as a LookupError deep in the ORM.
    #     True emits a CHECK so the database rejects it at the point of writing.
    created_via: Mapped[CreatedVia] = mapped_column(
        Enum(
            CreatedVia,
            native_enum=False,
            length=50,
            create_constraint=True,
            name="ck_user_created_via",
        ),
        nullable=False,
        default=CreatedVia.EMAIL,
        server_default="EMAIL",  # For existing rows during migration
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_deliverable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # native_enum=False stores the uppercase member NAME as VARCHAR. Two
    # things this column used to get wrong, fixed together:
    #   * length: it was sized to the exact longest name of the day, so adding
    #     any longer member silently produced a StringDataRightTruncation (or
    #     worse, a truncated value) in production. 50 is the width used for
    #     every non-native enum in this codebase - roughly 4x the longest
    #     current member - and varchar(n) costs nothing extra in PostgreSQL.
    #   * create_constraint: SQLAlchemy 2.0 defaults it to False, so the column
    #     was a free-text VARCHAR. An out-of-range value was accepted on write
    #     and only blew up later on READ, as a LookupError deep in the ORM.
    #     True emits a CHECK so the database rejects it at the point of writing.
    suspension_status: Mapped[SuspensionStatus] = mapped_column(
        Enum(
            SuspensionStatus,
            native_enum=False,
            length=50,
            create_constraint=True,
            name="ck_user_suspension_status",
        ),
        nullable=False,
        default=SuspensionStatus.ACTIVE,
    )
    suspended_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspended_by: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avatar_file_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file.id", use_alter=True),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        # Partial unique indexes - only enforced for non-deleted records
        # Allows soft-deleted users to re-register with the same email/phone
        Index(
            "uq_user_org_email_active",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        Index(
            "uq_user_org_phone_active",
            "organization_id",
            "phone",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Composite index for user list queries with sorting by created_time
        # Covers: WHERE organization_id = X AND deleted_time IS NULL ORDER BY created_time DESC
        Index(
            "ix_user_org_active_created",
            "organization_id",
            "deleted_time",
            desc("created_time"),
        ),
        # Composite index for user list queries with status filtering
        # Covers: WHERE organization_id = X AND deleted_time IS NULL AND suspension_status = X
        Index(
            "ix_user_org_active_status",
            "organization_id",
            "deleted_time",
            "suspension_status",
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="users"
    )
    user_roles: Mapped[list[UserRole]] = relationship(
        "UserRole", foreign_keys="UserRole.user_id", back_populates="user"
    )

    # Notification relationships
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="user"
    )
    notification_preference: Mapped[UserNotificationPreference | None] = relationship(
        "UserNotificationPreference", back_populates="user", uselist=False
    )
    in_app_notifications: Mapped[list[UserNotification]] = relationship(
        "UserNotification", back_populates="user"
    )

    # File relationships
    uploaded_files: Mapped[list[File]] = relationship(
        "File", foreign_keys="[File.uploaded_by_user_id]", back_populates="uploaded_by"
    )
    file_usage: Mapped[FileUsage | None] = relationship(
        "FileUsage", back_populates="user", uselist=False
    )

    # Two-Factor Authentication relationship
    two_factor: Mapped[UserTwoFactor | None] = relationship(
        "UserTwoFactor", back_populates="user", uselist=False
    )
    # Suspension relationship
    suspended_by_user: Mapped[User | None] = relationship(
        "User", foreign_keys=[suspended_by], remote_side=[id], uselist=False
    )

    # Avatar relationship
    avatar: Mapped[File | None] = relationship(
        "File", foreign_keys=[avatar_file_id], lazy="selectin", uselist=False
    )

    # Onboarding relationships
    user_user_types: Mapped[list[UserUserType]] = relationship(
        "UserUserType", back_populates="user"
    )
    user_onboarding_progress: Mapped[list[UserOnboardingProgress]] = relationship(
        "UserOnboardingProgress", back_populates="user"
    )
    phone_verifications: Mapped[list[PhoneVerification]] = relationship(
        "PhoneVerification", back_populates="user"
    )
    email_change_requests: Mapped[list[EmailChangeRequest]] = relationship(
        "EmailChangeRequest", back_populates="user"
    )
    # SSO identity relationships
    identities: Mapped[list[UserIdentity]] = relationship(
        "UserIdentity", back_populates="user"
    )
