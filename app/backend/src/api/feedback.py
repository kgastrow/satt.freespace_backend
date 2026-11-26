"""
Feedback API endpoints.

Allows authenticated users to submit feedback (bug reports, suggestions, complaints, praise, other).
Admins with feedback:view can view all feedback, feedback:respond can respond, feedback:delete can delete.
Users can view their own feedback submissions.
"""

import traceback
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.core.query_params import get_pagination_params, parse_filters, parse_sort
from src.crud.feedback import (
    FEEDBACK_FILTER_FIELDS,
    FEEDBACK_SORT_FIELDS,
    create_feedback,
    create_feedback_attachment,
    create_feedback_reply,
    get_feedback_by_id,
    get_feedbacks_list,
    get_user_feedbacks,
    mark_feedback_viewed,
    mark_feedback_viewed_by_admin,
    soft_delete_feedback,
    update_feedback,
)
from src.crud.user_notification import create_user_notification
from src.logger.logger import Logger
from src.serialisers.feedback import (
    CreateFeedbackReplyRequest,
    CreateFeedbackReplyResponse,
    CreateFeedbackRequest,
    CreateFeedbackResponse,
    DeleteFeedbackResponse,
    FeedbackAttachmentRequest,
    FeedbackAttachmentResponse,
    FeedbackListResponse,
    FeedbackReplyResponse,
    FeedbackResponse,
    MarkFeedbackViewedResponse,
    UpdateFeedbackRequest,
    UpdateFeedbackResponse,
)


