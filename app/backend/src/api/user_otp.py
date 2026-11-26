"""
User OTP API endpoints.
Migrated to FastAPI with async/await patterns.
"""

import traceback
from typing import Annotated
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.response_codes import get_response_code
from src.crud.organization import get_organization_by_slug
from src.crud.user import get_user_by_id, update_user
from src.crud.user_otp import create_otp, verify_otp
from src.logger.logger import Logger
from src.models.user import User
from src.serialisers.auth import AccessTokenResponse
from src.serialisers.user_otp import (
    GenerateOTPResponse,
    SendVerificationEmailRequest,
    SendVerificationEmailResponse,
    VerifyEmailRequest,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from src.services.auth_session import issue_session_for_user
from src.services.notifications import notification_dispatcher


router = APIRouter(prefix="/user-otp", tags=["user-otp"])


@router.post("", response_model=GenerateOTPResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_SEND)
async def generate_otp_endpoint(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Generate OTP for current user (rate limited to prevent abuse)"""
    # Get full user object
    user = await get_user_by_id(session, current_user.id, current_user.organization_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
            detail_code="common.forbidden",
        )

    otp_code = await create_otp(session, user.id, current_user.organization_id)

    # Send OTP via email
    await notification_dispatcher.send_to_user(
        session=session,
        user_id=str(user.id),
        organization_id=current_user.organization_id,
        channel="email",
        content=f"Your verification code is: {otp_code[:3]}-{otp_code[3:]}\n\nThis code will expire in 10 minutes.",
        subject="Your Verification Code",
        is_urgent=True,
    )

    return GenerateOTPResponse(
        message="OTP sent successfully",
        message_code=get_response_code("otp.sent"),
    )


@router.post(
    "/verify", response_model=VerifyOTPResponse, status_code=status.HTTP_202_ACCEPTED
)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def verify_otp_endpoint(
    request: Request,
    verify_data: VerifyOTPRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Verify the OTP code (rate limited to prevent brute force attacks)"""
    try:
        success = await verify_otp(
            session,
            PyUUID(verify_data.user_id),
            verify_data.otp_code,
            verify_data.organization_id,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )

    if not success:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP",
            detail_code="otp.invalid",
        )

    return VerifyOTPResponse(
        message="OTP verification successful",
        message_code=get_response_code("otp.verified"),
    )


@router.post("/verify-email", response_model=AccessTokenResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
async def verify_email_endpoint(
    request: Request,
    response: Response,
    verify_data: VerifyEmailRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Verify user's email using OTP code and return auth tokens (rate limited to prevent brute force attacks)"""
    try:
        # Resolve organization slug to ID
        organization = await get_organization_by_slug(
            session, verify_data.organization_slug
        )
        if not organization:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or OTP",
                detail_code="otp.invalid",
            )

        # Get user by email with organization filtering for tenant isolation
        result = await session.execute(
            select(User).where(
                User.email == verify_data.email,
                User.organization_id == organization.id,
                User.deleted_time.is_(None),
            )
        )
        user = result.scalars().first()

        # Use generic error message to prevent user enumeration
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or OTP",
                detail_code="otp.invalid",
            )

        # Verify OTP
        try:
            success = await verify_otp(
                session, user.id, verify_data.otp_code, str(user.organization_id)
            )
        except ValueError as e:
            # Log the actual error but return generic message
            Logger.warning(
                f"OTP verification failed for email: {verify_data.email}: {e}"
            )
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or OTP",
                detail_code="otp.invalid",
            )

        if not success:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email or OTP",
                detail_code="otp.invalid",
            )

        # Mark the address verified FIRST, and commit, because this endpoint is
        # what MAKES the email verified: the gate below runs with
        # require_email_verified=True and would otherwise reject the very user
        # it just verified. update_user commits, so the verification survives a
        # refusal from the gate -- the address ends up verified either way, only
        # the session is withheld.
        updated_user = await update_user(
            session=session,
            request={"id": user.id, "email": user.email, "email_verified": True},
            organization_id=str(user.organization_id),
        )
        # update_user raises rather than returning None; the fallback keeps the
        # identity-map instance it mutated in place should that ever change.
        user = updated_user if updated_user is not None else user

        # SECURITY: every gate between "we know who this is" and "here is a
        # session" -- organization active, suspension, the second factor --
        # lives in issue_session_for_user, the same helper /auth/login,
        # /auth/verify-2fa and the SSO callback use. This endpoint used to mint
        # the tokens itself with none of those checks, so a SUSPENDED user got
        # a working session and a 2FA-enrolled account was fully compromised by
        # read access to the mailbox alone.
        grant = await issue_session_for_user(
            session,
            user=user,
            organization=organization,
            request=request,
            response=response,
            auth_provider="email",
            require_email_verified=True,
            # This endpoint CANNOT present a TOTP challenge: its only caller is
            # the frontend VerifyEmailPage, whose authSlice matcher
            # (verifyEmailOTP.matchFulfilled) stores payload.access_token
            # unconditionally and has no requires_2fa branch, and the response
            # model here is a bare AccessTokenResponse. So an enrolled user is
            # REFUSED (403 auth.2fa_required) and told to sign in normally,
            # where the challenge is wired -- never signed in without their
            # second factor. If this response ever becomes a union like the SSO
            # callback's and the frontend learns to branch, flip this to True.
            allow_two_factor_challenge=False,
        )

        assert grant.access_token is not None
        return AccessTokenResponse(access_token=grant.access_token)
    except HTTPException:
        raise
    except Exception as e:
        # Log the full exception internally but return generic error
        error_tb = traceback.format_exc()
        Logger.error(f"Error during email verification: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or OTP",
            detail_code="otp.invalid",
        )


