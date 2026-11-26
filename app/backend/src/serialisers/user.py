import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

from src.serialisers.common import NormalizedEmail


PhoneNumber.phone_format = "E164"


# Password complexity requirements
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]).+$"
)


def validate_password_complexity(password: str) -> str:
    """
    Validate password meets complexity requirements:
    - At least 8 characters
    - At most 128 characters
    - At least one lowercase letter
    - At least one uppercase letter
    - At least one digit
    - At least one special character
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long"
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"Password must be at most {PASSWORD_MAX_LENGTH} characters long"
        )
    if not PASSWORD_PATTERN.match(password):
        raise ValueError(
            "Password must contain at least one lowercase letter, "
            "one uppercase letter, one digit, and one special character"
        )
    return password


class GetUserRequest(BaseModel):
    id: Optional[UUID] = Field(None)
    email: Optional[NormalizedEmail] = Field(None, max_length=255)

    model_config = ConfigDict(extra="forbid")


class GetUserResponse(BaseModel):
    id: UUID
    created_time: str
    updated_time: str
    email: EmailStr
    email_verified: bool
    email_deliverable: bool
    phone: Optional[PhoneNumber]
    phone_verified: bool
    first_name: Optional[str]
    last_name: Optional[str]
    is_admin: Optional[bool]


class CreateUserRequest(BaseModel):
    email: NormalizedEmail = Field(..., max_length=255)
    password: Optional[str] = Field(None, max_length=255)
    email_verified: Optional[bool] = Field(False)
    email_deliverable: Optional[bool] = Field(True)
    phone: Optional[PhoneNumber] = Field(None, max_length=255)
    phone_verified: Optional[bool] = Field(False)
    first_name: Optional[str] = Field(None, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    is_admin: Optional[bool] = Field(False)
    created_via: Optional[str] = Field(None)

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password complexity if provided (None allowed for SSO users)"""
        if v is not None:
            return validate_password_complexity(v)
        return v


class UpdateUserRequest(BaseModel):
    id: UUID
    email: Optional[NormalizedEmail] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=255)
    email_verified: Optional[bool] = Field(None)
    email_deliverable: Optional[bool] = Field(None)
    phone: Optional[PhoneNumber] = Field(None, max_length=255)
    phone_verified: Optional[bool] = Field(None)
    first_name: Optional[str] = Field(None, max_length=255)
    last_name: Optional[str] = Field(None, max_length=255)
    is_admin: Optional[bool] = Field(None)

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password complexity if provided"""
        if v is not None:
            return validate_password_complexity(v)
        return v


class DeleteUserRequest(BaseModel):
    id: UUID

    model_config = ConfigDict(extra="forbid")


# API request/response models for user registration and profile


class RegisterRequest(BaseModel):
    email: NormalizedEmail
    password: str
    organization_slug: str
    phone: Optional[PhoneNumber] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    invite_token: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity"""
        return validate_password_complexity(v)


class UserResponse(BaseModel):
    id: str
    email: str
    email_deliverable: bool = True


class RegisterResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user: UserResponse
    requires_verification: bool


class UserProfileRoleInfo(BaseModel):
    """Role info for user profile."""

    id: str
    name: str


class UserProfileOrganizationInfo(BaseModel):
    """Organization info for user profile."""

    id: str
    name: str
    slug: str


class UserProfileResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    email_deliverable: bool
    phone: Optional[PhoneNumber]
    phone_verified: bool = False
    first_name: Optional[str]
    last_name: Optional[str]
    is_admin: bool
    organization_id: str
    organization: Optional[UserProfileOrganizationInfo] = None
    roles: list[UserProfileRoleInfo] = []
    avatar_url: Optional[str] = None
    full_avatar_url: Optional[str] = None


class UpdateUserProfileRequest(BaseModel):
    """Request model for updating own user profile (no id, used with /me endpoint)"""

    email: Optional[NormalizedEmail] = None
    password: Optional[str] = None
    phone: Optional[PhoneNumber] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password complexity if provided"""
        if v is not None:
            return validate_password_complexity(v)
        return v


class UpdateUserProfileResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user: dict


class ChangePasswordRequest(BaseModel):
    """Request model for changing password with current password verification."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password complexity."""
        return validate_password_complexity(v)


