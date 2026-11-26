"""
CRUD operations for the global UserType model.
User types are system-wide and not scoped to organizations.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_type import UserType


async def get_all(session: AsyncSession, limit: int = 100, offset: int = 0):
    """Get all user types."""
    count_result = await session.execute(
        select(func.count())
        .select_from(UserType)
        .where(UserType.deleted_time.is_(None))
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(UserType)
        .where(UserType.deleted_time.is_(None))
        .order_by(UserType.display_order, UserType.name)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all(), total


async def get_by_id(session: AsyncSession, id: str):
    """Get a user type by ID."""
    result = await session.execute(
        select(UserType).where(UserType.id == UUID(id), UserType.deleted_time.is_(None))
    )
    return result.scalars().first()


async def get_by_code(session: AsyncSession, code: str):
    """Get a user type by code."""
    result = await session.execute(
        select(UserType).where(UserType.code == code, UserType.deleted_time.is_(None))
    )
    return result.scalars().first()


async def get_default(session: AsyncSession):
    """Get the default user type."""
    result = await session.execute(
        select(UserType).where(
            UserType.is_default.is_(True), UserType.deleted_time.is_(None)
        )
    )
    return result.scalars().first()


async def get_active_user_types(session: AsyncSession):
    """Get all active user types that require onboarding."""
    result = await session.execute(
        select(UserType)
        .where(
            UserType.is_active.is_(True),
            UserType.deleted_time.is_(None),
        )
        .order_by(UserType.display_order, UserType.name)
    )
    return result.scalars().all()


async def create(session: AsyncSession, data: dict):
    """Create a new user type."""
    # Check if code already exists
    existing = await session.execute(
        select(UserType).where(
            UserType.code == data["code"], UserType.deleted_time.is_(None)
        )
    )
    if existing.scalars().first():
        raise ValueError(f"User type with code '{data['code']}' already exists")

    user_type = UserType(**data)
    session.add(user_type)
    await session.commit()
    await session.refresh(user_type)
    return user_type


async def update(session: AsyncSession, id: str, data: dict):
    """Update a user type."""
    user_type = await get_by_id(session, id)
    if not user_type:
        raise ValueError(f"User type with id {id} not found")

    # Check code uniqueness if code is being changed
    if "code" in data and data["code"] != user_type.code:
        existing = await session.execute(
            select(UserType).where(
                UserType.code == data["code"],
                UserType.id != UUID(id),
                UserType.deleted_time.is_(None),
            )
        )
        if existing.scalars().first():
            raise ValueError(f"User type with code '{data['code']}' already exists")

    for key, value in data.items():
        if hasattr(user_type, key):
            setattr(user_type, key, value)

    await session.commit()
    await session.refresh(user_type)
    return user_type


async def soft_delete(session: AsyncSession, id: str):
    """Soft delete a user type."""
    user_type = await get_by_id(session, id)
    if not user_type:
        raise ValueError(f"User type with id {id} not found")

    user_type.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user_type)
    return user_type
