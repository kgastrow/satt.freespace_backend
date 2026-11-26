"""
Email Change API endpoints.
Multi-step email change verification flow with identity verification and OTP.
"""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.response_codes import get_response_code
from src.core.security import verify_password
from src.crud.email_change_request import (
    cancel_pending_requests,
    create_email_change_request,
    get_active_request_for_user,
    increment_otp_attempts,
    increment_resend_count,
    update_request_status,
)
from src.crud.refresh_token import delete_all_refresh_tokens_for_user
from src.crud.user import get_user_by_email, get_user_by_id
from src.models.email_change_request import EmailChangeStatus
from src.serialisers.email_change import (
    CancelEmailChangeResponse,
    EmailChangeStatusResponse,
    InitiateEmailChangeRequest,
    InitiateEmailChangeResponse,
    ResendOTPRequest,
    ResendOTPResponse,
    VerifyIdentityRequest,
    VerifyIdentityResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.email_change import email_change_service


router = APIRouter(prefix="/users/me/email", tags=["email-change"])

# Rate limiting keys
RATE_LIMIT_INITIATE = "3/day"
RATE_LIMIT_IDENTITY_VERIFY = "5/15minutes"
RATE_LIMIT_OTP_VERIFY = "3/minute"
RATE_LIMIT_RESEND = "3/hour"
RATE_LIMIT_STATUS = "30/minute"
RATE_LIMIT_CANCEL = "10/minute"


def generate_otp() -> str:
    """Generate a 6-digit OTP code."""
    return str(secrets.randbelow(1000000)).zfill(6)


@router.post("/change", response_model=InitiateEmailChangeResponse)
@limiter.limit(RATE_LIMIT_INITIATE)
async def initiate_email_change(
    request: Request,
    change_request: InitiateEmailChangeRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Initiate email change request.
    Validates new email format, not registered, not same as current.
    Rate limited to 3 requests per 24 hours.
    """
    user_id = str(current_user.id)
    org_id = str(current_user.organization_id)

    # Get current user
    user = await get_user_by_id(session, user_id, org_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Check if new email is same as current
    if change_request.new_email.lower() == user.email.lower():
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New email is the same as current email",
            detail_code="email_change.email_same_as_current",
        )

    # Check if new email is already registered
    existing_user = await get_user_by_email(session, change_request.new_email, org_id)
    if existing_user:
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
            detail_code="email_change.email_already_registered",
        )

    # Check for active request
    active_request = await get_active_request_for_user(session, user_id, org_id)
    if active_request:
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="An email change request is already active",
            detail_code="email_change.already_active",
        )

    # Create new email change request
    request_data = {
        "user_id": user_id,
        "old_email": user.email,
        "new_email": change_request.new_email,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    email_change_req = await create_email_change_request(
        session=session, data=request_data, organization_id=org_id
    )

    return InitiateEmailChangeResponse(
        message="Email change request initiated. Please verify your identity.",
        message_code=get_response_code("email_change.request_initiated"),
        request_id=str(email_change_req.id),
        status=email_change_req.status,
    )


@router.post("/change/verify", response_model=VerifyIdentityResponse)
@limiter.limit(RATE_LIMIT_IDENTITY_VERIFY)
async def verify_identity(
    request: Request,
    verify_request: VerifyIdentityRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Submit identity verification (password or 2FA code).
    Rate limited to 5 attempts per 15 minutes.
    """
    user_id = str(current_user.id)
    org_id = str(current_user.organization_id)

    # Get active request
    active_request = await get_active_request_for_user(session, user_id, org_id)
    if not active_request:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active email change request found",
            detail_code="email_change.not_found",
        )

    # Check if request has expired
    expires_at = active_request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        await update_request_status(
            session, str(active_request.id), EmailChangeStatus.EXPIRED, org_id
        )
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email change request has expired",
            detail_code="email_change.request_expired",
        )

    # Check if already verified
    if active_request.status != EmailChangeStatus.PENDING_VERIFICATION.value:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identity verification already completed",
            detail_code="email_change.invalid_status",
        )

    # Get user
    user = await get_user_by_id(session, user_id, org_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Verify identity based on method
    verification_success = False

    if verify_request.verification_method == "password":
        verification_success = verify_password(
            verify_request.verification_value, user.password
        )
        if not verification_success:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid password",
                detail_code="email_change.invalid_password",
            )

    elif verify_request.verification_method in ["totp", "sms_2fa"]:
        # For 2FA, we would validate against the 2FA service
        # For now, this is a placeholder
        raise create_http_exception(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="2FA verification not yet implemented",
            detail_code="common.error",
        )

    # Generate OTP and store hash
    otp_code = generate_otp()
    otp_hash_value = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    # Update request status
    await update_request_status(
        session=session,
        request_id=str(active_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        identity_verified_at=datetime.now(timezone.utc),
        identity_verification_method=verify_request.verification_method,
        otp_hash=otp_hash_value,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Send OTP email to new email address
    await email_change_service.send_otp_to_new_email(
        session=session,
        user_id=user_id,
        organization_id=org_id,
        new_email=active_request.new_email,
        otp_code=otp_code,
        expires_minutes=10,
    )

    return VerifyIdentityResponse(
        message="Identity verified. OTP sent to new email address.",
        message_code=get_response_code("email_change.identity_verified"),
        status=EmailChangeStatus.PENDING_OTP.value,
    )


@router.post("/change/otp", response_model=VerifyOTPResponse)
@limiter.limit(RATE_LIMIT_OTP_VERIFY)
async def verify_otp(
    request: Request,
    otp_request: VerifyOTPRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Submit OTP from new email.
    Rate limited to 3 attempts with max attempts enforcement.
    """
    user_id = str(current_user.id)
    org_id = str(current_user.organization_id)

    # Get active request
    active_request = await get_active_request_for_user(session, user_id, org_id)
    if not active_request:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active email change request found",
            detail_code="email_change.not_found",
        )

    # Check if status is pending_otp
    if active_request.status != EmailChangeStatus.PENDING_OTP.value:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email change request is not in OTP verification stage",
            detail_code="email_change.invalid_status",
        )

    # Check if OTP has expired
    otp_expires_at = active_request.otp_expires_at
    if otp_expires_at.tzinfo is None:
        otp_expires_at = otp_expires_at.replace(tzinfo=timezone.utc)

    if otp_expires_at < datetime.now(timezone.utc):
        await update_request_status(
            session, str(active_request.id), EmailChangeStatus.EXPIRED, org_id
        )
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired",
            detail_code="email_change.otp_expired",
        )

    # Check max attempts
    if active_request.otp_attempts >= 3:
        await update_request_status(
            session, str(active_request.id), EmailChangeStatus.EXPIRED, org_id
        )
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum OTP attempts exceeded",
            detail_code="email_change.max_otp_attempts",
        )

    # Verify OTP
    otp_valid = bcrypt.checkpw(
        otp_request.otp_code.encode(), active_request.otp_hash.encode()
    )

    if not otp_valid:
        # Increment attempts
        await increment_otp_attempts(session, str(active_request.id), org_id)
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code",
            detail_code="email_change.invalid_otp",
        )

    # OTP is valid - update user email
    user = await get_user_by_id(session, user_id, org_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Store old email for notifications and audit
    old_email = user.email
    new_email = active_request.new_email

    # Update user email
    user.email = new_email
    await session.commit()

    # Complete the request
    completion_time = datetime.now(timezone.utc)
    await update_request_status(
        session=session,
        request_id=str(active_request.id),
        status=EmailChangeStatus.COMPLETED,
        organization_id=org_id,
        completed_at=completion_time,
    )

    # Invalidate all refresh tokens for the user (force re-authentication)
    await delete_all_refresh_tokens_for_user(
        session=session,
        user_id=user_id,
        organization_id=org_id,
    )

    # Send confirmation emails
    timestamp_str = completion_time.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Send to old email (security alert)
    await email_change_service.send_change_confirmation_to_old_email(
        session=session,
        user_id=user_id,
        organization_id=org_id,
        old_email=old_email,
        new_email=new_email,
        timestamp=timestamp_str,
    )

    # Send to new email (confirmation)
    await email_change_service.send_change_confirmation_to_new_email(
        session=session,
        user_id=user_id,
        organization_id=org_id,
        new_email=new_email,
        timestamp=timestamp_str,
    )

    # Log audit event
    await audit_service.log_update(
        session=session,
        organization_id=org_id,
        resource_type="User",
        resource_id=user_id,
        old_values={"email": old_email},
        new_values={"email": new_email},
        actor_id=user_id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return VerifyOTPResponse(
        message="Email address successfully changed",
        message_code=get_response_code("email_change.completed"),
        status=EmailChangeStatus.COMPLETED.value,
    )


@router.post("/change/resend", response_model=ResendOTPResponse)
@limiter.limit(RATE_LIMIT_RESEND)
async def resend_otp(
    request: Request,
    resend_request: ResendOTPRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Resend OTP to new email.
    Rate limited to 3 resends per hour.
    """
    user_id = str(current_user.id)
    org_id = str(current_user.organization_id)

    # Get active request
    active_request = await get_active_request_for_user(session, user_id, org_id)
    if not active_request:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active email change request found",
            detail_code="email_change.not_found",
        )

    # Check if status is pending_otp
    if active_request.status != EmailChangeStatus.PENDING_OTP.value:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email change request is not in OTP verification stage",
            detail_code="email_change.invalid_status",
        )

    # Check max resends
    if active_request.otp_resend_count >= 3:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum resend attempts exceeded",
            detail_code="email_change.max_resend_attempts",
        )

    # Generate new OTP
    otp_code = generate_otp()
    otp_hash_value = bcrypt.hashpw(otp_code.encode(), bcrypt.gensalt()).decode()

    # Update request with new OTP
    await update_request_status(
        session=session,
        request_id=str(active_request.id),
        status=EmailChangeStatus.PENDING_OTP,
        organization_id=org_id,
        otp_hash=otp_hash_value,
        otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        otp_attempts=0,
    )

    # Increment resend count
    await increment_resend_count(session, str(active_request.id), org_id)

    # Send OTP email to new email address
    await email_change_service.send_otp_to_new_email(
        session=session,
        user_id=user_id,
        organization_id=org_id,
        new_email=active_request.new_email,
        otp_code=otp_code,
        expires_minutes=10,
    )

    return ResendOTPResponse(
        message="OTP resent to new email address",
        message_code=get_response_code("email_change.otp_sent"),
    )


