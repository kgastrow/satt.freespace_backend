"""
Two-Factor Authentication API endpoints.
Provides user-facing endpoints for 2FA setup and management.
"""

from datetime import datetime, timedelta, timezone
import traceback
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.security import verify_password
from src.crud import organization_two_factor_settings as org_2fa_crud
from src.crud import user as user_crud
from src.crud import user_two_factor as user_2fa_crud
from src.logger.logger import Logger
from src.serialisers.two_factor import (
    BackupCodesInfoResponse,
    BackupCodesResponse,
    DeleteTwoFactorRequest,
    DeleteTwoFactorResponse,
    TwoFactorPolicyResponse,
    TwoFactorSetupResponse,
    UsersWithout2FAResponse,
    UserTwoFactorStatusResponse,
    UserWithout2FAInfo,
    VerifyTwoFactorSetupRequest,
    VerifyTwoFactorSetupResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.two_factor import TwoFactorService


router = APIRouter(prefix="/two-factor", tags=["two-factor"])


@router.get("/policy", response_model=TwoFactorPolicyResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_two_factor_policy(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get the organization's 2FA policy for the current user.

    This endpoint is available to all authenticated users (no special permissions required).
    Used by the frontend to determine:
    - Whether to show 2FA settings in menus
    - Whether to enforce mandatory 2FA setup
    - Grace period deadlines for mandatory 2FA
    """
    # Get org 2FA settings
    org_2fa_settings = await org_2fa_crud.get_by_organization_id(
        session, current_user.organization_id
    )

    # Get user's 2FA status
    user_2fa = await user_2fa_crud.get_by_user_id(
        session, current_user.id, current_user.organization_id
    )
    user_has_2fa = user_2fa is not None and user_2fa.is_enabled

    # Default values if no settings exist
    if not org_2fa_settings:
        return TwoFactorPolicyResponse(
            two_factor_available=False,
            two_factor_policy="disabled",
            is_mandatory=False,
            grace_period_days=None,
            enforcement_deadline=None,
            user_has_2fa=user_has_2fa,
            requires_setup=False,
        )

    # Calculate if 2FA is available (allowed AND not disabled)
    two_factor_available = (
        org_2fa_settings.two_factor_allowed
        and org_2fa_settings.two_factor_policy != "disabled"
    )

    is_mandatory = org_2fa_settings.two_factor_policy == "mandatory"

    # Calculate enforcement deadline if mandatory
    enforcement_deadline = None
    if is_mandatory and org_2fa_settings.enforcement_start_time:
        enforcement_deadline = org_2fa_settings.enforcement_start_time + timedelta(
            days=org_2fa_settings.grace_period_days
        )

    # User requires setup if mandatory 2FA is active and they don't have it
    requires_setup = is_mandatory and two_factor_available and not user_has_2fa

    return TwoFactorPolicyResponse(
        two_factor_available=two_factor_available,
        two_factor_policy=cast(
            Literal["disabled", "optional", "mandatory"],
            org_2fa_settings.two_factor_policy,
        ),
        is_mandatory=is_mandatory,
        grace_period_days=org_2fa_settings.grace_period_days if is_mandatory else None,
        enforcement_deadline=enforcement_deadline,
        user_has_2fa=user_has_2fa,
        requires_setup=requires_setup,
    )


@router.get("/users-without-2fa", response_model=UsersWithout2FAResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_users_without_2fa(
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("two_factor:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get list of users in the organization who don't have 2FA enabled.

    Requires two_factor:read permission. Used by admins to see which users
    need to set up 2FA when mandatory enforcement is active.
    """
    users = await user_2fa_crud.get_users_without_2fa(
        session, current_user.organization_id
    )

    return UsersWithout2FAResponse(
        users=[UserWithout2FAInfo.model_validate(user) for user in users],
        total=len(users),
    )


@router.post("/setup", response_model=TwoFactorSetupResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def initiate_two_factor_setup(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Initiate 2FA setup for the current user. Returns secret and provisioning URI."""
    try:
        org_2fa_settings = await org_2fa_crud.get_by_organization_id(
            session, current_user.organization_id
        )
        if not org_2fa_settings or not org_2fa_settings.two_factor_allowed:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA is not enabled for this organization",
                detail_code="two_factor.not_allowed",
            )

        existing = await user_2fa_crud.get_by_user_id(
            session, current_user.id, current_user.organization_id
        )
        if existing:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is already set up for this user",
                detail_code="two_factor.already_exists",
            )

        # Generate a proper TOTP secret
        secret = TwoFactorService.generate_secret()
        # Use org-specific 2FA app name if configured, otherwise fall back to global app name
        issuer_name = org_2fa_settings.two_factor_app_name or settings.APP_NAME
        provisioning_uri = TwoFactorService.generate_provisioning_uri(
            secret, current_user.email, issuer=issuer_name
        )

        # Return the secret for the user to add to their authenticator app
        # The secret is shown once and will be encrypted when stored after verification
        return TwoFactorSetupResponse(
            secret=secret,
            provisioning_uri=provisioning_uri,
            qr_code_data=provisioning_uri,  # QR code encodes the provisioning URI
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="two_factor.invalid_request",
        )


@router.post("/verify-setup", response_model=VerifyTwoFactorSetupResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def verify_two_factor_setup(
    request: Request,
    verify_request: VerifyTwoFactorSetupRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Verify 2FA setup by validating TOTP code. Creates 2FA record and returns backup codes."""
    try:
        # Check organization allows 2FA
        org_2fa_settings = await org_2fa_crud.get_by_organization_id(
            session, current_user.organization_id
        )
        if not org_2fa_settings or not org_2fa_settings.two_factor_allowed:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA is not enabled for this organization",
                detail_code="two_factor.not_allowed",
            )

        # Check user doesn't already have 2FA enabled
        existing = await user_2fa_crud.get_by_user_id(
            session, current_user.id, current_user.organization_id
        )
        if existing:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is already set up for this user",
                detail_code="two_factor.already_exists",
            )

        # Verify the TOTP code against the provided secret
        if not TwoFactorService.verify_totp(verify_request.secret, verify_request.code):
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please try again.",
                detail_code="two_factor.invalid_code",
            )

        # Generate backup codes
        plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=10)

        # Create the 2FA record with encrypted secret
        user_2fa = await user_2fa_crud.create(
            session,
            {
                "user_id": current_user.id,
                "secret": verify_request.secret,
                "is_enabled": True,
                "verified_at": datetime.now(timezone.utc),
            },
            current_user.organization_id,
        )

        # Store hashed backup codes
        for hashed_code in hashed_codes:
            await user_2fa_crud.create_backup_code(
                session, str(user_2fa.id), hashed_code
            )

        return VerifyTwoFactorSetupResponse(
            message="Two-factor authentication has been enabled successfully",
            message_code="two_factor.enabled",
            backup_codes=plain_codes,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="two_factor.invalid_request",
        )


@router.get("/status", response_model=UserTwoFactorStatusResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_two_factor_status(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get the current user's 2FA status."""
    try:
        user_2fa = await user_2fa_crud.get_by_user_id(
            session, current_user.id, current_user.organization_id
        )
        if not user_2fa:
            return UserTwoFactorStatusResponse(is_enabled=False, verified_at=None)
        return UserTwoFactorStatusResponse(
            is_enabled=user_2fa.is_enabled, verified_at=user_2fa.verified_at
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="two_factor.invalid_request",
        )


@router.get("/backup-codes", response_model=BackupCodesInfoResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def get_backup_codes_info(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get backup codes status for the current user's 2FA.

    Note: Backup codes are hashed and cannot be retrieved after initial setup.
    This endpoint returns the count of remaining unused codes.
    Use POST /two-factor/regenerate-backup-codes to generate new codes.
    """
    try:
        user_2fa = await user_2fa_crud.get_by_user_id(
            session, current_user.id, current_user.organization_id
        )
        if not user_2fa:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="2FA is not set up for this user",
                detail_code="two_factor.not_found",
            )

        backup_codes = await user_2fa_crud.get_backup_codes(
            session, current_user.id, current_user.organization_id
        )

        total_codes = len(backup_codes)
        used_codes = sum(1 for code in backup_codes if code.used_at is not None)
        remaining_codes = total_codes - used_codes

        return BackupCodesInfoResponse(
            total_codes=total_codes,
            remaining_codes=remaining_codes,
            used_codes=used_codes,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="two_factor.not_found",
        )


@router.post("/regenerate-backup-codes", response_model=BackupCodesResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def regenerate_backup_codes(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Regenerate backup codes for the current user.

    This invalidates all existing backup codes and generates 10 new ones.
    The new codes are only shown once - store them securely.
    """
    try:
        user_2fa = await user_2fa_crud.get_by_user_id(
            session, current_user.id, current_user.organization_id
        )
        if not user_2fa or not user_2fa.is_enabled:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="2FA is not set up for this user",
                detail_code="two_factor.not_found",
            )

        # Delete existing backup codes (soft delete)
        existing_codes = await user_2fa_crud.get_backup_codes(
            session, current_user.id, current_user.organization_id
        )
        for code in existing_codes:
            code.deleted_time = datetime.now(timezone.utc)

        # Generate new backup codes
        plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=10)

        # Store hashed backup codes
        for hashed_code in hashed_codes:
            await user_2fa_crud.create_backup_code(
                session, str(user_2fa.id), hashed_code
            )

        await session.commit()

        return BackupCodesResponse(backup_codes=plain_codes)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="two_factor.not_found",
        )


@router.delete("/setup", response_model=DeleteTwoFactorResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def delete_two_factor(
    request: Request,
    delete_request: DeleteTwoFactorRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete 2FA setup for the current user. Requires password re-authentication."""
    try:
        # Verify password for re-authentication before allowing 2FA deletion
        user = await user_crud.get_user_by_id(
            session, current_user.id, current_user.organization_id
        )
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        if not verify_password(delete_request.password, user.password):
            raise create_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password",
                detail_code="auth.invalid_password",
            )

        await user_2fa_crud.delete(
            session, current_user.id, current_user.organization_id
        )
        return DeleteTwoFactorResponse(
            message="2FA has been disabled",
            message_code="two_factor.disabled",
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="two_factor.not_found",
        )


# =============================================================================
# Admin 2FA Management Endpoints
# =============================================================================


class AdminDisable2FAResponse(DeleteTwoFactorResponse):
    """Response for admin 2FA disable."""

    user_id: str


@router.delete("/admin/users/{user_id}/2fa", response_model=AdminDisable2FAResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def admin_disable_two_factor(
    user_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Admin endpoint to disable 2FA for a user (super admin only).

    This allows admins to help users who have been locked out of their
    accounts due to lost 2FA devices or backup codes.
    """
    try:
        organization_id = str(current_user.organization_id)

        # Verify target user exists
        user = await user_crud.get_user_by_id(session, user_id, organization_id)
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Check if user has 2FA enabled
        user_2fa = await user_2fa_crud.get_by_user_id(session, user_id, organization_id)
        if not user_2fa or not user_2fa.is_enabled:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not have 2FA enabled",
                detail_code="two_factor.not_enabled",
            )

        # Disable 2FA for the user
        await user_2fa_crud.delete(session, user_id, organization_id)

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserTwoFactor",
            resource_id=str(user_2fa.id),
            old_values={"is_enabled": True},
            new_values={"is_enabled": False, "disabled_by_admin": True},
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            # `log_update` takes no `resource_name`; passing one raised
            # TypeError and turned admin-disable-2FA into a 500.
            resource_context={"resource_name": f"2FA for {user.email}"},
        )

        return AdminDisable2FAResponse(
            message="2FA has been disabled for this user",
            message_code="two_factor.admin_disabled",
            user_id=user_id,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="two_factor.not_found",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to disable 2FA for user: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="server.error",
        )