class ChangePasswordResponse(BaseModel):
    """Response model for successful password change."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class AvatarUploadResponse(BaseModel):
    """Response model for avatar upload."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    avatar_url: Optional[str] = None
    full_avatar_url: Optional[str] = None


class DeleteAvatarResponse(BaseModel):
    """Response model for avatar deletion."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")


class UserPermissionsResponse(BaseModel):
    """Response containing user's effective permissions."""

    permissions: list[str]


# API request/response models for admin user management


class UserRoleInfo(BaseModel):
    """Simple role info for user listing."""

    id: str
    name: str


class UserDetailResponse(BaseModel):
    id: str
    email: str
    email_verified: bool
    email_deliverable: bool
    phone: Optional[str] = None
    phone_verified: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: bool
    created_time: str
    updated_time: Optional[str] = None
    suspension_status: Optional[str] = None
    roles: list[UserRoleInfo] = []


class UserListResponse(BaseModel):
    items: list[UserDetailResponse]
    total: int
    limit: int
    offset: int


class AdminCreateUserRequest(BaseModel):
    """Request model for admin creating a user (no id, simplified)"""

    email: NormalizedEmail
    password: str
    phone: Optional[PhoneNumber] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: bool = False

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password complexity"""
        return validate_password_complexity(v)


class AdminUpdateUserRequest(BaseModel):
    """Request model for admin updating a user (id comes from path parameter)"""

    email: Optional[NormalizedEmail] = None
    password: Optional[str] = None
    phone: Optional[PhoneNumber] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password complexity if provided, treat empty string as None"""
        if v is not None and v != "":
            return validate_password_complexity(v)
        return None


class CreateUserApiResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user: UserDetailResponse


class AdminUpdateUserResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user: UserDetailResponse


class DeleteUserApiResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str


class SuspendUserRequest(BaseModel):
    """Request model for suspending a user."""

    reason: Optional[str] = Field(None, max_length=500)
    send_notification: bool = Field(False)

    model_config = ConfigDict(extra="forbid")


class SuspendUserResponse(BaseModel):
    """Response model for suspending a user."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str


class UnsuspendUserResponse(BaseModel):
    """Response model for unsuspending a user."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str


# Enhanced user list/detail models for admin user management


class UserTypeOnboardingInfo(BaseModel):
    """User type with onboarding status."""

    id: str
    name: str
    code: str
    onboarding_status: str
    onboarded_at: Optional[str] = None


class UserSessionInfo(BaseModel):
    """Session information for user detail."""

    id: str
    created_time: str
    updated_time: Optional[str] = None
    expires_at: str
    auth_provider: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    is_current: bool = False


class TwoFactorStatusInfo(BaseModel):
    """Two-factor authentication status."""

    is_enabled: bool = False
    verified_at: Optional[str] = None
    backup_codes_remaining: int = 0


class FileUsageInfo(BaseModel):
    """File usage breakdown."""

    total_files: int = 0
    total_size_bytes: int = 0
    image_count: int = 0
    image_size_bytes: int = 0
    video_count: int = 0
    video_size_bytes: int = 0
    document_count: int = 0
    document_size_bytes: int = 0
    audio_count: int = 0
    audio_size_bytes: int = 0
    other_count: int = 0
    other_size_bytes: int = 0


class FeedbackSummaryInfo(BaseModel):
    """Summary of user's feedback."""

    id: str
    type: str
    subject: str
    status: str
    created_time: str


class NotificationPreferencesInfo(BaseModel):
    """User notification preferences summary."""

    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = False
    in_app_enabled: bool = True


class IdentityProviderInfo(BaseModel):
    """Identity provider link info."""

    id: str
    provider: str
    provider_email: Optional[str] = None
    created_time: str


class DataExportInfo(BaseModel):
    """Data export request info."""

    id: str
    status: str
    created_time: str
    completed_at: Optional[str] = None
    file_size_bytes: Optional[int] = None
    download_count: int = 0
    expires_at: Optional[str] = None


