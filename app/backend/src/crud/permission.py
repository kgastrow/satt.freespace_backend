"""
CRUD operations for Permission model.
Permissions are global (no organization_id) and define available actions in the system.
Permission codes follow the format 'resource:action' (e.g., 'users:read', 'roles:write').
"""

from datetime import datetime, timezone
import re
from typing import Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.permission import Permission


# Regex pattern for permission code validation
PERMISSION_CODE_PATTERN = re.compile(r"^[a-z_]+:[a-z_]+$")


async def create_permission(
    session: AsyncSession,
    code: str,
    name: str,
    description: Optional[str] = None,
    display_order: int = 0,
) -> Permission:
    """
    Create a new permission.

    Args:
        session: Database session
        code: Permission code in format 'resource:action' (e.g., 'users:read')
        name: Human-readable permission name
        description: Optional description
        display_order: Optional display order for UI

    Returns:
        The created Permission

    Raises:
        ValueError: If code format is invalid or code already exists
    """
    # Validate code format
    if not PERMISSION_CODE_PATTERN.match(code):
        raise ValueError(
            f"Invalid permission code format: '{code}'. "
            "Must be 'resource:action' with lowercase letters and underscores only."
        )

    # Parse resource and action from code
    resource, action = code.split(":")

    # Check for duplicate code
    existing_result = await session.execute(
        select(Permission).where(
            Permission.code == code, Permission.deleted_time.is_(None)
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise ValueError(f"Permission with code '{code}' already exists")

    # Create new permission
    permission = Permission(
        code=code,
        name=name,
        description=description,
        resource=resource,
        action=action,
        display_order=display_order,
    )

    session.add(permission)
    try:
        await session.commit()
        await session.refresh(permission)
    except Exception as e:
        await session.rollback()
        raise e

    return permission


async def get_permission_by_code(
    session: AsyncSession, code: str
) -> Optional[Permission]:
    """
    Get a permission by its code.

    Args:
        session: Database session
        code: Permission code (e.g., 'users:read')

    Returns:
        Permission if found, None otherwise
    """
    result = await session.execute(
        select(Permission).where(
            Permission.code == code, Permission.deleted_time.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def get_permission_by_id(
    session: AsyncSession, permission_id: str
) -> Optional[Permission]:
    """
    Get a permission by its ID.

    Args:
        session: Database session
        permission_id: Permission UUID

    Returns:
        Permission if found, None otherwise
    """
    perm_uuid = UUID(permission_id) if isinstance(permission_id, str) else permission_id

    result = await session.execute(
        select(Permission).where(
            Permission.id == perm_uuid, Permission.deleted_time.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def get_all_permissions(
    session: AsyncSession,
    resource: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Permission], int]:
    """
    Get all permissions with optional filtering by resource.

    Args:
        session: Database session
        resource: Optional resource filter (e.g., 'users', 'roles')
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        Tuple of (list of permissions, total count)
    """
    # Build base conditions
    conditions: list[ColumnElement[bool]] = [Permission.deleted_time.is_(None)]

    if resource:
        conditions.append(Permission.resource == resource)

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(Permission).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query with ordering
    result = await session.execute(
        select(Permission)
        .where(*conditions)
        .order_by(Permission.resource, Permission.display_order, Permission.action)
        .limit(limit)
        .offset(offset)
    )
    permissions = result.scalars().all()

    return list(permissions), total


async def update_permission(
    session: AsyncSession,
    permission_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    display_order: Optional[int] = None,
) -> Permission:
    """
    Update a permission's name, description, or display order.
    Note: Code cannot be changed after creation.

    Args:
        session: Database session
        permission_id: Permission UUID
        name: Optional new name
        description: Optional new description
        display_order: Optional new display order

    Returns:
        Updated Permission

    Raises:
        ValueError: If permission not found
    """
    permission = await get_permission_by_id(session, permission_id)

    if not permission:
        raise ValueError(f"Permission with id {permission_id} not found")

    # Update fields if provided
    if name is not None:
        permission.name = name

    if description is not None:
        permission.description = description

    if display_order is not None:
        permission.display_order = display_order

    try:
        await session.commit()
        await session.refresh(permission)
    except Exception as e:
        await session.rollback()
        raise e

    return permission


async def delete_permission(session: AsyncSession, permission_id: str) -> Permission:
    """
    Soft delete a permission.

    Args:
        session: Database session
        permission_id: Permission UUID

    Returns:
        Deleted Permission

    Raises:
        ValueError: If permission not found
    """
    permission = await get_permission_by_id(session, permission_id)

    if not permission:
        raise ValueError(f"Permission with id {permission_id} not found")

    # Soft delete
    permission.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(permission)
    except Exception as e:
        await session.rollback()
        raise e

    return permission


async def get_distinct_resources(session: AsyncSession) -> list[str]:
    """
    Get list of distinct resources from all permissions.
    Useful for UI filtering.

    Args:
        session: Database session

    Returns:
        List of distinct resource names
    """
    result = await session.execute(
        select(Permission.resource)
        .where(Permission.deleted_time.is_(None))
        .distinct()
        .order_by(Permission.resource)
    )
    return [row[0] for row in result.fetchall()]
