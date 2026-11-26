"""
CRUD operations for the global Role model.
Roles are system-wide and not scoped to organizations.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.role import Role
from src.serialisers.role import (
    CreateRoleRequest,
    DeleteRoleRequest,
    GetRoleRequest,
    UpdateRoleRequest,
)


# Protected system roles that cannot be modified or deleted
PROTECTED_ROLES = frozenset(["admin", "owner", "super_admin"])


async def create_role(session: AsyncSession, request: dict):
    """Create a new global role."""
    validated_request = CreateRoleRequest(**request)

    # Check if role name already exists globally
    existing_result = await session.execute(
        select(Role).where(
            Role.name == validated_request.name, Role.deleted_time.is_(None)
        )
    )
    existing_role = existing_result.scalars().first()

    if existing_role:
        raise ValueError(f"Role with name '{validated_request.name}' already exists")

    new_role = Role(
        name=validated_request.name,
        description=validated_request.description,
        is_default_on_registration=validated_request.is_default_on_registration,
    )

    session.add(new_role)
    await session.commit()
    await session.refresh(new_role)
    return new_role


async def get_role_by_id(session: AsyncSession, role_id: str):
    """Get a global role by ID."""
    request = GetRoleRequest(id=UUID(role_id))
    result = await session.execute(
        select(Role).where(Role.id == request.id, Role.deleted_time.is_(None))
    )
    role = result.scalars().first()
    return role


async def get_role_by_name(session: AsyncSession, name: str):
    """Get a global role by name."""
    result = await session.execute(
        select(Role).where(Role.name == name, Role.deleted_time.is_(None))
    )
    role = result.scalars().first()
    return role


async def list_roles(session: AsyncSession, limit: int = 100, offset: int = 0):
    """List all global roles."""
    # Efficient count query using func.count()
    count_result = await session.execute(
        select(func.count()).select_from(Role).where(Role.deleted_time.is_(None))
    )
    total = count_result.scalar() or 0

    # Get paginated results
    result = await session.execute(
        select(Role)
        .where(Role.deleted_time.is_(None))
        .order_by(Role.name)
        .limit(limit)
        .offset(offset)
    )
    roles = result.scalars().all()
    return roles, total


async def update_role(session: AsyncSession, role_id: str, request: dict):
    """Update a global role."""
    validated_request = UpdateRoleRequest(**request)
    role = await get_role_by_id(session, role_id)

    if not role:
        raise ValueError(f"Role with id {role_id} not found")

    # Prevent modification of protected system roles
    if role.name in PROTECTED_ROLES:
        raise ValueError("Cannot modify protected system role")

    if validated_request.name:
        # Check if new name conflicts globally
        existing_result = await session.execute(
            select(Role).where(
                Role.name == validated_request.name,
                Role.id != role.id,
                Role.deleted_time.is_(None),
            )
        )
        existing_role = existing_result.scalars().first()

        if existing_role:
            raise ValueError(
                f"Role with name '{validated_request.name}' already exists"
            )
        role.name = validated_request.name

    if validated_request.description is not None:
        role.description = validated_request.description

    if validated_request.is_default_on_registration is not None:
        role.is_default_on_registration = validated_request.is_default_on_registration

    await session.commit()
    await session.refresh(role)
    return role


async def delete_role(session: AsyncSession, role_id: str):
    """Soft delete a global role."""
    request = DeleteRoleRequest(id=UUID(role_id))
    role = await get_role_by_id(session, str(request.id))

    if not role:
        raise ValueError(f"Role with id {request.id} not found")

    # Prevent deletion of protected system roles
    if role.name in PROTECTED_ROLES:
        raise ValueError("Cannot delete protected system role")

    # Soft delete - CASCADE will handle user_role deletions at DB level
    role.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(role)
    return role


async def get_default_registration_roles(session: AsyncSession) -> list[Role]:
    """Get all roles that should be automatically assigned to new users on registration."""
    result = await session.execute(
        select(Role).where(
            Role.is_default_on_registration.is_(True),
            Role.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())
