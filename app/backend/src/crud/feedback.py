"""
CRUD operations for Feedback and FeedbackAttachment models.

All feedback operations are tenant-scoped and require organization_id filtering.
Supports filtering by type, status, date range, and rating.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sort,
    get_total_count,
)
from src.core.query_params import FilterSpec, SortSpec
from src.models.feedback import Feedback, FeedbackAttachment, FeedbackReply


# Configuration for feedback DSL queries
FEEDBACK_FILTER_FIELDS = {"type", "status", "rating", "created_time"}
FEEDBACK_SORT_FIELDS = {"created_time", "type", "status", "rating"}
FEEDBACK_FIELD_MAPPING: dict[str, str] = {}


async def create_feedback(
    session: AsyncSession,
    feedback_data: dict[str, Any],
    organization_id: str,
    user_id: str,
) -> Feedback:
    """
    Create a feedback submission.

    Args:
        session: Database session
        feedback_data: Feedback data including:
            - type: Feedback type (bug, suggestion, complaint, praise, other)
            - rating: Star rating 1-5 (optional)
            - subject: Feedback subject (max 100 chars)
            - message: Feedback message (max 2000 chars)
            - page_url: Page URL where feedback was submitted (optional)
            - user_agent: User agent string (optional)
            - screen_resolution: Screen resolution (optional)
        organization_id: Organization UUID string
        user_id: User ID submitting the feedback

    Returns:
        The created Feedback

    Raises:
        ValueError: If validation fails
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    feedback = Feedback(
        organization_id=org_uuid,
        user_id=user_uuid,
        type=feedback_data["type"],
        rating=feedback_data.get("rating"),
        subject=feedback_data["subject"],
        message=feedback_data["message"],
        page_url=feedback_data.get("page_url"),
        user_agent=feedback_data.get("user_agent"),
        screen_resolution=feedback_data.get("screen_resolution"),
        status="new",
    )

    session.add(feedback)
    try:
        await session.commit()
        await session.refresh(feedback)
    except Exception as e:
        await session.rollback()
        raise e

    return feedback


async def get_feedback_by_id(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
    load_relationships: bool = True,
) -> Optional[Feedback]:
    """
    Get feedback by ID within organization context.

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string
        load_relationships: Whether to eagerly load user and attachments relationships

    Returns:
        The Feedback or None if not found
    """
    feedback_uuid = UUID(feedback_id)
    org_uuid = UUID(organization_id)

    conditions: list[ColumnElement[bool]] = [
        Feedback.id == feedback_uuid,
        Feedback.organization_id == org_uuid,
        Feedback.deleted_time.is_(None),
    ]

    query = select(Feedback).where(*conditions)

    if load_relationships:
        query = query.options(
            selectinload(Feedback.attachments),
            selectinload(Feedback.user),
            selectinload(Feedback.replies).selectinload(FeedbackReply.user),
        )

    result = await session.execute(query)
    return result.scalars().first()


