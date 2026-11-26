"""
CRUD operations for the tenant-scoped UserOnboardingProgress model.
Tracks progress through onboarding steps for users within an organization.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_onboarding_progress import UserOnboardingProgress


async def get_progress_for_user_type(
    session: AsyncSession, user_user_type_id: str, organization_id: str
):
    """Get all progress records for a user's onboarding (by user_user_type_id)."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserOnboardingProgress).where(
            UserOnboardingProgress.user_user_type_id == UUID(user_user_type_id),
            UserOnboardingProgress.organization_id == org_uuid,
            UserOnboardingProgress.deleted_time.is_(None),
        )
    )
    return result.scalars().all()


async def get_step_progress(
    session: AsyncSession,
    user_user_type_id: str,
    onboarding_step_id: str,
    organization_id: str,
):
    """Get progress record for a specific step."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserOnboardingProgress).where(
            UserOnboardingProgress.user_user_type_id == UUID(user_user_type_id),
            UserOnboardingProgress.onboarding_step_id == UUID(onboarding_step_id),
            UserOnboardingProgress.organization_id == org_uuid,
            UserOnboardingProgress.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create(session: AsyncSession, data: dict, organization_id: str):
    """Create a new progress record."""
    org_uuid = UUID(organization_id)
    user_id = UUID(data["user_id"])
    user_user_type_id = UUID(data["user_user_type_id"])
    onboarding_step_id = UUID(data["onboarding_step_id"])

    # Check if progress already exists for this step
    existing = await session.execute(
        select(UserOnboardingProgress).where(
            UserOnboardingProgress.user_user_type_id == user_user_type_id,
            UserOnboardingProgress.onboarding_step_id == onboarding_step_id,
            UserOnboardingProgress.organization_id == org_uuid,
            UserOnboardingProgress.deleted_time.is_(None),
        )
    )
    if existing.scalars().first():
        raise ValueError("Progress record already exists for this step")

    progress = UserOnboardingProgress(
        user_id=user_id,
        user_user_type_id=user_user_type_id,
        onboarding_step_id=onboarding_step_id,
        organization_id=org_uuid,
        submitted_data=data.get("submitted_data"),
        completed_time=data.get("completed_time"),
    )
    session.add(progress)
    await session.commit()
    await session.refresh(progress)
    return progress


async def update(session: AsyncSession, id: str, data: dict, organization_id: str):
    """Update a progress record."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserOnboardingProgress).where(
            UserOnboardingProgress.id == UUID(id),
            UserOnboardingProgress.organization_id == org_uuid,
            UserOnboardingProgress.deleted_time.is_(None),
        )
    )
    progress = result.scalars().first()
    if not progress:
        raise ValueError(f"Progress record with id {id} not found")

    for key, value in data.items():
        if hasattr(progress, key):
            setattr(progress, key, value)

    await session.commit()
    await session.refresh(progress)
    return progress