@router.delete("/change", response_model=CancelEmailChangeResponse)
@limiter.limit(RATE_LIMIT_CANCEL)
async def cancel_email_change(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Cancel pending email change request."""
    user_id = str(current_user.id)
    org_id = str(current_user.organization_id)

    # Cancel all pending requests
    cancelled_count = await cancel_pending_requests(session, user_id, org_id)

    if cancelled_count == 0:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active email change request found",
            detail_code="email_change.not_found",
        )

    return CancelEmailChangeResponse(
        message="Email change request cancelled",
        message_code=get_response_code("email_change.cancelled"),
    )


@router.get("/change/status", response_model=EmailChangeStatusResponse)
@limiter.limit(RATE_LIMIT_STATUS)
async def get_email_change_status(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Check current email change request status."""
    user_id = str(current_user.id)
    org_id = str(current_user.organization_id)

    # Get active request
    active_request = await get_active_request_for_user(session, user_id, org_id)

    if not active_request:
        return EmailChangeStatusResponse(has_active_request=False)

    return EmailChangeStatusResponse(
        has_active_request=True,
        request_id=str(active_request.id),
        old_email=active_request.old_email,
        new_email=active_request.new_email,
        status=active_request.status,
        identity_verified=active_request.identity_verified_at is not None,
        otp_attempts=active_request.otp_attempts,
        otp_resend_count=active_request.otp_resend_count,
        expires_at=active_request.expires_at,
    )