router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "", response_model=CreateFeedbackResponse, status_code=status.HTTP_201_CREATED
)
async def submit_feedback_endpoint(
    http_request: Request,
    request: CreateFeedbackRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Submit feedback.

    Any authenticated user can submit feedback.
    Auto-captures context fields (page_url, user_agent, screen_resolution) if provided.
    Returns the created feedback with ID.
    """
    try:
        feedback_data = request.model_dump()
        feedback = await create_feedback(
            session=session,
            feedback_data=feedback_data,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
        )

        return CreateFeedbackResponse(
            message="Feedback submitted successfully",
            message_code="feedback.created",
            feedback=FeedbackResponse.from_orm_feedback(feedback),
        )
    except IntegrityError as e:
        Logger.warning(f"Integrity error creating feedback: {e}")
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback could not be created due to a conflict",
            detail_code="feedback.conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating feedback: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating feedback",
            detail_code="feedback.database_error",
        )


@router.get("/me", response_model=FeedbackListResponse)
async def get_my_feedback_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Get current user's own feedback submissions.

    Returns all feedback submitted by the authenticated user.
    Supports pagination via limit and offset.
    """
    feedbacks, total = await get_user_feedbacks(
        session=session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    return FeedbackListResponse(
        items=[FeedbackResponse.from_orm_feedback(f) for f in feedbacks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=FeedbackListResponse)
async def list_feedback_endpoint(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("feedback:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    organization_id: Optional[str] = Query(
        None, description="Filter by organization (super admin only)"
    ),
):
    """
    List all feedback for the organization with SDL filtering and sorting.

    Requires feedback:view permission.

    **Filter examples:**
    - `filter[type]=bug` - exact match by type
    - `filter[status]=new` - exact match by status
    - `filter[status][in]=new,in_review` - value in list
    - `filter[rating][gte]=3` - minimum rating
    - `filter[rating][lte]=5` - maximum rating
    - `filter[created_time][gte]=2024-01-01T00:00:00Z` - filter from date
    - `filter[created_time][lte]=2024-12-31T23:59:59Z` - filter to date

    **Sort:** `sort=created_time:desc` or `sort=type:asc,created_time:desc`

    **Pagination:** `limit=50&offset=0`

    Super admins can filter by organization_id to view feedback across organizations.
    """
    # Parse SDL parameters from request
    filters = parse_filters(request, allowed_fields=FEEDBACK_FILTER_FIELDS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=FEEDBACK_SORT_FIELDS,
        default_sort="created_time:desc",
    )
    limit, offset = get_pagination_params(request, default_limit=100, max_limit=1000)

    # Determine the organization_id to use for filtering
    # Only system super admins (is_admin=True) can query across organizations
    # Regular organization admins with feedback:view permission can only view their own org
    filter_org_id = current_user.organization_id
    if organization_id:
        # Cross-org access requires super admin (is_admin=True on User model)
        if not current_user.is_admin:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins can view feedback from other organizations",
                detail_code="feedback.cross_org_forbidden",
            )
        filter_org_id = organization_id

    feedbacks, total = await get_feedbacks_list(
        session=session,
        organization_id=filter_org_id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    return FeedbackListResponse(
        items=[FeedbackResponse.from_orm_feedback(f) for f in feedbacks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback_endpoint(
    feedback_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get feedback by ID.

    Users can access their own feedback.
    Users with feedback:view permission can access any feedback in their organization.
    """
    feedback = await get_feedback_by_id(
        session=session,
        feedback_id=feedback_id,
        organization_id=current_user.organization_id,
    )

    if not feedback:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
            detail_code="feedback.not_found",
        )

    # Check authorization: user can view own feedback OR has feedback:view permission
    from src.crud.role_permission import user_has_permission

    has_view_permission = current_user.is_admin or await user_has_permission(
        session, current_user.id, current_user.organization_id, "feedback:view"
    )

    if str(feedback.user_id) != current_user.id and not has_view_permission:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this feedback",
            detail_code="feedback.forbidden",
        )

    # Load attachments and user relationships
    await session.refresh(feedback, ["attachments", "user"])

    return FeedbackResponse.from_orm_feedback(feedback)


@router.patch("/{feedback_id}", response_model=UpdateFeedbackResponse)
async def update_feedback_endpoint(
    feedback_id: str,
    request: UpdateFeedbackRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("feedback:respond"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update feedback (admin only).

    Requires feedback:respond permission.
    Can update status, admin_notes (internal), and admin_response (visible to user).
    Tracks responded_by/responded_at and resolved_by/resolved_at automatically.
    Sends notification to user when admin responds or resolves the feedback.
    """
    # Get the feedback before update to check if response is new
    existing_feedback = await get_feedback_by_id(
        session=session,
        feedback_id=feedback_id,
        organization_id=current_user.organization_id,
        load_relationships=False,
    )

    if not existing_feedback:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
            detail_code="feedback.not_found",
        )

    had_response_before = bool(existing_feedback.admin_response)
    was_resolved_before = existing_feedback.status == "resolved"

    feedback = await update_feedback(
        session=session,
        feedback_id=feedback_id,
        organization_id=current_user.organization_id,
        feedback_data=request.model_dump(exclude_unset=True),
        updated_by_id=current_user.id,
    )

    if not feedback:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
            detail_code="feedback.not_found",
        )

    # Send notification to user if admin added a response or resolved the feedback
    request_data = request.model_dump(exclude_unset=True)
    should_notify = False
    notification_title = ""
    notification_body = ""

    # Notify if new admin_response was added
    if (
        "admin_response" in request_data
        and request_data["admin_response"]
        and not had_response_before
    ):
        should_notify = True
        notification_title = "Feedback Response Received"
        notification_body = (
            f"Your feedback '{feedback.subject}' has received a response from our team."
        )

    # Notify if status changed to resolved
    elif (
        "status" in request_data
        and request_data["status"] == "resolved"
        and not was_resolved_before
    ):
        should_notify = True
        notification_title = "Feedback Resolved"
        notification_body = (
            f"Your feedback '{feedback.subject}' has been marked as resolved."
        )

    if should_notify:
        try:
            await create_user_notification(
                session=session,
                organization_id=current_user.organization_id,
                user_id=str(feedback.user_id),
                title=notification_title,
                body=notification_body,
                link="/settings/support/feedback",
            )
        except Exception as e:
            # Log but don't fail the request if notification fails
            Logger.warning(
                f"Failed to create notification for feedback {feedback_id}: {e}"
            )

    # Load attachments and user
    await session.refresh(feedback, ["attachments", "user"])

    return UpdateFeedbackResponse(
        message="Feedback updated successfully",
        message_code="feedback.updated",
        feedback=FeedbackResponse.from_orm_feedback(feedback),
    )


@router.delete("/{feedback_id}", response_model=DeleteFeedbackResponse)
async def delete_feedback_endpoint(
    feedback_id: str,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("feedback:delete"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete feedback.

    Requires feedback:delete permission (typically Org Owner or Super Admin).
    Uses soft delete (sets deleted_time).
    """
    feedback = await soft_delete_feedback(
        session=session,
        feedback_id=feedback_id,
        organization_id=current_user.organization_id,
    )

    if not feedback:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
            detail_code="feedback.not_found",
        )

    return DeleteFeedbackResponse(
        message="Feedback deleted successfully",
        message_code="feedback.deleted",
        feedback_id=feedback.id,
    )


@router.post(
    "/{feedback_id}/attachments",
    response_model=FeedbackAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback_attachment_endpoint(
    feedback_id: str,
    http_request: Request,
    request: FeedbackAttachmentRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a feedback attachment.

    Users can attach files to their own feedback.
    Requires that the feedback exists and belongs to the user's organization.
    File upload is handled separately via the file upload endpoint.
    This endpoint just records the attachment metadata.
    """
    try:
        # Verify feedback exists and user has access
        feedback = await get_feedback_by_id(
            session=session,
            feedback_id=feedback_id,
            organization_id=current_user.organization_id,
        )

        if not feedback:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
                detail_code="feedback.not_found",
            )

        # Check authorization: user can attach to own feedback OR has feedback:respond permission
        from src.crud.role_permission import user_has_permission

        has_respond_permission = current_user.is_admin or await user_has_permission(
            session, current_user.id, current_user.organization_id, "feedback:respond"
        )

        if str(feedback.user_id) != current_user.id and not has_respond_permission:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to attach files to this feedback",
                detail_code="feedback.forbidden",
            )

        attachment = await create_feedback_attachment(
            session=session,
            feedback_id=feedback_id,
            organization_id=current_user.organization_id,
            file_path=request.file_path,
            file_type=request.file_type,
            file_size_bytes=request.file_size_bytes,
        )

        return FeedbackAttachmentResponse.model_validate(attachment)

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="feedback.attachment_error",
        )
    except IntegrityError as e:
        Logger.warning(f"Integrity error creating feedback attachment: {e}")
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment could not be created due to a conflict",
            detail_code="feedback.attachment_conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating feedback attachment: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating attachment",
            detail_code="feedback.database_error",
        )


@router.post(
    "/{feedback_id}/replies",
    response_model=CreateFeedbackReplyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback_reply_endpoint(
    feedback_id: str,
    http_request: Request,
    request: CreateFeedbackReplyRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a reply to a feedback item.

    Users can reply to their own feedback.
    Users with feedback:respond permission can reply to any feedback in their organization.
    Sends notification to the other party when a reply is created.
    """
    try:
        # Get the feedback to check authorization
        feedback = await get_feedback_by_id(
            session=session,
            feedback_id=feedback_id,
            organization_id=current_user.organization_id,
            load_relationships=False,
        )

        if not feedback:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
                detail_code="feedback.not_found",
            )

        # Check authorization and determine if this is an admin reply
        from src.crud.role_permission import user_has_permission

        has_respond_permission = current_user.is_admin or await user_has_permission(
            session, current_user.id, current_user.organization_id, "feedback:respond"
        )

        is_owner = str(feedback.user_id) == current_user.id
        is_admin_reply = has_respond_permission and not is_owner

        # User must be owner OR have respond permission
        if not is_owner and not has_respond_permission:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to reply to this feedback",
                detail_code="feedback.forbidden",
            )

        reply = await create_feedback_reply(
            session=session,
            feedback_id=feedback_id,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            message=request.message,
            is_admin_reply=is_admin_reply,
        )

        # Send notification to the other party
        try:
            if is_admin_reply:
                # Admin replied, notify the feedback owner
                await create_user_notification(
                    session=session,
                    organization_id=current_user.organization_id,
                    user_id=str(feedback.user_id),
                    title="New Reply on Your Feedback",
                    body=f"Your feedback '{feedback.subject}' has received a new reply.",
                    link="/settings/support/feedback",
                )
            else:
                # User replied, this is informational - admins will see it in the dashboard
                # We could optionally notify admins here if needed
                pass
        except Exception as e:
            Logger.warning(f"Failed to create notification for feedback reply: {e}")

        return CreateFeedbackReplyResponse(
            message="Reply created successfully",
            message_code="feedback.reply_created",
            reply=FeedbackReplyResponse.from_orm_reply(reply),
        )

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="feedback.reply_error",
        )
    except IntegrityError as e:
        Logger.warning(f"Integrity error creating feedback reply: {e}")
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reply could not be created due to a conflict",
            detail_code="feedback.reply_conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating feedback reply: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating reply",
            detail_code="feedback.database_error",
        )


@router.post("/{feedback_id}/mark-viewed", response_model=MarkFeedbackViewedResponse)
async def mark_feedback_viewed_endpoint(
    feedback_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Mark a feedback as viewed by the owner.

    Updates user_last_viewed_at to clear the "new reply" indicator.
    Only the feedback owner can mark it as viewed.
    """
    feedback = await mark_feedback_viewed(
        session=session,
        feedback_id=feedback_id,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )

    if not feedback:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found or you are not the owner",
            detail_code="feedback.not_found",
        )

    return MarkFeedbackViewedResponse(
        message="Feedback marked as viewed",
        message_code="feedback.marked_viewed",
        feedback_id=feedback.id,
        viewed_at=feedback.user_last_viewed_at,
    )


@router.post(
    "/{feedback_id}/mark-viewed-admin", response_model=MarkFeedbackViewedResponse
)
async def mark_feedback_viewed_by_admin_endpoint(
    feedback_id: str,
    current_user: Annotated[CurrentUser, Depends(require_permission("feedback:view"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Mark a feedback as viewed by an admin.

    Updates admin_last_viewed_at to clear the "requires attention" indicator.
    Requires feedback:view permission.
    """
    feedback = await mark_feedback_viewed_by_admin(
        session=session,
        feedback_id=feedback_id,
        organization_id=current_user.organization_id,
    )

    if not feedback:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
            detail_code="feedback.not_found",
        )

    return MarkFeedbackViewedResponse(
        message="Feedback marked as viewed by admin",
        message_code="feedback.marked_viewed_admin",
        feedback_id=feedback.id,
        viewed_at=feedback.admin_last_viewed_at,
    )
