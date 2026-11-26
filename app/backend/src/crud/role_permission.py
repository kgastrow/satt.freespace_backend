"""
CRUD operations for RolePermission model.
Manages the many-to-many relationship between global roles and global permissions.
Both roles and permissions are now system-wide (not org-scoped).
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.permission import Permission
from src.models.role import Role
from src.models.role_permission import RolePermission
from src.models.user_role import UserRole
from src.models.user_type_permission import UserTypePermission
from src.models.user_user_type import OnboardingStatus, UserUserType
from src.services.cache import cache_service


async def grant_permission_to_role(
    session: AsyncSession, role_id: str, permission_id: str, granted_by_user_id: str
) -> RolePermission:
    """
    Grant a permission to a global role.

    Args:
        session: Database session
        role_id: Role UUID
        permission_id: Permission UUID
        granted_by_user_id: User UUID who is granting the permission

    Returns:
        The created RolePermission

    Raises:
        ValueError: If role not found, permission not found, or already granted
    """
    role_uuid = UUID(role_id) if isinstance(role_id, str) else role_id
    permission_uuid = (
        UUID(permission_id) if isinstance(permission_id, str) else permission_id
    )
    granted_by_uuid = (
        UUID(granted_by_user_id)
        if isinstance(granted_by_user_id, str)
        else granted_by_user_id
    )

    # Validate role exists (globally)
    role_result = await session.execute(
        select(Role).where(Role.id == role_uuid, Role.deleted_time.is_(None))
    )
    role = role_result.scalar_one_or_none()

    if not role:
        raise ValueError(f"Role with id {role_id} not found")

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
        select(RolePermission).where(
            RolePermission.role_id == role_uuid,
            RolePermission.permission_id == permission_uuid,
            RolePermission.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise ValueError(
            f"Permission '{permission.code}' is already granted to role '{role.name}'"
        )

    # Create new role permission
    role_permission = RolePermission(
        role_id=role_uuid, permission_id=permission_uuid, granted_by=granted_by_uuid
    )

    session.add(role_permission)
    try:
        await session.commit()
        await session.refresh(role_permission)
    except Exception as e:
        await session.rollback()
        raise e

    # Invalidate cache for all users with this role (across all organizations)
    await _invalidate_role_users_cache(session, role_id)

    return role_permission


async def revoke_permission_from_role(
    session: AsyncSession, role_id: str, permission_id: str
) -> RolePermission:
    """
    Revoke a permission from a global role (soft delete).

    Args:
        session: Database session
        role_id: Role UUID
        permission_id: Permission UUID

    Returns:
        The revoked RolePermission

    Raises:
        ValueError: If role not found or permission grant not found
    """
    role_uuid = UUID(role_id) if isinstance(role_id, str) else role_id
    permission_uuid = (
        UUID(permission_id) if isinstance(permission_id, str) else permission_id
    )

    # Validate role exists (globally)
    role_result = await session.execute(
        select(Role).where(Role.id == role_uuid, Role.deleted_time.is_(None))
    )
    role = role_result.scalar_one_or_none()

    if not role:
        raise ValueError(f"Role with id {role_id} not found")

    # Find existing grant
    result = await session.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_uuid,
            RolePermission.permission_id == permission_uuid,
            RolePermission.deleted_time.is_(None),
        )
    )
    role_permission = result.scalar_one_or_none()

    if not role_permission:
        raise ValueError("Permission grant not found")

    # Soft delete
    role_permission.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(role_permission)
    except Exception as e:
        await session.rollback()
        raise e

    # Invalidate cache for all users with this role (across all organizations)
    await _invalidate_role_users_cache(session, role_id)

    return role_permission


async def get_role_permissions(session: AsyncSession, role_id: str) -> list[Permission]:
    """
    Get all permissions for a global role.

    Args:
        session: Database session
        role_id: Role UUID

    Returns:
        List of Permission objects
    """
    role_uuid = UUID(role_id) if isinstance(role_id, str) else role_id

    # Validate role exists
    role_result = await session.execute(
        select(Role).where(Role.id == role_uuid, Role.deleted_time.is_(None))
    )
    role = role_result.scalar_one_or_none()

    if not role:
        return []

    # Get permissions through role_permissions
    result = await session.execute(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(
            RolePermission.role_id == role_uuid,
            RolePermission.deleted_time.is_(None),
            Permission.deleted_time.is_(None),
        )
        .order_by(Permission.resource, Permission.display_order, Permission.action)
    )
    permissions = result.scalars().all()

    return list(permissions)


async def get_user_permissions(
    session: AsyncSession, user_id: str, organization_id: str
) -> list[str]:
    """
    Get all permission codes for a user based on their roles AND user types.
    Uses cache when available.

    Permission aggregation:
    - User -> UserRole -> Role -> RolePermission -> Permission
    - User -> UserUserType -> UserType -> UserTypePermission -> Permission

    Args:
        session: Database session
        user_id: User UUID
        organization_id: Organization UUID (for user_role and user_user_type context)

    Returns:
        List of permission code strings (e.g., ['users:read', 'roles:write'])
    """
    # Try cache first
    cached_permissions = await cache_service.get_user_permissions(
        organization_id, user_id
    )
    if cached_permissions is not None:
        return cached_permissions

    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    # Get all permissions through user's active roles in this organization
    role_permissions_result = await session.execute(
        select(Permission.code)
        .distinct()
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_uuid,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
            RolePermission.deleted_time.is_(None),
            Permission.deleted_time.is_(None),
        )
    )
    role_permission_codes = {row[0] for row in role_permissions_result.fetchall()}

    # Get all permissions through user's active user types in this organization
    # Only include user types that are approved and not expired
    now = datetime.now(timezone.utc)
    user_type_permissions_result = await session.execute(
        select(Permission.code)
        .distinct()
        .join(UserTypePermission, UserTypePermission.permission_id == Permission.id)
        .join(
            UserUserType, UserUserType.user_type_id == UserTypePermission.user_type_id
        )
        .where(
            UserUserType.user_id == user_uuid,
            UserUserType.organization_id == org_uuid,
            UserUserType.onboarding_status == OnboardingStatus.APPROVED,
            UserUserType.deleted_time.is_(None),
            UserTypePermission.deleted_time.is_(None),
            Permission.deleted_time.is_(None),
            # Expiry check - include if no expiry OR not yet expired
            or_(
                UserUserType.expires_at.is_(None),
                UserUserType.expires_at > now,
            ),
        )
    )
    user_type_permission_codes = {
        row[0] for row in user_type_permissions_result.fetchall()
    }

    # Union permissions from both sources
    permission_codes = list(role_permission_codes | user_type_permission_codes)

    # Cache the result
    await cache_service.set_user_permissions(organization_id, user_id, permission_codes)

    return permission_codes


async def user_has_permission(
    session: AsyncSession, user_id: str, organization_id: str, permission_code: str
) -> bool:
    """
    Check if a user has a specific permission.

    Args:
        session: Database session
        user_id: User UUID
        organization_id: Organization UUID
        permission_code: Permission code to check (e.g., 'users:read')

    Returns:
        True if user has the permission, False otherwise
    """
    permissions = await get_user_permissions(session, user_id, organization_id)
    return permission_code in permissions


async def get_permission_matrix(session: AsyncSession) -> dict[str, Any]:
    """
    Get global permission matrix.
    Returns all permissions and all global roles with their assigned permission IDs.

    Args:
        session: Database session

    Returns:
        Dict with 'permissions' list and 'roles' list with permission_ids
    """
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

    return {"permissions": permission_data, "roles": role_data}


async def _invalidate_role_users_cache(session: AsyncSession, role_id: str) -> None:
    """
    Invalidate permission cache for all users with a specific role.
    Since roles are global, we need to invalidate across all organizations.

    Args:
        session: Database session
        role_id: Role UUID
    """
    role_uuid = UUID(role_id) if isinstance(role_id, str) else role_id

    # Invalidate role-level cache
    await cache_service.invalidate_role_permissions(role_id)

    # Get all user_role assignments for this role (across all organizations)
    result = await session.execute(
        select(UserRole.user_id, UserRole.organization_id).where(
            UserRole.role_id == role_uuid,
            UserRole.deleted_time.is_(None),
        )
    )
    user_org_pairs = result.fetchall()

    # Invalidate each user's permission cache in their respective org context
    for user_id, org_id in user_org_pairs:
        await cache_service.invalidate_user_permissions(str(org_id), str(user_id))