async def get_feedbacks_list(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Feedback], int]:
    """
    Get paginated list of feedback with DSL filtering and sorting.

    Args:
        session: Database session
        organization_id: Organization UUID string
        filters: List of FilterSpec objects for filtering
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of feedback, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query with eager loading
    base_query = (
        select(Feedback)
        .where(
            Feedback.organization_id == org_uuid,
            Feedback.deleted_time.is_(None),
        )
        .options(
            selectinload(Feedback.attachments),
            selectinload(Feedback.user),
            selectinload(Feedback.replies).selectinload(FeedbackReply.user),
        )
    )

    # Apply DSL filters
    if filters:
        base_query = apply_filters(
            base_query, Feedback, filters, FEEDBACK_FIELD_MAPPING
        )

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to created_time desc)
    if sorts:
        base_query = apply_sort(base_query, Feedback, sorts, FEEDBACK_FIELD_MAPPING)
    else:
        base_query = base_query.order_by(Feedback.created_time.desc())

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    feedbacks = result.scalars().all()

    return list(feedbacks), total_count


async def get_user_feedbacks(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Feedback], int]:
    """
    Get feedback submissions by a specific user.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of feedback, total count)
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    conditions: list[ColumnElement[bool]] = [
        Feedback.organization_id == org_uuid,
        Feedback.user_id == user_uuid,
        Feedback.deleted_time.is_(None),
    ]

    # Count query
    count_query = select(func.count(Feedback.id)).where(*conditions)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    # Data query
    data_query = (
        select(Feedback)
        .where(*conditions)
        .options(
            selectinload(Feedback.attachments),
            selectinload(Feedback.user),
            selectinload(Feedback.replies).selectinload(FeedbackReply.user),
        )
        .order_by(Feedback.created_time.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    feedbacks = result.scalars().all()

    return list(feedbacks), total


async def update_feedback(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
    feedback_data: dict[str, Any],
    updated_by_id: Optional[str] = None,
) -> Optional[Feedback]:
    """
    Update a feedback (typically by admin).

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string
        feedback_data: Fields to update (all optional):
            - status: New status value
            - admin_notes: Internal admin notes
            - admin_response: Response visible to user
        updated_by_id: User ID performing the update (optional)

    Returns:
        The updated Feedback or None if not found

    Raises:
        ValueError: If trying to update feedback from another organization
    """
    feedback_uuid = UUID(feedback_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(Feedback).where(
            Feedback.id == feedback_uuid,
            Feedback.organization_id == org_uuid,
            Feedback.deleted_time.is_(None),
        )
    )
    feedback = result.scalars().first()

    if not feedback:
        return None

    # Update allowed fields
    if "status" in feedback_data:
        feedback.status = feedback_data["status"]
        # If status is being set to resolved, track resolution
        if feedback_data["status"] == "resolved" and feedback.resolved_at is None:
            feedback.resolved_at = datetime.now(timezone.utc)
            if updated_by_id:
                feedback.resolved_by = UUID(updated_by_id)

    if "admin_notes" in feedback_data:
        feedback.admin_notes = feedback_data["admin_notes"]

    if "admin_response" in feedback_data:
        feedback.admin_response = feedback_data["admin_response"]
        # Track when response was added
        if feedback_data["admin_response"] and feedback.responded_at is None:
            feedback.responded_at = datetime.now(timezone.utc)
            if updated_by_id:
                feedback.responded_by = UUID(updated_by_id)

    try:
        await session.commit()
        await session.refresh(feedback)
    except Exception as e:
        await session.rollback()
        raise e

    return feedback


async def soft_delete_feedback(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
) -> Optional[Feedback]:
    """
    Soft delete a feedback.

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string

    Returns:
        The deleted Feedback or None if not found

    Raises:
        ValueError: If trying to delete feedback from another organization
    """
    feedback_uuid = UUID(feedback_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(Feedback).where(
            Feedback.id == feedback_uuid,
            Feedback.organization_id == org_uuid,
            Feedback.deleted_time.is_(None),
        )
    )
    feedback = result.scalars().first()

    if not feedback:
        return None

    feedback.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(feedback)
    except Exception as e:
        await session.rollback()
        raise e

    return feedback


# ============================================================================
# FEEDBACK ATTACHMENT CRUD
# ============================================================================


async def create_feedback_attachment(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
    file_path: str,
    file_type: str,
    file_size_bytes: int,
) -> FeedbackAttachment:
    """
    Create a feedback attachment.

    Args:
        session: Database session
        feedback_id: Parent feedback UUID string
        organization_id: Organization UUID string (for tenant check)
        file_path: S3 path to the file
        file_type: MIME type of the file
        file_size_bytes: File size in bytes

    Returns:
        The created FeedbackAttachment

    Raises:
        ValueError: If feedback not found or doesn't belong to organization
    """
    feedback_uuid = UUID(feedback_id)

    # Verify feedback exists and belongs to organization
    feedback = await get_feedback_by_id(session, feedback_id, organization_id)
    if not feedback:
        raise ValueError(
            f"Feedback {feedback_id} not found in organization {organization_id}"
        )

    attachment = FeedbackAttachment(
        feedback_id=feedback_uuid,
        file_path=file_path,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
    )

    session.add(attachment)
    try:
        await session.commit()
        await session.refresh(attachment)
    except Exception as e:
        await session.rollback()
        raise e

    return attachment


async def get_attachments_by_feedback_id(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
) -> list[FeedbackAttachment]:
    """
    Get all attachments for a feedback.

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string (for tenant check)

    Returns:
        List of FeedbackAttachment
    """
    feedback_uuid = UUID(feedback_id)

    # Verify feedback exists and belongs to organization
    feedback = await get_feedback_by_id(session, feedback_id, organization_id)
    if not feedback:
        return []

    conditions: list[ColumnElement[bool]] = [
        FeedbackAttachment.feedback_id == feedback_uuid,
        FeedbackAttachment.deleted_time.is_(None),
    ]

    result = await session.execute(
        select(FeedbackAttachment)
        .where(*conditions)
        .order_by(FeedbackAttachment.created_time.asc())
    )
    return list(result.scalars().all())


async def delete_attachment(
    session: AsyncSession,
    attachment_id: str,
    organization_id: str,
) -> Optional[FeedbackAttachment]:
    """
    Soft delete an attachment.

    Args:
        session: Database session
        attachment_id: FeedbackAttachment UUID string
        organization_id: Organization UUID string (for tenant check)

    Returns:
        The deleted FeedbackAttachment or None if not found

    Raises:
        ValueError: If attachment's feedback doesn't belong to organization
    """
    attachment_uuid = UUID(attachment_id)
    org_uuid = UUID(organization_id)

    # Get attachment with feedback join to verify organization
    result = await session.execute(
        select(FeedbackAttachment)
        .join(Feedback, FeedbackAttachment.feedback_id == Feedback.id)
        .where(
            FeedbackAttachment.id == attachment_uuid,
            Feedback.organization_id == org_uuid,
            FeedbackAttachment.deleted_time.is_(None),
        )
    )
    attachment = result.scalars().first()

    if not attachment:
        return None

    attachment.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(attachment)
    except Exception as e:
        await session.rollback()
        raise e

    return attachment


# ============================================================================
# FEEDBACK REPLY CRUD
# ============================================================================


async def create_feedback_reply(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
    user_id: str,
    message: str,
    is_admin_reply: bool = False,
) -> FeedbackReply:
    """
    Create a reply to a feedback item.

    Args:
        session: Database session
        feedback_id: Parent feedback UUID string
        organization_id: Organization UUID string (for tenant check)
        user_id: User ID creating the reply
        message: Reply message content
        is_admin_reply: Whether this is an admin reply

    Returns:
        The created FeedbackReply

    Raises:
        ValueError: If feedback not found or doesn't belong to organization
    """
    feedback_uuid = UUID(feedback_id)
    user_uuid = UUID(user_id)

    # Verify feedback exists and belongs to organization
    feedback = await get_feedback_by_id(
        session, feedback_id, organization_id, load_relationships=False
    )
    if not feedback:
        raise ValueError(
            f"Feedback {feedback_id} not found in organization {organization_id}"
        )

    reply = FeedbackReply(
        feedback_id=feedback_uuid,
        user_id=user_uuid,
        message=message,
        is_admin_reply=is_admin_reply,
    )

    session.add(reply)
    try:
        await session.commit()
        await session.refresh(reply, ["user"])
    except Exception as e:
        await session.rollback()
        raise e

    return reply


async def get_feedback_replies(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
) -> list[FeedbackReply]:
    """
    Get all replies for a feedback item.

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string (for tenant check)

    Returns:
        List of FeedbackReply ordered by created_time
    """
    feedback_uuid = UUID(feedback_id)

    # Verify feedback exists and belongs to organization
    feedback = await get_feedback_by_id(
        session, feedback_id, organization_id, load_relationships=False
    )
    if not feedback:
        return []

    conditions: list[ColumnElement[bool]] = [
        FeedbackReply.feedback_id == feedback_uuid,
        FeedbackReply.deleted_time.is_(None),
    ]

    result = await session.execute(
        select(FeedbackReply)
        .where(*conditions)
        .options(selectinload(FeedbackReply.user))
        .order_by(FeedbackReply.created_time.asc())
    )
    return list(result.scalars().all())


async def mark_feedback_viewed(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
    user_id: str,
) -> Optional[Feedback]:
    """
    Mark a feedback as viewed by the user (updates user_last_viewed_at).

    Only the feedback owner can mark it as viewed.

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string
        user_id: User ID marking the feedback as viewed

    Returns:
        The updated Feedback or None if not found or not owner
    """
    feedback_uuid = UUID(feedback_id)
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(Feedback).where(
            Feedback.id == feedback_uuid,
            Feedback.organization_id == org_uuid,
            Feedback.user_id == user_uuid,  # Only owner can mark as viewed
            Feedback.deleted_time.is_(None),
        )
    )
    feedback = result.scalars().first()

    if not feedback:
        return None

    feedback.user_last_viewed_at = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(feedback)
    except Exception as e:
        await session.rollback()
        raise e

    return feedback


async def mark_feedback_viewed_by_admin(
    session: AsyncSession,
    feedback_id: str,
    organization_id: str,
) -> Optional[Feedback]:
    """
    Mark a feedback as viewed by an admin (updates admin_last_viewed_at).

    This clears the "requires attention" indicator for this feedback.

    Args:
        session: Database session
        feedback_id: Feedback UUID string
        organization_id: Organization UUID string

    Returns:
        The updated Feedback or None if not found
    """
    feedback_uuid = UUID(feedback_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(Feedback).where(
            Feedback.id == feedback_uuid,
            Feedback.organization_id == org_uuid,
            Feedback.deleted_time.is_(None),
        )
    )
    feedback = result.scalars().first()

    if not feedback:
        return None

    feedback.admin_last_viewed_at = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(feedback)
    except Exception as e:
        await session.rollback()
        raise e

    return feedback
