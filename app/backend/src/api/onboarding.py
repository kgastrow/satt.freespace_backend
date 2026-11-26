"""
Onboarding API Endpoints.

User-facing endpoints for onboarding workflow including status checking,
step submission, and phone verification.
"""

import json
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.exceptions import create_http_exception
from src.crud import onboarding_review_comment as comment_crud
from src.crud import user_user_type as user_user_type_crud
from src.crud.feature_flag import get_resolved_flags_for_organization
from src.logger.logger import Logger
from src.models.onboarding_review_comment import CommentAuthorType
from src.models.user_user_type import OnboardingStatus
from src.serialisers.onboarding import (
    RespondToChangeRequest,
    ReviewCommentResponse,
    ReviewCommentsResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.onboarding import onboarding_service
from src.services.onboarding_notifications import onboarding_notification_service
from src.services.phone_verification import phone_verification_service


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def check_onboarding_enabled(session: AsyncSession, organization_id: str) -> bool:
    """Check if the user_onboarding feature flag is enabled for the organization."""
    flags = await get_resolved_flags_for_organization(session, organization_id)
    return flags.get("user_onboarding", False)


def require_onboarding_enabled(enabled: bool) -> None:
    """Raise 403 if onboarding is not enabled."""
    if not enabled:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User onboarding is not enabled for this organization",
            detail_code="common.forbidden",
        )


# Request/Response Models
class StartOnboardingRequest(BaseModel):
    """Request body for starting onboarding."""

    user_type_id: str = Field(..., description="UUID of the user type to onboard for")
    model_config = ConfigDict(extra="forbid")


class SubmitStepRequest(BaseModel):
    """Request body for submitting a step."""

    submitted_data: dict = Field(..., description="Data submitted for the step")
    model_config = ConfigDict(extra="forbid")

    @field_validator("submitted_data")
    @classmethod
    def validate_submitted_data_size(cls, v: dict) -> dict:
        """Validate that submitted_data doesn't exceed the maximum allowed size (100KB)."""
        if len(json.dumps(v)) > 102400:
            raise ValueError("submitted_data exceeds maximum allowed size")
        return v


class SendOTPRequest(BaseModel):
    """Request body for sending OTP."""

    phone: str = Field(..., min_length=10, max_length=20, description="Phone number")
    model_config = ConfigDict(extra="forbid")


class VerifyOTPRequest(BaseModel):
    """Request body for verifying OTP."""

    phone: str = Field(..., min_length=10, max_length=20, description="Phone number")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")
    model_config = ConfigDict(extra="forbid")


