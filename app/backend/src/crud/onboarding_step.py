"""
CRUD operations for the global OnboardingStep model.
Onboarding steps are system-wide and not scoped to organizations.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.onboarding_step import OnboardingStep


async def get_all_for_user_type(session: AsyncSession, user_type_id: str):
    """Get all onboarding steps for a specific user type, ordered by step_order."""
    result = await session.execute(
        select(OnboardingStep)
        .where(
            OnboardingStep.user_type_id == UUID(user_type_id),
            OnboardingStep.deleted_time.is_(None),
        )
        .order_by(OnboardingStep.step_order)
    )
    return result.scalars().all()


async def get_by_id(session: AsyncSession, id: str):
    """Get an onboarding step by ID."""
    result = await session.execute(
        select(OnboardingStep).where(
            OnboardingStep.id == UUID(id), OnboardingStep.deleted_time.is_(None)
        )
    )
    return result.scalars().first()


async def create(session: AsyncSession, data: dict):
    """Create a new onboarding step."""
    # Handle user_type_id which might already be a UUID or a string
    user_type_id = data["user_type_id"]
    if isinstance(user_type_id, str):
        user_type_id = UUID(user_type_id)

    # Check if code already exists for this user type
    existing = await session.execute(
        select(OnboardingStep).where(
            OnboardingStep.user_type_id == user_type_id,
            OnboardingStep.code == data["code"],
            OnboardingStep.deleted_time.is_(None),
        )
    )
    if existing.scalars().first():
        raise ValueError(
            f"Onboarding step with code '{data['code']}' already exists for this user type"
        )

    step = OnboardingStep(
        user_type_id=user_type_id,
        name=data["name"],
        code=data["code"],
        step_order=data["step_order"],
        description=data.get("description"),
        required_fields=data.get("required_fields"),
        validation_rules=data.get("validation_rules"),
        requires_verification=data.get("requires_verification", False),
        is_active=data.get("is_active", True),
    )
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


async def update(session: AsyncSession, id: str, data: dict):
    """Update an onboarding step."""
    step = await get_by_id(session, id)
    if not step:
        raise ValueError(f"Onboarding step with id {id} not found")

    # Check code uniqueness if code is being changed
    if "code" in data and data["code"] != step.code:
        existing = await session.execute(
            select(OnboardingStep).where(
                OnboardingStep.user_type_id == step.user_type_id,
                OnboardingStep.code == data["code"],
                OnboardingStep.id != UUID(id),
                OnboardingStep.deleted_time.is_(None),
            )
        )
        if existing.scalars().first():
            raise ValueError(
                f"Onboarding step with code '{data['code']}' already exists for this user type"
            )

    for key, value in data.items():
        if hasattr(step, key):
            setattr(step, key, value)

    await session.commit()
    await session.refresh(step)
    return step


async def reorder(session: AsyncSession, user_type_id: str, step_orders: list[dict]):
    """
    Reorder steps for a user type.
    step_orders should be a list of dicts with 'id' and 'step_order' keys.
    """
    for item in step_orders:
        step = await get_by_id(session, item["id"])
        if not step:
            raise ValueError(f"Onboarding step with id {item['id']} not found")
        if str(step.user_type_id) != user_type_id:
            raise ValueError(
                f"Onboarding step {item['id']} does not belong to user type {user_type_id}"
            )
        step.step_order = item["step_order"]

    await session.commit()
    return True


async def soft_delete(session: AsyncSession, id: str):
    """Soft delete an onboarding step."""
    step = await get_by_id(session, id)
    if not step:
        raise ValueError(f"Onboarding step with id {id} not found")

    step.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(step)
    return step
