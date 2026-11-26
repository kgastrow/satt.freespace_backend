"""
Authentication API endpoints.
Migrated to FastAPI with async/await patterns.
"""

import asyncio
from datetime import datetime, timezone
import time
import traceback
from typing import Annotated, Union

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.config import settings
from src.core.cookies import (
    clear_refresh_cookie,
    get_refresh_token_from_cookie,
)
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.response_codes import get_response_code
from src.core.security import (
    create_access_token,
    jwt_decode_options,
    verify_password,
)
from src.crud.refresh_token import (
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    get_refresh_token,
    update_last_active,
)
from src.crud.user import get_user_by_email, get_user_by_id
from src.logger.logger import Logger
from src.middleware.security_metrics import (
    record_2fa_failure,
    record_failed_login,
)
from src.serialisers.auth import (
    AccessTokenResponse,
    CheckEmailRequest,
    CheckEmailResponse,
    LoginRequest,
    LoginResponseWith2FA,
    LogoutAllRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    RefreshTokenResponse,
    Verify2FARequest,
)
from src.services.audit import get_client_ip
from src.services.auth_session import issue_session_for_user
from src.services.brute_force_detector import brute_force_detector


router = APIRouter(prefix="/auth", tags=["auth"])


# Maps a login-gate refusal onto the metric label this endpoint has always used,
# so moving the gates into src.services.auth_session did not change the
# security_metrics time series.
_GATE_FAILURE_REASONS = {
    "user.suspended": "suspended",
    "auth.organization_not_active": "organization_not_active",
}


def _gate_failure_reason(exc: HTTPException) -> str:
    """Metric label for a session-gate refusal."""
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("detail_code")
        if isinstance(code, str):
            return _GATE_FAILURE_REASONS.get(code, code)
    return "login_gate_rejected"