@router.get("/status")
async def get_onboarding_status(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the current user's onboarding status.

    Returns:
    - status: 'not_started' | 'in_progress' | 'pending_review' | 'approved' | 'rejected'
    - current_step: Current step to complete (null if all complete or not started)
    - progress: List of completed progress records
    - steps: All onboarding steps for the user type
    - user_type: The user's selected user type (null if not started)
    - completed_steps_count: Number of completed steps
    - total_steps_count: Total number of steps
    - all_user_types: List of all user types the user has with their statuses
    - can_add_more_types: Boolean indicating if more user types are available
    """
    from src.crud import onboarding_step as onboarding_step_crud
    from src.crud import user_onboarding_progress as progress_crud
    from src.crud import user_type as user_type_crud
    from src.crud import user_user_type as user_user_type_crud

    # Check if onboarding is enabled for this organization
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    if not is_enabled:
        # Return disabled status - frontend should hide onboarding UI
        return {
            "status": "not_started",
            "current_step": None,
            "progress": [],
            "steps": [],
            "user_type": None,
            "completed_steps_count": 0,
            "total_steps_count": 0,
            "onboarding_enabled": False,
            "all_user_types": [],
            "can_add_more_types": False,
        }

    try:
        # Get user's user_user_type records
        user_user_types = await user_user_type_crud.get_all_for_user(
            session, str(current_user.id), str(current_user.organization_id)
        )

        # Get all active user types to determine if more can be added
        all_active_user_types = await user_type_crud.get_active_user_types(session)
        assigned_type_ids = {str(uut.user_type_id) for uut in user_user_types}
        can_add_more_types = any(
            str(ut.id) not in assigned_type_ids and ut.requires_onboarding
            for ut in all_active_user_types
        )

        # Build all_user_types list with details
        all_user_types_list = []
        for uut in user_user_types:
            ut = await user_type_crud.get_by_id(session, str(uut.user_type_id))
            if ut:
                all_user_types_list.append(
                    {
                        "user_user_type_id": str(uut.id),
                        "user_type_id": str(uut.user_type_id),
                        "user_type_name": ut.name,
                        "user_type_code": ut.code,
                        "onboarding_status": uut.onboarding_status.value,
                        "onboarded_at": (
                            uut.onboarded_at.isoformat() if uut.onboarded_at else None
                        ),
                    }
                )

        # If no user_user_type record exists, user hasn't started onboarding
        if not user_user_types:
            return {
                "status": "not_started",
                "current_step": None,
                "progress": [],
                "steps": [],
                "user_type": None,
                "completed_steps_count": 0,
                "total_steps_count": 0,
                "all_user_types": [],
                "can_add_more_types": can_add_more_types,
            }

        # Select the "active" user_user_type: prefer in_progress, then change_requested, then pending_review, then first
        uut = user_user_types[0]  # Default to first
        for candidate in user_user_types:
            if candidate.onboarding_status.value == "in_progress":
                uut = candidate
                break
            if (
                candidate.onboarding_status.value == "change_requested"
                and uut.onboarding_status.value not in ["in_progress"]
            ):
                uut = candidate
            if (
                candidate.onboarding_status.value == "pending_review"
                and uut.onboarding_status.value
                not in ["in_progress", "change_requested"]
            ):
                uut = candidate

        user_type = await user_type_crud.get_by_id(session, str(uut.user_type_id))

        # Get all steps for this user type
        all_steps = await onboarding_step_crud.get_all_for_user_type(
            session, str(uut.user_type_id)
        )
        active_steps = [s for s in all_steps if s.is_active]

        # Get progress records
        progress_records = await progress_crud.get_progress_for_user_type(
            session, str(uut.id), str(current_user.organization_id)
        )

        # Auto-complete phone verification step if user already has verified phone
        completed_step_ids_set = {str(p.onboarding_step_id) for p in progress_records}

        # Check if user has verified phone by querying the user record
        from src.crud import user as user_crud

        user_record = await user_crud.get_user_by_id(
            session, str(current_user.id), str(current_user.organization_id)
        )

        if user_record and user_record.phone_verified and user_record.phone:
            for step in active_steps:
                if (
                    step.requires_verification
                    and step.code == "phone_verification"
                    and str(step.id) not in completed_step_ids_set
                ):
                    # User has verified phone but step not complete - auto-complete it
                    await onboarding_service.submit_step(
                        session=session,
                        user_id=str(current_user.id),
                        user_user_type_id=str(uut.id),
                        step_id=str(step.id),
                        submitted_data={
                            "phone": user_record.phone,
                            "verified": True,
                            "auto_completed": True,
                        },
                        organization_id=str(current_user.organization_id),
                    )
                    # Refresh progress records after auto-completion
                    progress_records = await progress_crud.get_progress_for_user_type(
                        session, str(uut.id), str(current_user.organization_id)
                    )
                    break  # Only auto-complete one verification step

        # Build progress list
        progress_list = [
            {
                "id": str(p.id),
                "user_id": str(p.user_id),
                "user_user_type_id": str(p.user_user_type_id),
                "onboarding_step_id": str(p.onboarding_step_id),
                "organization_id": str(p.organization_id),
                "submitted_data": p.submitted_data or {},
                "completed_time": (
                    p.completed_time.isoformat() if p.completed_time else None
                ),
                "created_time": p.created_time.isoformat() if p.created_time else None,
            }
            for p in progress_records
        ]

        # Build steps list
        steps_list = [
            {
                "id": str(s.id),
                "user_type_id": str(s.user_type_id),
                "name": s.name,
                "code": s.code,
                "description": s.description,
                "step_order": s.step_order,
                "required_fields": s.required_fields or {},
                "validation_rules": s.validation_rules or {},
                "requires_verification": s.requires_verification,
                "is_active": s.is_active,
            }
            for s in active_steps
        ]

        # Calculate completed steps
        completed_step_ids = {
            str(p.onboarding_step_id) for p in progress_records if p.completed_time
        }
        completed_steps_count = len(completed_step_ids)
        total_steps_count = len(active_steps)

        # Find current (next incomplete) step
        current_step = None
        for step in active_steps:
            if str(step.id) not in completed_step_ids:
                current_step = {
                    "id": str(step.id),
                    "user_type_id": str(step.user_type_id),
                    "name": step.name,
                    "code": step.code,
                    "description": step.description,
                    "step_order": step.step_order,
                    "required_fields": step.required_fields or {},
                    "validation_rules": step.validation_rules or {},
                    "requires_verification": step.requires_verification,
                    "is_active": step.is_active,
                }
                break

        # Build user_type response
        user_type_response = None
        if user_type:
            user_type_response = {
                "id": str(user_type.id),
                "name": user_type.name,
                "code": user_type.code,
                "description": user_type.description,
                "is_active": user_type.is_active,
                "requires_onboarding": user_type.requires_onboarding,
                "requires_manual_review": user_type.requires_manual_review,
                "is_default": user_type.is_default,
                "display_order": user_type.display_order,
                "created_time": (
                    user_type.created_time.isoformat()
                    if user_type.created_time
                    else None
                ),
            }

        return {
            "status": uut.onboarding_status.value,
            "user_user_type_id": str(uut.id),
            "current_step": current_step,
            "progress": progress_list,
            "steps": steps_list,
            "user_type": user_type_response,
            "completed_steps_count": completed_steps_count,
            "total_steps_count": total_steps_count,
            "all_user_types": all_user_types_list,
            "can_add_more_types": can_add_more_types,
        }

    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to get onboarding status for user {current_user.id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again later.",
            detail_code="common.internal_error",
        )


@router.get("/my-user-types")
async def get_my_user_types(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get all user types the current user has onboarded as with their statuses.

    Returns:
    - user_types: List of user types with onboarding status
    - total: Total count of user types
    """
    from src.crud import user_type as user_type_crud
    from src.crud import user_user_type as user_user_type_crud

    # Check if onboarding is enabled for this organization
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    if not is_enabled:
        return {"user_types": [], "total": 0, "onboarding_enabled": False}

    try:
        # Get user's user_user_type records
        user_user_types = await user_user_type_crud.get_all_for_user(
            session, str(current_user.id), str(current_user.organization_id)
        )

        # Build response list with user type details
        user_types_list = []
        for uut in user_user_types:
            ut = await user_type_crud.get_by_id(session, str(uut.user_type_id))
            if ut:
                user_types_list.append(
                    {
                        "user_user_type_id": str(uut.id),
                        "user_type_id": str(uut.user_type_id),
                        "user_type_name": ut.name,
                        "user_type_code": ut.code,
                        "user_type_description": ut.description,
                        "onboarding_status": uut.onboarding_status.value,
                        "onboarded_at": (
                            uut.onboarded_at.isoformat() if uut.onboarded_at else None
                        ),
                        "created_time": (
                            uut.created_time.isoformat() if uut.created_time else None
                        ),
                    }
                )

        return {"user_types": user_types_list, "total": len(user_types_list)}

    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to get user types for user {current_user.id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again later.",
            detail_code="common.internal_error",
        )


@router.post("/start/{user_type_id}", status_code=status.HTTP_201_CREATED)
async def start_onboarding(
    user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Start the onboarding process for a user type.

    Creates a UserUserType association with status 'in_progress' and returns
    the first step to complete.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    try:
        result = await onboarding_service.start_onboarding(
            session,
            str(current_user.id),
            user_type_id,
            str(current_user.organization_id),
        )
        return result

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to start onboarding for user {current_user.id} user_type {user_type_id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again later.",
            detail_code="common.internal_error",
        )


@router.post("/steps/{step_id}/submit")
async def submit_step(
    step_id: str,
    request: SubmitStepRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Submit data for an onboarding step.

    Validates the submitted data and marks the step as complete. If all steps
    are complete, updates the onboarding status accordingly.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    from src.crud import user_user_type as user_user_type_crud

    try:
        # Find the user's active onboarding (in_progress or pending_review)
        user_user_types = await user_user_type_crud.get_all_for_user(
            session, str(current_user.id), str(current_user.organization_id)
        )

        # Filter to find the one that matches the step
        from src.crud import onboarding_step as onboarding_step_crud

        step = await onboarding_step_crud.get_by_id(session, step_id)
        if not step:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Onboarding step with id {step_id} not found",
                detail_code="common.not_found",
            )

        # Find the user_user_type that matches this step's user_type_id
        user_user_type = None
        for uut in user_user_types:
            if str(uut.user_type_id) == str(step.user_type_id):
                user_user_type = uut
                break

        if not user_user_type:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have not started onboarding for this user type",
                detail_code="common.validation_error",
            )

        # Check status allows submission
        if user_user_type.onboarding_status.value not in [
            "in_progress",
            "pending_review",
            "change_requested",
        ]:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot submit step - onboarding status is {user_user_type.onboarding_status.value}",
                detail_code="common.validation_error",
            )

        # If editing during change_requested, set requires_admin_attention
        if user_user_type.onboarding_status == OnboardingStatus.CHANGE_REQUESTED:
            await user_user_type_crud.set_requires_admin_attention(
                session,
                str(user_user_type.id),
                True,
                str(current_user.organization_id),
            )

        result = await onboarding_service.submit_step(
            session,
            str(current_user.id),
            str(user_user_type.id),
            step_id,
            request.submitted_data,
            str(current_user.organization_id),
        )
        return result

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to submit step {step_id} for user {current_user.id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again later.",
            detail_code="common.internal_error",
        )


