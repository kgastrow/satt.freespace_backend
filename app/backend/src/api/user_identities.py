"""
User Identity API endpoints.
Provides user-facing endpoints for managing connected accounts (SSO identities).
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
)
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.security import hash_password
from src.crud import organization_two_factor_settings as org_2fa_crud
from src.crud import user as user_crud
from src.crud import user_identity as identity_crud
from src.crud import user_two_factor as user_2fa_crud
from src.models.user import CreatedVia
from src.serialisers.user_identity import (
    UnlinkIdentityResponse,
    UnlinkWithSetupRequest,
    UnlinkWithSetupResponse,
    UserIdentitiesResponse,
    UserIdentityResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.two_factor import TwoFactorService


router = APIRouter(prefix="/user/me/identities", tags=["user-identities"])


@router.get("", response_model=UserIdentitiesResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_user_identities(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get all linked identities for the current user.

    Returns the list of connected accounts (email, SSO providers) along with
    metadata about the user's account setup and 2FA status.
    """
    # Get full user to check password and created_via
    user = await user_crud.get_user_by_id(
        session, current_user.id, current_user.organization_id
    )
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Get all user identities
    identities = await identity_crud.get_by_user_id(
        session, current_user.id, current_user.organization_id
    )

    # Get 2FA policy and status
    org_2fa_settings = await org_2fa_crud.get_by_organization_id(
        session, current_user.organization_id
    )
    user_2fa = await user_2fa_crud.get_by_user_id(
        session, current_user.id, current_user.organization_id
    )

    has_password = user.password is not None
    two_factor_enabled = user_2fa is not None and user_2fa.is_enabled
    two_factor_policy = "disabled"
    if org_2fa_settings:
        two_factor_policy = org_2fa_settings.two_factor_policy

    # Determine if user can unlink identities
    # Can't unlink if it's the only auth method and user has no password
    identity_count = len(identities)

    # Build identity responses
    identity_responses = []
    for identity in identities:
        is_primary = identity.provider.lower() == user.created_via.value.lower()
        # Can unlink if: has password OR has other identities
        can_unlink = has_password or identity_count > 1

        identity_responses.append(
            UserIdentityResponse(
                id=str(identity.id),
                provider=identity.provider,
                provider_email=identity.provider_email,
                linked_at=identity.created_time or datetime.now(timezone.utc),
                is_primary=is_primary,
                can_unlink=can_unlink,
            )
        )

    # User requires setup if they have no password (SSO-only account)
    requires_setup_for_unlink = not has_password

    return UserIdentitiesResponse(
        identities=identity_responses,
        created_via=user.created_via.value,
        has_password=has_password,
        two_factor_policy=two_factor_policy,
        two_factor_enabled=two_factor_enabled,
        requires_setup_for_unlink=requires_setup_for_unlink,
    )