@router.post("/check-email", response_model=CheckEmailResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def check_email_endpoint(
    request: Request,
    check_data: CheckEmailRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Check available authentication methods for an email address.

    Used for two-step login flow:
    1. User enters email
    2. Frontend shows appropriate auth options (password field and/or SSO buttons)

    Returns:
    - exists: Whether an account exists with this email
    - auth_methods: List of available auth methods ('password', 'google', etc.)
    """
    from src.crud.organization import get_organization_by_slug
    from src.crud.user_identity import get_by_user_id as get_identities_by_user_id

    # Get organization
    organization = await get_organization_by_slug(session, check_data.organization_slug)
    if not organization:
        # Don't reveal org doesn't exist - just return no account
        return CheckEmailResponse(exists=False, auth_methods=[])

    if not organization.is_active:
        return CheckEmailResponse(exists=False, auth_methods=[])

    # Get user by email within organization
    user = await get_user_by_email(session, check_data.email, str(organization.id))

    if not user:
        return CheckEmailResponse(exists=False, auth_methods=[])

    # Build list of available auth methods
    auth_methods: list[str] = []

    # Check if password auth is available (user has a password set)
    if user.password is not None:
        auth_methods.append("password")

    # Check for SSO identities
    identities = await get_identities_by_user_id(
        session, str(user.id), str(organization.id)
    )
    for identity in identities:
        if identity.provider not in auth_methods:
            auth_methods.append(identity.provider)

    # If user was created via SSO but doesn't have identity record yet (legacy),
    # add their created_via provider
    if user.created_via.value != "email" and user.created_via.value not in auth_methods:
        auth_methods.append(user.created_via.value)

    return CheckEmailResponse(exists=True, auth_methods=auth_methods)


@router.post("/login", response_model=Union[AccessTokenResponse, LoginResponseWith2FA])
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login_endpoint(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Login endpoint with stricter rate limiting to prevent brute force attacks"""
    Logger.debug(
        f"Login request for email {login_data.email} in organization {login_data.organization_slug}"
    )

    # Get organization first
    from src.crud.organization import get_organization_by_slug

    client_ip = get_client_ip(request) or "unknown"

    # Check if IP is blocked due to brute force
    if await brute_force_detector.is_blocked(client_ip):
        record_failed_login("unknown", client_ip, "ip_blocked")
        raise create_http_exception(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later.",
            detail_code="auth.ip_blocked",
        )

    # Check if account is locked due to repeated failures
    if await brute_force_detector.is_account_locked(
        login_data.email, login_data.organization_slug
    ):
        record_failed_login("unknown", client_ip, "account_locked")
        raise create_http_exception(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to too many failed attempts. Please try again later.",
            detail_code="auth.account_locked",
        )

    organization = await get_organization_by_slug(session, login_data.organization_slug)
    if not organization:
        record_failed_login("unknown", client_ip, "organization_not_found")
        await brute_force_detector.record_failure(client_ip, "login")
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            detail_code="auth.invalid_credentials",
        )

    if not organization.is_active:
        record_failed_login(str(organization.id), client_ip, "organization_not_active")
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not active",
            detail_code="auth.organization_not_active",
        )

    # Get user by email within organization
    user = await get_user_by_email(session, login_data.email, str(organization.id))

    if not user:
        record_failed_login(str(organization.id), client_ip, "user_not_found")
        await brute_force_detector.record_failure(client_ip, "login")
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            detail_code="auth.invalid_credentials",
        )

    # Check if this is an SSO-only account (no password set)
    if user.password is None:
        record_failed_login(str(organization.id), client_ip, "sso_only_account")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses SSO. Please sign in with your SSO provider.",
            detail_code="auth.sso_only_account",
        )

    if not verify_password(login_data.password, user.password):
        record_failed_login(str(organization.id), client_ip, "invalid_credentials")
        threshold_exceeded = await brute_force_detector.record_failure(
            client_ip, "login"
        )
        if threshold_exceeded:
            await brute_force_detector.block_ip(client_ip, reason="brute_force_login")
        await brute_force_detector.record_account_failure(
            login_data.email, login_data.organization_slug
        )
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            detail_code="auth.invalid_credentials",
        )

    # Every gate that stands between "the password was right" and "here is a
    # session" -- suspension, organization active, the second factor -- lives in
    # issue_session_for_user, which the SSO paths also go through. Keeping them
    # in one place is what stops a new login path from quietly skipping one
    # (the SSO callback used to skip all of them).
    try:
        grant = await issue_session_for_user(
            session,
            user=user,
            organization=organization,
            request=request,
            # The refresh cookie is set only when a full session is minted,
            # never alongside a 2FA challenge.
            response=response,
            auth_provider="email",
        )
    except HTTPException as exc:
        record_failed_login(str(organization.id), client_ip, _gate_failure_reason(exc))
        raise

    if grant.requires_2fa:
        assert grant.two_factor_token is not None
        return LoginResponseWith2FA(
            requires_2fa=True,
            two_factor_token=grant.two_factor_token,
        )

    # Full session issued - clear brute force failures on successful login
    await brute_force_detector.clear_failures(client_ip)
    await brute_force_detector.clear_account_failures(
        login_data.email, login_data.organization_slug
    )

    # SECURITY FIX: Use Logger instead of print (VULN-auth-005)
    Logger.info(
        f"Login successful: user={login_data.email}, org={login_data.organization_slug}"
    )

    assert grant.access_token is not None
    return AccessTokenResponse(access_token=grant.access_token)