@router.post("/phone/send-otp")
async def send_otp(
    request: SendOTPRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Send an OTP code to a phone number for verification.

    Enforces rate limiting: max 3 OTP requests per phone per hour.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    try:
        result = await phone_verification_service.send_otp(
            session,
            str(current_user.id),
            request.phone,
            str(current_user.organization_id),
        )
        return result

    except ValueError as e:
        error_message = str(e)
        # Differentiate between rate limiting and phone uniqueness errors
        if "already registered" in error_message:
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_message,
                detail_code="common.validation_error",
            )
        raise create_http_exception(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_message,
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to send OTP for user {current_user.id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again later.",
            detail_code="common.internal_error",
        )


@router.post("/phone/verify")
async def verify_otp(
    request: VerifyOTPRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Verify an OTP code for phone number verification.

    Checks if the OTP is valid, not expired, and hasn't exceeded max attempts (3).
    Updates the user's phone_verified field on success and marks the phone
    verification onboarding step as complete.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    from src.crud import onboarding_step as onboarding_step_crud
    from src.crud import user_user_type as user_user_type_crud

    try:
        # Verify the OTP first
        result = await phone_verification_service.verify_otp(
            session,
            str(current_user.id),
            request.phone,
            request.otp,
            str(current_user.organization_id),
        )

        # Now mark the phone verification onboarding step as complete
        # Find the user's active onboarding
        user_user_types = await user_user_type_crud.get_all_for_user(
            session, str(current_user.id), str(current_user.organization_id)
        )

        if user_user_types:
            # Get the first active onboarding
            user_user_type = user_user_types[0]

            # Find the phone verification step for this user type
            all_steps = await onboarding_step_crud.get_all_for_user_type(
                session, str(user_user_type.user_type_id)
            )

            phone_step = None
            for step in all_steps:
                if step.requires_verification and step.is_active:
                    phone_step = step
                    break

            if phone_step:
                # Mark the step as complete
                await onboarding_service.submit_step(
                    session=session,
                    user_id=str(current_user.id),
                    user_user_type_id=str(user_user_type.id),
                    step_id=str(phone_step.id),
                    submitted_data={"phone": request.phone, "verified": True},
                    organization_id=str(current_user.organization_id),
                )

        return result

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to verify OTP for user {current_user.id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred. Please try again later.",
            detail_code="common.internal_error",
        )


@router.post("/submissions/{user_user_type_id}/respond")
async def respond_to_change_request(
    user_user_type_id: str,
    request: RespondToChangeRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Respond to a change request without resubmitting data.

    Adds a comment to the review thread and sets requires_admin_attention = true.
    Only works when status is 'change_requested'.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    # Get the user_user_type and verify ownership
    user_user_type = await user_user_type_crud.get_by_id(
        session, user_user_type_id, str(current_user.organization_id)
    )

    if not user_user_type:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if str(user_user_type.user_id) != str(current_user.id):
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only respond to your own onboarding submissions",
            detail_code="common.forbidden",
        )

    if user_user_type.onboarding_status != OnboardingStatus.CHANGE_REQUESTED:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot respond - status is '{user_user_type.onboarding_status.value}', expected 'change_requested'",
            detail_code="common.validation_error",
        )

    # Create user comment
    await comment_crud.create(
        session,
        user_user_type_id=user_user_type_id,
        author_id=str(current_user.id),
        author_type=CommentAuthorType.USER,
        comment=request.comment,
        organization_id=str(current_user.organization_id),
    )

    # Set requires_admin_attention
    await user_user_type_crud.set_requires_admin_attention(
        session, user_user_type_id, True, str(current_user.organization_id)
    )

    # Send notification to admins
    await onboarding_notification_service.send_user_responded_notification(
        session,
        user_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
        user_user_type_id=user_user_type_id,
    )

    return {
        "message": "Response submitted successfully",
        "user_user_type_id": user_user_type_id,
    }


@router.post("/submissions/{user_user_type_id}/resubmit")
async def resubmit_for_review(
    user_user_type_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Resubmit onboarding for review after making changes.

    Changes status from 'change_requested' to 'pending_review' and
    sets requires_admin_attention = true.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    # Get the user_user_type and verify ownership
    user_user_type = await user_user_type_crud.get_by_id(
        session, user_user_type_id, str(current_user.organization_id)
    )

    if not user_user_type:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if str(user_user_type.user_id) != str(current_user.id):
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only resubmit your own onboarding submissions",
            detail_code="common.forbidden",
        )

    if user_user_type.onboarding_status != OnboardingStatus.CHANGE_REQUESTED:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resubmit - status is '{user_user_type.onboarding_status.value}', expected 'change_requested'",
            detail_code="common.validation_error",
        )

    # Update status to pending_review with attention flag
    await user_user_type_crud.update_status(
        session,
        user_user_type_id,
        OnboardingStatus.PENDING_REVIEW,
        str(current_user.organization_id),
        requires_admin_attention=True,
    )

    # Send notification to admins
    await onboarding_notification_service.send_user_resubmitted_notification(
        session,
        user_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
        user_user_type_id=user_user_type_id,
    )

    return {
        "message": "Onboarding resubmitted for review",
        "user_user_type_id": user_user_type_id,
        "status": "pending_review",
    }