@router.delete("/{provider}", response_model=UnlinkIdentityResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def unlink_identity(
    provider: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Unlink an SSO identity from the current user (simple unlink).

    This is the simple flow for users who already have a password set.
    Returns 400 if the user has no password - use POST with setup instead.
    """
    # Get full user to check password
    user = await user_crud.get_user_by_id(
        session, current_user.id, current_user.organization_id
    )
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Verify user has a password
    if not user.password:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot unlink identity without a password. Use the setup flow to create a password first.",
            detail_code="identity.password_required",
        )

    # Get all user identities
    identities = await identity_crud.get_by_user_id(
        session, current_user.id, current_user.organization_id
    )

    # Find the identity to unlink
    target_identity = None
    for identity in identities:
        if identity.provider.lower() == provider.lower():
            target_identity = identity
            break

    if not target_identity:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {provider} identity found for this user",
            detail_code="identity.not_found",
        )

    # Soft-delete the identity
    await identity_crud.delete(
        session, str(target_identity.id), current_user.organization_id
    )

    # Log audit event
    await audit_service.log_delete(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="UserIdentity",
        resource_id=str(target_identity.id),
        resource_data={"provider": provider},
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return UnlinkIdentityResponse(
        message=f"{provider.title()} account unlinked successfully",
        message_code="identity.unlinked",
    )


@router.post("/{provider}/unlink-with-setup", response_model=UnlinkWithSetupResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def unlink_identity_with_setup(
    provider: str,
    setup_request: UnlinkWithSetupRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Unlink an SSO identity with account security setup.

    This is the flow for SSO-only users who need to set up a password
    (and optionally 2FA) before unlinking their SSO identity.

    Steps performed:
    1. Validate password complexity
    2. If TOTP provided, verify and enable 2FA
    3. Set password on user
    4. Update created_via to EMAIL
    5. Create EMAIL identity if not exists
    6. Soft-delete the SSO identity
    """
    # Get full user
    user = await user_crud.get_user_by_id(
        session, current_user.id, current_user.organization_id
    )
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Get all user identities
    identities = await identity_crud.get_by_user_id(
        session, current_user.id, current_user.organization_id
    )

    # Find the identity to unlink
    target_identity = None
    for identity in identities:
        if identity.provider.lower() == provider.lower():
            target_identity = identity
            break

    if not target_identity:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {provider} identity found for this user",
            detail_code="identity.not_found",
        )

    # Get 2FA policy
    org_2fa_settings = await org_2fa_crud.get_by_organization_id(
        session, current_user.organization_id
    )
    two_factor_policy = (
        org_2fa_settings.two_factor_policy if org_2fa_settings else "disabled"
    )

    # If mandatory 2FA, require TOTP setup
    if two_factor_policy == "mandatory":
        if not setup_request.totp_secret or not setup_request.totp_code:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-factor authentication is required by your organization",
                detail_code="identity.2fa_required",
            )

    backup_codes = None

    # Handle 2FA setup if provided
    if setup_request.totp_secret and setup_request.totp_code:
        # Check org allows 2FA
        if not org_2fa_settings or not org_2fa_settings.two_factor_allowed:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA is not enabled for this organization",
                detail_code="two_factor.not_allowed",
            )

        # Check user doesn't already have 2FA
        existing_2fa = await user_2fa_crud.get_by_user_id(
            session, current_user.id, current_user.organization_id
        )
        if existing_2fa:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is already set up for this user",
                detail_code="two_factor.already_exists",
            )

        # Verify TOTP code
        if not TwoFactorService.verify_totp(
            setup_request.totp_secret, setup_request.totp_code
        ):
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please try again.",
                detail_code="two_factor.invalid_code",
            )

        # Generate backup codes
        plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=10)
        backup_codes = plain_codes

        # Create 2FA record
        user_2fa = await user_2fa_crud.create(
            session,
            {
                "user_id": current_user.id,
                "secret": setup_request.totp_secret,
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

    # Hash and set password
    hashed_password = hash_password(setup_request.new_password)
    user.password = hashed_password

    # Update created_via to EMAIL
    user.created_via = CreatedVia.EMAIL

    # Check if EMAIL identity already exists
    has_email_identity = any(i.provider.lower() == "email" for i in identities)

    # Create EMAIL identity if not exists
    if not has_email_identity:
        await identity_crud.create(
            session,
            user_id=current_user.id,
            provider="email",
            provider_user_id=current_user.id,  # Use user ID as provider_user_id for email
            organization_id=current_user.organization_id,
            provider_email=user.email,
        )

    # Soft-delete the SSO identity
    await identity_crud.delete(
        session, str(target_identity.id), current_user.organization_id
    )

    await session.commit()

    # Log audit events
    await audit_service.log_update(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="User",
        resource_id=current_user.id,
        old_values={"password": None, "created_via": provider},
        new_values={"password": "[SET]", "created_via": "email"},
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    await audit_service.log_delete(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="UserIdentity",
        resource_id=str(target_identity.id),
        resource_data={"provider": provider, "with_setup": True},
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return UnlinkWithSetupResponse(
        message="Account security configured and identity unlinked successfully",
        message_code="identity.unlinked_with_setup",
        backup_codes=backup_codes,
    )