@router.post("/verify-2fa", response_model=AccessTokenResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def verify_2fa_endpoint(
    request: Request,
    response: Response,
    verify_data: Verify2FARequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Verify 2FA code (TOTP or backup code) and complete login."""
    client_ip = get_client_ip(request) or "unknown"

    # Decode and validate temporary 2FA token
    try:
        payload = jwt.decode(
            verify_data.two_factor_token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options=jwt_decode_options(),
        )
        if payload.get("purpose") != "2fa_verification":
            record_2fa_failure("unknown", "invalid_token_purpose")
            raise create_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA token",
                detail_code="auth.invalid_2fa_token",
            )
        user_id = payload.get("user_id")
        organization_id = payload.get("organization_id")
    except jwt.ExpiredSignatureError:
        record_2fa_failure("unknown", "token_expired")
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA token expired",
            detail_code="auth.2fa_token_expired",
        )
    except jwt.InvalidTokenError:
        record_2fa_failure("unknown", "invalid_token")
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA token",
            detail_code="auth.invalid_2fa_token",
        )

    if not user_id or not organization_id:
        record_2fa_failure("unknown", "missing_token_claims")
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA token",
            detail_code="auth.invalid_2fa_token",
        )

    # Check if user is locked out due to 2FA failures
    if await brute_force_detector.is_2fa_locked(user_id):
        ttl = await brute_force_detector.get_2fa_lockout_ttl(user_id)
        record_2fa_failure(organization_id, "2fa_locked")
        raise create_http_exception(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed 2FA attempts. Please try again in {ttl // 60} minutes.",
            detail_code="auth.2fa_locked",
        )

    # Get user 2FA record
    from src.crud.user_two_factor import (
        get_backup_codes,
        get_by_user_id,
        get_decrypted_secret,
        mark_backup_code_used,
    )
    from src.services.two_factor import TwoFactorService

    user_2fa = await get_by_user_id(session, user_id, organization_id)
    if not user_2fa or not user_2fa.is_enabled:
        record_2fa_failure(organization_id, "2fa_not_enabled")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA not enabled for this user",
            detail_code="auth.2fa_not_enabled",
        )

    code = verify_data.code.strip()
    verified = False

    # Try TOTP first (6 digits)
    if len(code) == 6 and code.isdigit():
        # Get decrypted secret for TOTP verification
        decrypted_secret = await get_decrypted_secret(session, user_id, organization_id)
        if decrypted_secret:
            verified = TwoFactorService.verify_totp(decrypted_secret, code)

    # Try backup code if TOTP fails (8 characters)
    if not verified and len(code) == 8:
        backup_codes = await get_backup_codes(session, user_id, organization_id)
        for backup_code in backup_codes:
            # Skip already used codes
            if backup_code.used_at is not None:
                continue

            if TwoFactorService.verify_backup_code(code, backup_code.code):
                # Mark backup code as used
                await mark_backup_code_used(session, str(backup_code.id))
                verified = True
                break

    if not verified:
        record_2fa_failure(organization_id, "invalid_code")
        # Track IP-based failures
        threshold_exceeded = await brute_force_detector.record_failure(client_ip, "2fa")
        if threshold_exceeded:
            await brute_force_detector.block_ip(client_ip, reason="brute_force_2fa")
        # Track per-user 2FA failures for account-level lockout
        await brute_force_detector.record_2fa_failure(user_id)
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code",
            detail_code="auth.invalid_2fa_code",
        )

    # SECURITY FIX: Check if user is suspended before issuing tokens (VULN-auth-002)
    # -- now enforced centrally by issue_session_for_user below.
    from src.crud.organization import get_organization_by_id

    user = await get_user_by_id(session, user_id, organization_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA token",
            detail_code="auth.invalid_2fa_token",
        )

    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA token",
            detail_code="auth.invalid_2fa_token",
        )

    # 2FA verified - run the same gate as /auth/login (suspension, org active)
    # and mint there. two_factor_satisfied: this endpoint has just checked the
    # second factor itself, so the gate must not ask for it again.
    grant = await issue_session_for_user(
        session,
        user=user,
        organization=organization,
        request=request,
        response=response,
        auth_provider="email",
        two_factor_satisfied=True,
    )

    # Clear brute force failures on successful verification
    await brute_force_detector.clear_failures(client_ip)
    await brute_force_detector.clear_2fa_failures(user_id)

    # SECURITY FIX: Use Logger instead of print (VULN-auth-005)
    Logger.info(f"2FA verified: user_id={user_id}, org_id={organization_id}")

    assert grant.access_token is not None
    return AccessTokenResponse(access_token=grant.access_token)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_endpoint(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
):
    """Refresh access token using refresh token from httpOnly cookie"""
    cookie_token = get_refresh_token_from_cookie(request)
    if not cookie_token:
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
            detail_code="auth.invalid_token",
        )

    stored_token = await get_refresh_token(session, cookie_token)

    now = datetime.now(timezone.utc)
    if not stored_token:
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            detail_code="auth.invalid_token",
        )

    # For SQLite testing, convert to naive datetime for comparison
    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        raise create_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            detail_code="auth.token_expired",
        )

    # Validate organization is still active
    from src.crud.organization import get_organization_by_id

    organization = await get_organization_by_id(
        session, str(stored_token.organization_id)
    )
    if not organization or not organization.is_active:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not active",
            detail_code="auth.organization_not_active",
        )

    # Check if user is suspended
    from src.models.user import SuspensionStatus

    user = await get_user_by_id(
        session, str(stored_token.user_id), str(stored_token.organization_id)
    )
    if user and user.suspension_status == SuspensionStatus.SUSPENDED:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact your administrator.",
            detail_code="user.suspended",
        )

    new_access_token = create_access_token(
        user_id=str(stored_token.user_id),
        organization_id=str(stored_token.organization_id),
    )

    # Update last active timestamp for session tracking
    await update_last_active(session, cookie_token)

    return RefreshTokenResponse(access_token=new_access_token)


@router.post("/logout")
async def logout_endpoint(
    request: Request,
    response: Response,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Logout endpoint - invalidates refresh token from httpOnly cookie"""
    organization_id = current_user.organization_id

    cookie_token = get_refresh_token_from_cookie(request)
    if cookie_token:
        await delete_refresh_token(session, cookie_token, organization_id)

    clear_refresh_cookie(response)

    # SECURITY FIX: Use Logger instead of print (VULN-auth-005)
    Logger.info(f"Logout: user_id={current_user.id}, org_id={organization_id}")
    return {
        "message": "Logged out successfully",
        "message_code": get_response_code("auth.logout_success"),
    }


@router.post("/logout/all")
async def logout_all_endpoint(
    request: Request,
    response: Response,
    logout_data: LogoutAllRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Logs out a user from all devices by deleting all refresh tokens.

    Authorization:
    - Users can only log out themselves
    - User admins can log out any user in their organization
    - Super admins can log out any user
    """
    organization_id = current_user.organization_id
    target_user_id = logout_data.user_id

    # Authorization check: user can only log out themselves unless they're admin
    if target_user_id != current_user.id:
        # SECURITY FIX: Validate that target user exists in the current organization (VULN-auth-004)
        target_user = await get_user_by_id(session, target_user_id, organization_id)
        if not target_user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in your organization",
                detail_code="user.not_found",
            )

        # Must be super admin or have admin role to log out other users
        has_admin_role = current_user.has_role("owner") or current_user.has_role(
            "admin"
        )
        if not current_user.is_admin and not has_admin_role:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only log out yourself. Admin access required to log out other users.",
                detail_code="auth.admin_required",
            )

    await delete_all_refresh_tokens_for_user(session, target_user_id, organization_id)

    # Invalidate JWT cache for the logged out user
    from src.services.cache import cache_service

    await cache_service.invalidate_jwt_for_user(target_user_id)

    # Clear the current user's refresh cookie
    clear_refresh_cookie(response)

    return {
        "message": "Logged out from all devices",
        "message_code": get_response_code("auth.all_sessions_logged_out"),
    }


@router.post("/password-reset/request")
@limiter.limit(settings.RATE_LIMIT_OTP_SEND)
async def password_reset_request_endpoint(
    request: Request,
    reset_data: PasswordResetRequestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Request a password reset email.

    This endpoint is public (no authentication required) but rate-limited.
    For security, always returns success message even if email doesn't exist.

    - **email**: Email address of the account
    - **organization_slug**: Organization identifier

    Rate limited to 1 request per minute per IP, plus IP-based abuse detection.
    """
    from src.crud.organization import get_organization_by_slug
    from src.crud.user_otp import create_password_reset_token
    from src.services.tasks import task_queue

    # Constant-time response to prevent user enumeration via timing analysis
    MINIMUM_RESPONSE_TIME = 0.3  # 300ms floor
    start_time = time.monotonic()
    response_msg = (
        "If an account exists with this email, a password reset link has been sent."
    )

    client_ip = get_client_ip(request) or "unknown"

    # Check IP-based password reset rate limiting
    if await brute_force_detector.record_password_reset_request(client_ip):
        # IP has exceeded password reset threshold - silently return success
        # to prevent enumeration but don't actually send email
        Logger.warning(
            f"Password reset blocked for IP {client_ip} - threshold exceeded"
        )
        elapsed = time.monotonic() - start_time
        if elapsed < MINIMUM_RESPONSE_TIME:
            await asyncio.sleep(MINIMUM_RESPONSE_TIME - elapsed)
        return {"message": response_msg}

    Logger.debug(
        f"Password reset requested for {reset_data.email} in {reset_data.organization_slug}"
    )

    # Get organization - don't reveal if it doesn't exist
    organization = await get_organization_by_slug(session, reset_data.organization_slug)

    if organization:
        # Get user - don't reveal if they don't exist
        user = await get_user_by_email(session, reset_data.email, str(organization.id))

        if user and user.email_verified:
            # Generate password reset token
            reset_token = await create_password_reset_token(
                session=session, user_id=user.id, organization_id=str(organization.id)
            )

            # Build reset URL
            # SPA route (app/frontend/src/router.tsx), so the FRONTEND origin.
            reset_url = f"{settings.PUBLIC_URL_FRONTEND}/reset-password?token={reset_token}&org={reset_data.organization_slug}"

            # Queue email sending
            await task_queue.enqueue_password_reset_email(
                to=user.email,
                reset_token=reset_token,
                reset_url=reset_url,
                organization_id=str(organization.id),
            )

            Logger.info(f"Password reset email queued for {reset_data.email}")

    # Normalize response time to prevent timing-based user enumeration
    elapsed = time.monotonic() - start_time
    if elapsed < MINIMUM_RESPONSE_TIME:
        await asyncio.sleep(MINIMUM_RESPONSE_TIME - elapsed)

    return {"message": response_msg}


@router.post("/password-reset/confirm")
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def password_reset_confirm_endpoint(
    request: Request,
    confirm_data: PasswordResetConfirmRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Confirm password reset with token and new password.

    - **token**: Password reset token from email
    - **new_password**: New password (minimum 8 characters)
    - **organization_slug**: Organization identifier

    Rate limited to 5 requests per minute per IP.
    """
    from src.core.security import hash_password
    from src.crud.organization import get_organization_by_slug
    from src.crud.user_otp import verify_password_reset_token

    Logger.debug(
        f"Password reset confirmation attempt for org {confirm_data.organization_slug}"
    )

    # SECURITY FIX: Use create_http_exception consistently (VULN-auth-006)
    # Validate password length
    if len(confirm_data.new_password) < 8:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
            detail_code="auth.password_too_short",
        )

    # Get organization
    organization = await get_organization_by_slug(
        session, confirm_data.organization_slug
    )
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
            detail_code="auth.password_reset_token_invalid",
        )

    try:
        # Verify token and get user_id (this marks the token as used)
        user_id = await verify_password_reset_token(
            session=session,
            token=confirm_data.token,
            organization_id=str(organization.id),
        )
    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Password reset token verification failed: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
            detail_code="auth.password_reset_token_expired",
        )

    # Get user and update password
    user = await get_user_by_id(session, str(user_id), str(organization.id))
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password reset token",
            detail_code="auth.password_reset_token_invalid",
        )

    # Update password
    user.password = hash_password(confirm_data.new_password)
    await session.commit()

    # Invalidate all existing refresh tokens for security
    await delete_all_refresh_tokens_for_user(
        session, str(user_id), str(organization.id)
    )

    # Invalidate JWT cache
    from src.services.cache import cache_service

    await cache_service.invalidate_jwt_for_user(str(user_id))

    Logger.info(f"Password reset completed for user {user_id}")

    return {
        "message": "Password has been reset successfully. You can now log in with your new password.",
        "message_code": get_response_code("auth.password_reset_success"),
    }