_WITHDRAWABLE_STATUSES = {
    OnboardingStatus.IN_PROGRESS,
    OnboardingStatus.PENDING_REVIEW,
    OnboardingStatus.CHANGE_REQUESTED,
}


@router.delete("/submissions/{user_user_type_id}")
async def withdraw_onboarding(
    user_user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Withdraw the current user from an in-flight onboarding for a user type.

    Allowed only while the submission is still in motion (in_progress,
    pending_review, change_requested). Soft-deletes the UserUserType row,
    cascading to progress and review comments, and invalidates the user's
    permission cache. The user is then free to start a fresh onboarding for
    the same or a different user type.
    """
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    user_user_type = await user_user_type_crud.get_by_id(
        session, user_user_type_id, str(current_user.organization_id)
    )

    if not user_user_type:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if str(user_user_type.user_id) != str(current_user.id):
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only withdraw from your own onboarding submissions",
            detail_code="common.forbidden",
        )

    prior_status = user_user_type.onboarding_status
    if prior_status not in _WITHDRAWABLE_STATUSES:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot withdraw - onboarding status is '{prior_status.value}'",
            detail_code="common.validation_error",
        )

    from src.crud import user_type as user_type_crud

    user_type = await user_type_crud.get_by_id(
        session, str(user_user_type.user_type_id)
    )
    user_type_name = user_type.name if user_type else ""

    await user_user_type_crud.delete(
        session, user_user_type_id, str(current_user.organization_id)
    )

    await audit_service.log_delete(
        session=session,
        organization_id=str(current_user.organization_id),
        resource_type="UserUserType",
        resource_id=user_user_type_id,
        actor_id=str(current_user.id),
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
        resource_data={
            "user_type_id": str(user_user_type.user_type_id),
            "user_type_name": user_type_name,
            "prior_status": prior_status.value,
            "withdrawn_by": "user",
        },
    )

    if prior_status in (
        OnboardingStatus.PENDING_REVIEW,
        OnboardingStatus.CHANGE_REQUESTED,
    ):
        await onboarding_notification_service.send_user_withdrew_notification(
            session,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
            user_user_type_id=user_user_type_id,
            user_type_name=user_type_name,
            prior_status=prior_status.value,
        )

    return {
        "message": "Onboarding withdrawn",
        "user_user_type_id": user_user_type_id,
        "prior_status": prior_status.value,
    }


@router.get(
    "/submissions/{user_user_type_id}/comments", response_model=ReviewCommentsResponse
)
async def get_my_review_comments(
    user_user_type_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get review comments for the user's own onboarding submission.

    Returns the conversation thread between admin and user during the
    change request flow.
    """
    # Check if onboarding is enabled
    is_enabled = await check_onboarding_enabled(
        session, str(current_user.organization_id)
    )
    require_onboarding_enabled(is_enabled)

    # Get the user_user_type and verify ownership
    user_user_type = await user_user_type_crud.get_by_id(
        session, user_user_type_id, str(current_user.organization_id)
    )

    if not user_user_type:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if str(user_user_type.user_id) != str(current_user.id):
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view comments on your own onboarding submissions",
            detail_code="common.forbidden",
        )

    # Get all comments
    comments = await comment_crud.get_for_submission(
        session, user_user_type_id, str(current_user.organization_id)
    )

    # Build response
    comment_responses = []
    for comment in comments:
        author_name = ""
        if comment.author:
            if comment.author_type == CommentAuthorType.ADMIN:
                # For admin comments, just show "Admin" to users
                author_name = "Admin"
            else:
                author_name = f"{comment.author.first_name or ''} {comment.author.last_name or ''}".strip()
                if not author_name:
                    author_name = "You"

        if comment.created_time:
            comment_responses.append(
                ReviewCommentResponse(
                    id=comment.id,
                    author_id=comment.author_id,
                    author_name=author_name,
                    author_type=comment.author_type.value,
                    comment=comment.comment,
                    created_time=comment.created_time,
                )
            )

    return ReviewCommentsResponse(comments=comment_responses)