@router.post("/send-verification-email", response_model=SendVerificationEmailResponse)
@limiter.limit(settings.RATE_LIMIT_OTP_SEND)
async def send_verification_email_endpoint(
    request: Request,
    send_data: SendVerificationEmailRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Send email verification OTP to user (rate limited to prevent abuse)"""
    try:
        # Resolve organization slug to ID
        organization = await get_organization_by_slug(
            session, send_data.organization_slug
        )
        if not organization:
            # Return success anyway to prevent org enumeration
            return SendVerificationEmailResponse(
                message="If this email exists, a verification code has been sent",
                message_code=get_response_code("user.verification_email_sent"),
            )

        # Get user by email with organization filtering for tenant isolation
        result = await session.execute(
            select(User).where(
                User.email == send_data.email,
                User.organization_id == organization.id,
                User.deleted_time.is_(None),
            )
        )
        user = result.scalars().first()

        # Return success message regardless of whether user exists to prevent enumeration
        if not user:
            return SendVerificationEmailResponse(
                message="If this email exists, a verification code has been sent",
                message_code=get_response_code("user.verification_email_sent"),
            )

        # Generate OTP
        otp_code = await create_otp(session, user.id, str(user.organization_id))

        # Send OTP via email
        await notification_dispatcher.send_to_user(
            session=session,
            user_id=str(user.id),
            organization_id=str(user.organization_id),
            channel="email",
            content=f"Your verification code is: {otp_code[:3]}-{otp_code[3:]}\n\nThis code will expire in 10 minutes.",
            subject="Your Verification Code",
            is_urgent=True,
        )

        return SendVerificationEmailResponse(
            message="If this email exists, a verification code has been sent",
            message_code=get_response_code("user.verification_email_sent"),
        )
    except HTTPException:
        raise
    except Exception as e:
        # Log the full exception internally but return generic success message
        error_tb = traceback.format_exc()
        Logger.error(f"Error sending verification email: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        return SendVerificationEmailResponse(
            message="If this email exists, a verification code has been sent",
            message_code=get_response_code("user.verification_email_sent"),
        )
