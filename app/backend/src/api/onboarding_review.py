"""
Onboarding Review API Endpoints.

Admin endpoints for reviewing pending onboarding submissions, including
approval and rejection workflows.
"""

from datetime import datetime, timezone
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user_admin, get_session
from src.core.exceptions import create_http_exception
from src.crud import onboarding_review_comment as comment_crud
from src.crud import user_onboarding_progress as progress_crud
from src.crud import user_user_type as user_user_type_crud
from src.models.onboarding_review_comment import CommentAuthorType
from src.models.user import User
from src.models.user_type import UserType
from src.models.user_user_type import OnboardingStatus, UserUserType
from src.serialisers.onboarding import (
    RequestChangeRequest,
    ReviewCommentResponse,
    ReviewCommentsResponse,
)
from src.services.onboarding_notifications import onboarding_notification_service


router = APIRouter(prefix="/onboarding/review", tags=["onboarding-review"])


# Request/Response Models
class ApproveRequest(BaseModel):
    """Request body for approving an onboarding submission."""

    expires_at: datetime | None = Field(
        None,
        description="Optional expiry datetime for this user type assignment. "
        "When expired, the user type's permissions will no longer apply.",
    )
    model_config = ConfigDict(extra="forbid")


class RejectRequest(BaseModel):
    """Request body for rejecting an onboarding submission."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="Reason for rejection"
    )
    model_config = ConfigDict(extra="forbid")


class SubmissionProgress(BaseModel):
    """Progress record for a submission step."""

    onboarding_step_id: str
    step_name: str
    submitted_data: dict
    completed_time: str | None
    model_config = ConfigDict(extra="forbid")


class ReviewSubmissionResponse(BaseModel):
    """Response model for a single review submission."""

    id: str
    user_id: str
    user_first_name: str
    user_last_name: str
    user_email: str
    user_type_id: str
    user_type_name: str
    submitted_at: str
    onboarding_status: str
    requires_admin_attention: bool = False
    steps_data: list[SubmissionProgress]
    model_config = ConfigDict(extra="forbid")


class PendingReviewSubmission(BaseModel):
    """Response model for a single pending review submission in the list."""

    id: str
    user_id: str
    user_first_name: str
    user_last_name: str
    user_email: str
    user_type_id: str
    user_type_name: str
    submitted_at: str
    status: str
    requires_admin_attention: bool = False
    model_config = ConfigDict(extra="forbid")


class PendingReviewListResponse(BaseModel):
    """Response model for list of pending reviews.

    Follows the Query DSL standard response format with 'items' key.
    """

    items: list[PendingReviewSubmission] = Field(
        ..., description="List of pending reviews"
    )
    total: int = Field(..., description="Total count matching filters")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Items skipped")
    model_config = ConfigDict(extra="forbid")


class SubmissionListResponse(BaseModel):
    """Response model for list of submissions with any status.

    Follows the Query DSL standard response format with 'items' key.
    """

    items: list[PendingReviewSubmission] = Field(..., description="List of submissions")
    total: int = Field(..., description="Total count matching filters")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Items skipped")
    model_config = ConfigDict(extra="forbid")


@router.get("/submissions", response_model=SubmissionListResponse)
async def get_submissions(
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: (
        Literal["pending_review", "change_requested", "approved", "rejected"] | None
    ) = Query(None, alias="status", description="Filter by onboarding status"),
    search: str | None = Query(None, description="Search by user name or email"),
    user_type_id: str | None = Query(None, description="Filter by user type ID"),
    requires_attention: bool | None = Query(
        None, description="Filter by requires_admin_attention flag"
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    Get onboarding submissions for the current organization with filtering.

    Requires admin role (owner/admin) or super admin.
    Supports filtering by status, searching by name/email, and filtering by user type.
    """
    org_uuid = UUID(current_user.organization_id)

    # Build base query with joins
    query = (
        select(UserUserType, User, UserType)
        .join(User, UserUserType.user_id == User.id)
        .join(UserType, UserUserType.user_type_id == UserType.id)
        .where(
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
            User.deleted_time.is_(None),
        )
    )

    # Filter by status if provided
    if status_filter:
        status_enum = OnboardingStatus(status_filter)
        query = query.where(UserUserType.onboarding_status == status_enum)
    else:
        # Default to showing reviewable statuses (not in_progress or pending)
        query = query.where(
            UserUserType.onboarding_status.in_(
                [
                    OnboardingStatus.PENDING_REVIEW,
                    OnboardingStatus.CHANGE_REQUESTED,
                    OnboardingStatus.APPROVED,
                    OnboardingStatus.REJECTED,
                ]
            )
        )

    # Filter by requires_admin_attention
    if requires_attention is not None:
        query = query.where(UserUserType.requires_admin_attention == requires_attention)

    # Search by name or email
    if search:
        # Escape SQL wildcards to prevent search manipulation
        escaped_search = re.sub(r"([%_])", r"\\\1", search)
        search_term = f"%{escaped_search}%"
        query = query.where(
            or_(
                func.lower(User.first_name).like(func.lower(search_term)),
                func.lower(User.last_name).like(func.lower(search_term)),
                func.lower(User.email).like(func.lower(search_term)),
            )
        )

    # Filter by user type
    if user_type_id:
        try:
            user_type_uuid = UUID(user_type_id)
            query = query.where(UserUserType.user_type_id == user_type_uuid)
        except ValueError:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_type_id format",
                detail_code="common.validation_error",
            )

    # Get total count before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Add ordering and pagination
    query = query.order_by(UserUserType.updated_time.desc()).limit(limit).offset(offset)

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Build response
    submissions = []
    for submission, user, user_type in rows:
        submissions.append(
            PendingReviewSubmission(
                id=str(submission.id),
                user_id=str(submission.user_id),
                user_first_name=user.first_name if user.first_name else "",
                user_last_name=user.last_name if user.last_name else "",
                user_email=user.email,
                user_type_id=str(submission.user_type_id),
                user_type_name=user_type.name if user_type else "",
                status=submission.onboarding_status.value,
                requires_admin_attention=submission.requires_admin_attention,
                submitted_at=(
                    submission.updated_time.isoformat()
                    if submission.updated_time
                    else (
                        submission.created_time.isoformat()
                        if submission.created_time
                        else ""
                    )
                ),
            )
        )

    return SubmissionListResponse(
        items=submissions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/pending", response_model=PendingReviewListResponse)
async def get_pending_reviews(
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    search: str | None = Query(None, description="Search by user name or email"),
    user_type_id: str | None = Query(None, description="Filter by user type ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    Get all pending onboarding reviews for the current organization.

    Requires admin role (owner/admin) or super admin.
    Returns only submissions from the admin's organization.
    """
    org_uuid = UUID(current_user.organization_id)

    # Build base query with joins for efficient filtering
    query = (
        select(UserUserType, User, UserType)
        .join(User, UserUserType.user_id == User.id)
        .join(UserType, UserUserType.user_type_id == UserType.id)
        .where(
            UserUserType.organization_id == org_uuid,
            UserUserType.onboarding_status == OnboardingStatus.PENDING_REVIEW,
            UserUserType.deleted_time.is_(None),
            User.deleted_time.is_(None),
        )
    )

    # Search by name or email
    if search:
        # Escape SQL wildcards to prevent search manipulation
        escaped_search = re.sub(r"([%_])", r"\\\1", search)
        search_term = f"%{escaped_search}%"
        query = query.where(
            or_(
                func.lower(User.first_name).like(func.lower(search_term)),
                func.lower(User.last_name).like(func.lower(search_term)),
                func.lower(User.email).like(func.lower(search_term)),
            )
        )

    # Filter by user type
    if user_type_id:
        try:
            user_type_uuid = UUID(user_type_id)
            query = query.where(UserUserType.user_type_id == user_type_uuid)
        except ValueError:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user_type_id format",
                detail_code="common.validation_error",
            )

    # Get total count before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Add ordering and pagination
    query = query.order_by(UserUserType.updated_time.desc()).limit(limit).offset(offset)

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Build response
    submissions = []
    for submission, user, user_type in rows:
        submissions.append(
            PendingReviewSubmission(
                id=str(submission.id),
                user_id=str(submission.user_id),
                user_first_name=user.first_name if user.first_name else "",
                user_last_name=user.last_name if user.last_name else "",
                user_email=user.email,
                user_type_id=str(submission.user_type_id),
                user_type_name=user_type.name if user_type else "",
                status=submission.onboarding_status.value,
                requires_admin_attention=submission.requires_admin_attention,
                submitted_at=(
                    submission.updated_time.isoformat()
                    if submission.updated_time
                    else (
                        submission.created_time.isoformat()
                        if submission.created_time
                        else ""
                    )
                ),
            )
        )

    return PendingReviewListResponse(
        items=submissions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_user_type_id}", response_model=ReviewSubmissionResponse)
async def get_submission_details(
    user_user_type_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get detailed submission data for a specific onboarding review.

    Requires admin role (owner/admin) or super admin.
    Returns all submitted step data for review.
    """
    org_uuid = UUID(current_user.organization_id)
    uut_uuid = UUID(user_user_type_id)

    # Get the user_user_type record with org filtering
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == uut_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    submission = result.scalars().first()

    if not submission:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    # Fetch user details
    from src.crud.user import get_user_by_id

    user = await get_user_by_id(
        session, str(submission.user_id), str(current_user.organization_id)
    )

    # Fetch user type details
    from src.crud.user_type import get_by_id as get_user_type_by_id

    user_type = await get_user_type_by_id(session, str(submission.user_type_id))

    # Get all progress records with step details
    progress_records = await progress_crud.get_progress_for_user_type(
        session, user_user_type_id, str(current_user.organization_id)
    )

    # Build progress data with submitted information
    progress_list = []
    for progress in progress_records:
        # Get step details
        from src.crud.onboarding_step import get_by_id as get_step_by_id

        step = await get_step_by_id(session, str(progress.onboarding_step_id))

        if step:
            progress_list.append(
                {
                    "onboarding_step_id": str(step.id),
                    "step_name": step.name,
                    "step_order": step.step_order,
                    "submitted_data": progress.submitted_data or {},
                    "completed_time": (
                        progress.completed_time.isoformat()
                        if progress.completed_time
                        else None
                    ),
                }
            )

    # Sort by step order
    progress_list.sort(key=lambda x: x["step_order"])

    # Build progress response objects (without step_order which is internal)
    progress_response = [
        SubmissionProgress(
            onboarding_step_id=p["onboarding_step_id"],
            step_name=p["step_name"],
            submitted_data=p["submitted_data"],
            completed_time=p["completed_time"],
        )
        for p in progress_list
    ]

    return ReviewSubmissionResponse(
        id=str(submission.id),
        user_id=str(submission.user_id),
        user_first_name=user.first_name if user and user.first_name else "",
        user_last_name=user.last_name if user and user.last_name else "",
        user_email=user.email if user else "",
        user_type_id=str(submission.user_type_id),
        user_type_name=user_type.name if user_type else "",
        onboarding_status=submission.onboarding_status.value,
        requires_admin_attention=submission.requires_admin_attention,
        submitted_at=(
            submission.updated_time.isoformat()
            if submission.updated_time
            else (
                submission.created_time.isoformat() if submission.created_time else ""
            )
        ),
        steps_data=progress_response,
    )


@router.post("/{user_user_type_id}/approve")
async def approve_submission(
    user_user_type_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    request: ApproveRequest | None = None,
):
    """
    Approve an onboarding submission.

    Requires admin role (owner/admin) or super admin.
    Sets status to 'approved' and sets onboarded_at timestamp.
    Optionally sets an expiry date for the user type assignment.
    Triggers notification to user.
    """
    org_uuid = UUID(current_user.organization_id)
    uut_uuid = UUID(user_user_type_id)

    # Get the user_user_type record with org filtering
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == uut_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    submission = result.scalars().first()

    if not submission:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if submission.onboarding_status not in (
        OnboardingStatus.PENDING_REVIEW,
        OnboardingStatus.CHANGE_REQUESTED,
    ):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve submission with status '{submission.onboarding_status.value}'",
            detail_code="common.validation_error",
        )

    # Extract expires_at from request if provided
    expires_at = request.expires_at if request else None

    # Update status to approved and clear attention flag
    updated_submission = await user_user_type_crud.update_status(
        session,
        str(submission.id),
        OnboardingStatus.APPROVED,
        str(current_user.organization_id),
        onboarded_at=datetime.now(timezone.utc),
        requires_admin_attention=False,
        expires_at=expires_at,
    )

    # Send approval notification to user
    await onboarding_notification_service.send_approved_notification(
        session,
        user_id=str(submission.user_id),
        organization_id=str(current_user.organization_id),
        user_user_type_id=user_user_type_id,
    )

    return {
        "message": "Onboarding submission approved",
        "user_user_type_id": str(updated_submission.id),
        "status": updated_submission.onboarding_status.value,
        "onboarded_at": (
            updated_submission.onboarded_at.isoformat()
            if updated_submission.onboarded_at
            else None
        ),
        "expires_at": (
            updated_submission.expires_at.isoformat()
            if updated_submission.expires_at
            else None
        ),
    }


@router.post("/{user_user_type_id}/reject")
async def reject_submission(
    user_user_type_id: str,
    request: RejectRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Reject an onboarding submission.

    Requires admin role (owner/admin) or super admin.
    Sets status to 'rejected'.
    Triggers notification to user with rejection reason.
    """
    org_uuid = UUID(current_user.organization_id)
    uut_uuid = UUID(user_user_type_id)

    # Get the user_user_type record with org filtering
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == uut_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    submission = result.scalars().first()

    if not submission:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if submission.onboarding_status not in (
        OnboardingStatus.PENDING_REVIEW,
        OnboardingStatus.CHANGE_REQUESTED,
    ):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject submission with status '{submission.onboarding_status.value}'",
            detail_code="common.validation_error",
        )

    # Update status to rejected and clear attention flag
    updated_submission = await user_user_type_crud.update_status(
        session,
        str(submission.id),
        OnboardingStatus.REJECTED,
        str(current_user.organization_id),
        requires_admin_attention=False,
    )

    # Send rejection notification to user with reason
    await onboarding_notification_service.send_rejected_notification(
        session,
        user_id=str(submission.user_id),
        organization_id=str(current_user.organization_id),
        user_user_type_id=user_user_type_id,
        reason=request.reason,
    )

    return {
        "message": "Onboarding submission rejected",
        "user_user_type_id": str(updated_submission.id),
        "status": updated_submission.onboarding_status.value,
        "reason": request.reason,
    }


@router.post("/{user_user_type_id}/request-change")
async def request_change(
    user_user_type_id: str,
    request: RequestChangeRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Request changes to an onboarding submission.

    Sets status to 'change_requested', creates a review comment with the
    admin's message, and sends notification to the user.

    Requires admin role (owner/admin) or super admin.
    Only works on submissions with status 'pending_review'.
    """
    org_uuid = UUID(current_user.organization_id)
    uut_uuid = UUID(user_user_type_id)

    # Get the user_user_type record with org filtering
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == uut_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    submission = result.scalars().first()

    if not submission:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    if submission.onboarding_status != OnboardingStatus.PENDING_REVIEW:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot request changes on submission with status '{submission.onboarding_status.value}'",
            detail_code="common.validation_error",
        )

    # Update status to change_requested
    updated_submission = await user_user_type_crud.update_status(
        session,
        str(submission.id),
        OnboardingStatus.CHANGE_REQUESTED,
        str(current_user.organization_id),
        requires_admin_attention=False,
    )

    # Create review comment
    await comment_crud.create(
        session,
        user_user_type_id=user_user_type_id,
        author_id=str(current_user.id),
        author_type=CommentAuthorType.ADMIN,
        comment=request.comment,
        organization_id=str(current_user.organization_id),
    )

    # Send change requested notification to user
    await onboarding_notification_service.send_change_requested_notification(
        session,
        user_id=str(submission.user_id),
        organization_id=str(current_user.organization_id),
        user_user_type_id=user_user_type_id,
        comment=request.comment,
    )

    return {
        "message": "Change request sent successfully",
        "user_user_type_id": str(updated_submission.id),
        "status": updated_submission.onboarding_status.value,
    }


@router.get("/{user_user_type_id}/comments", response_model=ReviewCommentsResponse)
async def get_review_comments(
    user_user_type_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get all review comments for an onboarding submission.

    Returns the conversation thread between admin and user during the
    change request flow.

    Requires admin role (owner/admin) or super admin.
    """
    org_uuid = UUID(current_user.organization_id)
    uut_uuid = UUID(user_user_type_id)

    # Verify the submission exists and belongs to this org
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == uut_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    submission = result.scalars().first()

    if not submission:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
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
            author_name = f"{comment.author.first_name or ''} {comment.author.last_name or ''}".strip()
            if not author_name:
                author_name = comment.author.email

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


class AddCommentRequest(BaseModel):
    """Request body for adding a comment to a submission."""

    comment: str = Field(..., min_length=1, max_length=2000)
    model_config = ConfigDict(extra="forbid")


@router.post("/{user_user_type_id}/comments")
async def add_review_comment(
    user_user_type_id: str,
    request: AddCommentRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Add a comment to an onboarding submission review thread.

    Allows admins to continue the conversation with users during the
    change request flow.

    Requires admin role (owner/admin) or super admin.
    """
    org_uuid = UUID(current_user.organization_id)
    uut_uuid = UUID(user_user_type_id)

    # Verify the submission exists and belongs to this org
    result = await session.execute(
        select(UserUserType).where(
            UserUserType.id == uut_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    submission = result.scalars().first()

    if not submission:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding submission not found",
            detail_code="common.not_found",
        )

    # Create the comment
    await comment_crud.create(
        session=session,
        user_user_type_id=user_user_type_id,
        author_id=str(current_user.id),
        author_type=CommentAuthorType.ADMIN,
        comment=request.comment,
        organization_id=str(current_user.organization_id),
    )

    # Clear the requires_admin_attention flag since admin is responding
    await user_user_type_crud.set_requires_admin_attention(
        session, user_user_type_id, False, str(current_user.organization_id)
    )

    return {"message": "Comment added successfully"}