class ImpersonationHistoryInfo(BaseModel):
    """Impersonation session info."""

    id: str
    impersonator_id: str
    impersonator_name: Optional[str] = None
    created_time: str
    ended_time: Optional[str] = None


class SuspensionInfo(BaseModel):
    """Suspension details for a user."""

    suspended_time: Optional[str] = None
    suspended_by: Optional[str] = None
    suspended_by_name: Optional[str] = None
    suspension_reason: Optional[str] = None


class UserListItemResponse(BaseModel):
    """
    User list item with sparse fieldset support.
    All fields except id are optional to support sparse fieldsets.
    """

    id: str
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    email_deliverable: Optional[bool] = None
    phone: Optional[str] = None
    phone_verified: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: Optional[bool] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None
    suspension_status: Optional[str] = None
    created_via: Optional[str] = None
    roles: Optional[list[UserRoleInfo]] = None
    user_types: Optional[list[UserTypeOnboardingInfo]] = None
    avatar_url: Optional[str] = None
    total_storage_bytes: Optional[int] = None
    last_login: Optional[str] = None


class UserEnhancedListResponse(BaseModel):
    """Enhanced paginated user list response."""

    items: list[UserListItemResponse]
    total: int
    limit: int
    offset: int


class UserCursorListResponse(BaseModel):
    """Cursor-paginated user list response for large datasets.

    Cursor pagination provides O(1) performance regardless of page depth,
    unlike offset pagination which degrades linearly.
    """

    items: list[UserListItemResponse]
    total: int
    limit: int
    next_cursor: str | None = None
    has_more: bool = False


class UserFullDetailResponse(BaseModel):
    """
    Complete user details including all related data.
    Used for the user detail page.
    """

    # Basic info
    id: str
    email: str
    email_verified: bool
    email_deliverable: bool
    phone: Optional[str] = None
    phone_verified: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: bool
    created_time: str
    updated_time: Optional[str] = None
    created_via: str
    avatar_url: Optional[str] = None

    # Status
    suspension_status: str
    suspension_info: Optional[SuspensionInfo] = None

    # Roles and types
    roles: list[UserRoleInfo] = []
    user_types: list[UserTypeOnboardingInfo] = []

    # Sessions
    sessions: list[UserSessionInfo] = []

    # Security
    two_factor: TwoFactorStatusInfo
    identity_providers: list[IdentityProviderInfo] = []

    # Files
    file_usage: Optional[FileUsageInfo] = None

    # Activity
    feedback: list[FeedbackSummaryInfo] = []
    data_exports: list[DataExportInfo] = []
    impersonation_history: list[ImpersonationHistoryInfo] = []

    # Notification preferences
    notification_preferences: Optional[NotificationPreferencesInfo] = None


class InvalidateSessionRequest(BaseModel):
    """Request to invalidate a user session."""

    model_config = ConfigDict(extra="forbid")


class InvalidateSessionResponse(BaseModel):
    """Response from session invalidation."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    session_id: str


# Login History Models


class LoginHistoryEntry(BaseModel):
    """Single login history entry."""

    id: str
    created_time: str
    success: bool
    auth_method: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    failure_reason: Optional[str] = None


class LoginHistoryResponse(BaseModel):
    """Paginated login history response."""

    items: list[LoginHistoryEntry]
    total: int
    limit: int
    offset: int


# Admin Notification Preferences Models


class AdminUpdateNotificationPreferencesRequest(BaseModel):
    """Request model for admin updating a user's notification preferences."""

    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class NotificationPreferencesFullInfo(BaseModel):
    """Full notification preferences including all channels."""

    email_enabled: bool = True
    sms_enabled: bool = True
    whatsapp_enabled: bool = True
    in_app_enabled: bool = True
    quiet_hours_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    quiet_hours_timezone: str = "UTC"


class AdminNotificationPreferencesResponse(BaseModel):
    """Response for admin notification preferences endpoint."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str
    preferences: NotificationPreferencesFullInfo


class AdminPasswordResetResponse(BaseModel):
    """Response for admin password reset endpoint."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str
