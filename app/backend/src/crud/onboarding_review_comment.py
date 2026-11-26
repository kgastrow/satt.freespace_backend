"""
CRUD operations for the tenant-scoped OnboardingReviewComment model.
Tracks comments/messages between admins and users during onboarding review.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.onboarding_review_comment import (
    CommentAuthorType,
    OnboardingReviewComment,
)


async def create(
    session: AsyncSession,
    user_user_type_id: str,
    author_id: str,
    author_type: CommentAuthorType,
    comment: str,
    organization_id: str,
) -> OnboardingReviewComment:
    """Create a new review comment."""
    review_comment = OnboardingReviewComment(
        user_user_type_id=UUID(user_user_type_id),
        author_id=UUID(author_id),
        author_type=author_type,
        comment=comment,
        organization_id=UUID(organization_id),
    )
    session.add(review_comment)
    await session.commit()
    await session.refresh(review_comment)
    return review_comment


async def get_for_submission(
    session: AsyncSession, user_user_type_id: str, organization_id: str
) -> list[OnboardingReviewComment]:
    """Get all comments for a submission, ordered by created_time ascending."""
    result = await session.execute(
        select(OnboardingReviewComment)
        .options(selectinload(OnboardingReviewComment.author))
        .where(
            OnboardingReviewComment.user_user_type_id == UUID(user_user_type_id),
            OnboardingReviewComment.organization_id == UUID(organization_id),
            OnboardingReviewComment.deleted_time.is_(None),
        )
        .order_by(OnboardingReviewComment.created_time.asc())
    )
    return list(result.scalars().all())


async def get_latest_for_submission(
    session: AsyncSession, user_user_type_id: str, organization_id: str
) -> OnboardingReviewComment | None:
    """Get the most recent comment for a submission."""
    result = await session.execute(
        select(OnboardingReviewComment)
        .options(selectinload(OnboardingReviewComment.author))
        .where(
            OnboardingReviewComment.user_user_type_id == UUID(user_user_type_id),
            OnboardingReviewComment.organization_id == UUID(organization_id),
            OnboardingReviewComment.deleted_time.is_(None),
        )
        .order_by(OnboardingReviewComment.created_time.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_latest_admin_comment(
    session: AsyncSession, user_user_type_id: str, organization_id: str
) -> OnboardingReviewComment | None:
    """Get the most recent admin comment for a submission (for showing change request)."""
    result = await session.execute(
        select(OnboardingReviewComment)
        .options(selectinload(OnboardingReviewComment.author))
        .where(
            OnboardingReviewComment.user_user_type_id == UUID(user_user_type_id),
            OnboardingReviewComment.organization_id == UUID(organization_id),
            OnboardingReviewComment.author_type == CommentAuthorType.ADMIN,
            OnboardingReviewComment.deleted_time.is_(None),
        )
        .order_by(OnboardingReviewComment.created_time.desc())
        .limit(1)
    )
    return result.scalars().first()
