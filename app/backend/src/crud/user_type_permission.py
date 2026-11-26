"""
CRUD operations for UserTypePermission model.
Manages the many-to-many relationship between global user types and global permissions.
Both user types and permissions are system-wide (not org-scoped).
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.permission import Permission
from src.models.user_type import UserType
from src.models.user_type_permission import UserTypePermission
from src.models.user_user_type import UserUserType
from src.services.cache import cache_service


async def grant_permission_to_user_type(
    session: AsyncSession,
    user_type_id: str,
    permission_id: str,
    granted_by_user_id: str,
) -> UserTypePermission:
    """
    Grant a permission to a global user type.

    Args:
        session: Database session
        user_type_id: UserType UUID
        permission_id: Permission UUID
        granted_by_user_id: User UUID who is granting the permission

    Returns:
        The created UserTypePermission

    Raises:
        ValueError: If user type not found, permission not found, or already granted
    """
    user_type_uuid = (
        UUID(user_type_id) if isinstance(user_type_id, str) else user_type_id
    )
    permission_uuid = (
        UUID(permission_id) if isinstance(permission_id, str) else permission_id
    )
    granted_by_uuid = (
        UUID(granted_by_user_id)
        if isinstance(granted_by_user_id, str)
        else granted_by_user_id
    )

    # Validate user type exists
    user_type_result = await session.execute(
        select(UserType).where(
            UserType.id == user_type_uuid, UserType.deleted_time.is_(None)
        )
    )
    user_type = user_type_result.scalar_one_or_none()

    if not user_type:
        raise ValueError(f"User type with id {user_type_id} not found")

    # Validate permission exists
    permission_result = await session.execute(
        select(Permission).where(
            Permission.id == permission_uuid, Permission.deleted_time.is_(None)
        )
    )
    permission = permission_result.scalar_one_or_none()

    if not permission:
        raise ValueError(f"Permission with id {permission_id} not found")

    # Check if already granted
    existing_result = await session.execute(
        select(UserTypePermission).where(
            UserTypePermission.user_type_id == user_type_uuid,
            UserTypePermission.permission_id == permission_uuid,
            UserTypePermission.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise ValueError(
            f"Permission '{permission.code}' is already granted to user type '{user_type.name}'"
        )

    # Create new user type permission
    user_type_permission = UserTypePermission(
        user_type_id=user_type_uuid,
        permission_id=permission_uuid,
        granted_by=granted_by_uuid,
    )

    session.add(user_type_permission)
    try:
        await session.commit()
        await session.refresh(user_type_permission)
    except Exception as e:
        await session.rollback()
        raise e

    # Invalidate cache for all users with this user type
    await _invalidate_user_type_users_cache(session, user_type_id)

    return user_type_permission


async def revoke_permission_from_user_type(
    session: AsyncSession, user_type_id: str, permission_id: str
) -> UserTypePermission:
    """
    Revoke a permission from a global user type (soft delete).

    Args:
        session: Database session
        user_type_id: UserType UUID
        permission_id: Permission UUID

    Returns:
        The revoked UserTypePermission

    Raises:
        ValueError: If user type not found or permission grant not found
    """
    user_type_uuid = (
        UUID(user_type_id) if isinstance(user_type_id, str) else user_type_id
    )
    permission_uuid = (
        UUID(permission_id) if isinstance(permission_id, str) else permission_id
    )

    # Validate user type exists
    user_type_result = await session.execute(
        select(UserType).where(
            UserType.id == user_type_uuid, UserType.deleted_time.is_(None)
        )
    )
    user_type = user_type_result.scalar_one_or_none()

    if not user_type:
        raise ValueError(f"User type with id {user_type_id} not found")

    # Find existing grant
    result = await session.execute(
        select(UserTypePermission).where(
            UserTypePermission.user_type_id == user_type_uuid,
            UserTypePermission.permission_id == permission_uuid,
            UserTypePermission.deleted_time.is_(None),
        )
    )
    user_type_permission = result.scalar_one_or_none()

    if not user_type_permission:
        raise ValueError("Permission grant not found")

    # Soft delete
    user_type_permission.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(user_type_permission)
    except Exception as e:
        await session.rollback()
        raise e

    # Invalidate cache for all users with this user type
    await _invalidate_user_type_users_cache(session, user_type_id)

    return user_type_permission


async def get_user_type_permissions(
    session: AsyncSession, user_type_id: str
) -> list[Permission]:
    """
    Get all permissions for a global user type.

    Args:
        session: Database session
        user_type_id: UserType UUID

    Returns:
        List of Permission objects
    """
    user_type_uuid = (
        UUID(user_type_id) if isinstance(user_type_id, str) else user_type_id
    )

    # Validate user type exists
    user_type_result = await session.execute(
        select(UserType).where(
            UserType.id == user_type_uuid, UserType.deleted_time.is_(None)
        )
    )
    user_type = user_type_result.scalar_one_or_none()

    if not user_type:
        return []

    # Get permissions through user_type_permissions
    result = await session.execute(
        select(Permission)
        .join(UserTypePermission, UserTypePermission.permission_id == Permission.id)
        .where(
            UserTypePermission.user_type_id == user_type_uuid,
            UserTypePermission.deleted_time.is_(None),
            Permission.deleted_time.is_(None),
        )
        .order_by(Permission.resource, Permission.display_order, Permission.action)
    )
    permissions = result.scalars().all()

    return list(permissions)


async def get_permissions_by_user_types(
    session: AsyncSession, user_type_ids: list[str]
) -> list[str]:
    """
    Get all permission codes for a list of user types.

    Args:
        session: Database session
        user_type_ids: List of UserType UUIDs

    Returns:
        List of permission code strings
    """
    if not user_type_ids:
        return []

    user_type_uuids = [
        UUID(ut_id) if isinstance(ut_id, str) else ut_id for ut_id in user_type_ids
    ]

    result = await session.execute(
        select(Permission.code)
        .distinct()
        .join(UserTypePermission, UserTypePermission.permission_id == Permission.id)
        .where(
            UserTypePermission.user_type_id.in_(user_type_uuids),
            UserTypePermission.deleted_time.is_(None),
            Permission.deleted_time.is_(None),
        )
    )
    permission_codes = [row[0] for row in result.fetchall()]

    return permission_codes


async def get_extended_permission_matrix(session: AsyncSession) -> dict:
    """
    Get extended permission matrix including user types.
    Returns all permissions, roles with their assigned permission IDs,
    and user types with their assigned permission IDs.

    Args:
        session: Database session

    Returns:
        Dict with 'permissions', 'roles', and 'user_types' lists
    """
    from src.models.role import Role

    # Get all permissions
    permissions_result = await session.execute(
        select(Permission)
        .where(Permission.deleted_time.is_(None))
        .order_by(Permission.resource, Permission.display_order, Permission.action)
    )
    permissions = permissions_result.scalars().all()

    # Get all global roles with their permissions
    roles_result = await session.execute(
        select(Role)
        .options(selectinload(Role.role_permissions))
        .where(Role.deleted_time.is_(None))
        .order_by(Role.name)
    )
    roles = roles_result.scalars().all()

    # Get all user types with their permissions
    user_types_result = await session.execute(
        select(UserType)
        .options(selectinload(UserType.user_type_permissions))
        .where(UserType.deleted_time.is_(None), UserType.is_active.is_(True))
        .order_by(UserType.display_order, UserType.name)
    )
    user_types = user_types_result.scalars().all()

    # Build role data with permission IDs
    role_data = []
    for role in roles:
        permission_ids = [
            str(rp.permission_id)
            for rp in role.role_permissions
            if rp.deleted_time is None
        ]
        role_data.append(
            {
                "id": str(role.id),
                "name": role.name,
                "description": role.description,
                "permission_ids": permission_ids,
            }
        )

    # Build user type data with permission IDs
    user_type_data = []
    for user_type in user_types:
        permission_ids = [
            str(utp.permission_id)
            for utp in user_type.user_type_permissions
            if utp.deleted_time is None
        ]
        user_type_data.append(
            {
                "id": str(user_type.id),
                "name": user_type.name,
                "code": user_type.code,
                "description": user_type.description,
                "permission_ids": permission_ids,
            }
        )

    # Build permission data
    permission_data = [
        {
            "id": str(p.id),
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "resource": p.resource,
            "action": p.action,
            "display_order": p.display_order,
        }
        for p in permissions
    ]

    return {
        "permissions": permission_data,
        "roles": role_data,
        "user_types": user_type_data,
    }


async def _invalidate_user_type_users_cache(
    session: AsyncSession, user_type_id: str
) -> None:
    """
    Invalidate permission cache for all users with a specific user type.
    Since user types can be assigned across organizations, we need to
    invalidate across all relevant org contexts.

    Args:
        session: Database session
        user_type_id: UserType UUID
    """
    user_type_uuid = (
        UUID(user_type_id) if isinstance(user_type_id, str) else user_type_id
    )

    # Get all user_user_type assignments for this user type (across all organizations)
    result = await session.execute(
        select(UserUserType.user_id, UserUserType.organization_id).where(
            UserUserType.user_type_id == user_type_uuid,
            UserUserType.deleted_time.is_(None),
        )
    )
    user_org_pairs = result.fetchall()

    # Invalidate each user's permission cache in their respective org context
    for user_id, org_id in user_org_pairs:
        await cache_service.invalidate_user_permissions(str(org_id), str(user_id))
