"""
Phone verification API endpoints.

Provides endpoints for sending and verifying phone OTP codes.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.logger.logger import Logger
from src.serialisers.phone_verification import (
    SendPhoneOTPRequest,
    SendPhoneOTPResponse,
    VerifyPhoneOTPRequest,
    VerifyPhoneOTPResponse,
)
from src.services.phone_verification import phone_verification_service


router = APIRouter(prefix="/user/me/phone", tags=["phone-verification"])


@router.post("/send-otp", response_model=SendPhoneOTPResponse)
async def send_phone_otp_endpoint(
    http_request: Request,
    request: SendPhoneOTPRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Send an OTP code to the specified phone number for verification.

    Rate limited to 3 requests per hour per phone number.
    """
    try:
        result = await phone_verification_service.send_otp(
            session=session,
            user_id=str(current_user.id),
            phone=str(request.phone),
            organization_id=current_user.organization_id,
        )

        return SendPhoneOTPResponse(
            message=result.get("message", "OTP sent successfully"),
            message_code=get_response_code("phone.otp_sent"),
            verification_id=result["verification_id"],
            expires_at=result["expires_at"],
        )
    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Phone OTP send error: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        error_message = str(e)
        if "Too many OTP requests" in error_message:
            raise create_http_exception(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=error_message,
                detail_code="phone.rate_limit_exceeded",
            )
        elif "already registered" in error_message:
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_message,
                detail_code="phone.already_in_use",
            )
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
            detail_code="phone.verification_failed",
        )


@router.post("/verify-otp", response_model=VerifyPhoneOTPResponse)
async def verify_phone_otp_endpoint(
    http_request: Request,
    request: VerifyPhoneOTPRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Verify the OTP code for a phone number.

    On success, updates the user's phone and sets phone_verified to True.
    Maximum 3 verification attempts per OTP.
    """
    try:
        result = await phone_verification_service.verify_otp(
            session=session,
            user_id=str(current_user.id),
            phone=str(request.phone),
            otp_code=request.otp_code,
            organization_id=current_user.organization_id,
        )

        return VerifyPhoneOTPResponse(
            message=result.get("message", "Phone number verified successfully"),
            message_code=get_response_code("phone.otp_verified"),
            verified=result.get("verified", True),
            phone=result.get("phone"),
        )
    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Phone OTP verify error: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        error_message = str(e)
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
            detail_code="phone.verification_failed",
        )
