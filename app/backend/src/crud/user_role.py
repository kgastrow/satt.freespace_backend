"""
CRUD operations for UserRole model.
UserRole links users (org-scoped) to global roles.
The organization_id on UserRole indicates which org context the assignment is for.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.role import Role
from src.models.user import User
from src.models.user_role import UserRole
from src.serialisers.user_role import (
    AssignRoleRequest,
    GetUserRolesRequest,
    RevokeRoleRequest,
)


async def assign_role(
    session: AsyncSession, request: dict, assigned_by_user_id: str, organization_id: str
):
    """Assign a global role to a user within an organization context."""
    validated_request = AssignRoleRequest(**request)

    # Convert to UUID
    assigned_by_uuid = (
        UUID(assigned_by_user_id)
        if isinstance(assigned_by_user_id, str)
        else assigned_by_user_id
    )
    org_uuid = UUID(organization_id)

    # Check if user exists and belongs to organization
    user_result = await session.execute(
        select(User).where(
            User.id == validated_request.user_id,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = user_result.scalars().first()

    if not user:
        raise ValueError(f"User with id {validated_request.user_id} not found")

    # Check if role exists (globally - no org filter)
    role_result = await session.execute(
        select(Role).where(
            Role.id == validated_request.role_id, Role.deleted_time.is_(None)
        )
    )
    role = role_result.scalars().first()

    if not role:
        raise ValueError(f"Role with id {validated_request.role_id} not found")

    # Check if user already has this active role in this organization
    existing_result = await session.execute(
        select(UserRole).where(
            UserRole.user_id == validated_request.user_id,
            UserRole.role_id == validated_request.role_id,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
        )
    )
    existing_user_role = existing_result.scalars().first()

    if existing_user_role:
        raise ValueError(f"User already has role '{role.name}'")

    # Create new user_role assignment
    user_role = UserRole(
        user_id=validated_request.user_id,
        role_id=validated_request.role_id,
        assigned_by=assigned_by_uuid,
        organization_id=org_uuid,
    )

    session.add(user_role)
    await session.commit()

    # Re-fetch with eager loading for relationships accessed by API layer
    result = await session.execute(
        select(UserRole)
        .options(
            selectinload(UserRole.role),
            selectinload(UserRole.assigned_by_user),
        )
        .where(UserRole.id == user_role.id)
    )
    return result.scalars().first()


async def revoke_role(session: AsyncSession, request: dict, organization_id: str):
    """Revoke a role from a user within an organization context (soft delete).

    Note: The actor who revoked the role is captured via audit logs at the API layer.
    """
    validated_request = RevokeRoleRequest(**request)

    org_uuid = UUID(organization_id)

    # Find active user_role assignment within organization
    result = await session.execute(
        select(UserRole)
        .join(Role)
        .where(
            UserRole.user_id == validated_request.user_id,
            UserRole.role_id == validated_request.role_id,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
        )
    )
    user_role = result.scalars().first()

    if not user_role:
        raise ValueError("Active role assignment not found")

    # Get the role to check if it's the owner role
    role_result = await session.execute(
        select(Role).where(Role.id == validated_request.role_id)
    )
    role = role_result.scalars().first()

    # Prevent revoking the last owner role
    if role and role.name == "owner":
        owner_count = await count_users_with_role(session, "owner", organization_id)
        if owner_count <= 1:
            raise ValueError(
                "Cannot revoke owner role. Organization must have at least one owner."
            )

    # Revoke the role by soft-deleting
    user_role.deleted_time = datetime.now(timezone.utc)

    await session.commit()

    # Re-fetch with eager loading for relationships accessed by API layer
    result = await session.execute(
        select(UserRole)
        .options(
            selectinload(UserRole.role),
            selectinload(UserRole.assigned_by_user),
        )
        .where(UserRole.id == user_role.id)
    )
    return result.scalars().first()


async def get_user_roles(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    limit: int = 100,
    offset: int = 0,
):
    """Get active roles for a user within an organization."""
    request = GetUserRolesRequest(user_id=UUID(user_id))
    org_uuid = UUID(organization_id)

    # Efficient count query using func.count()
    count_result = await session.execute(
        select(func.count())
        .select_from(UserRole)
        .join(Role)
        .where(
            UserRole.user_id == request.user_id,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
        )
    )
    total = count_result.scalar()

    # Get paginated results with relationships eagerly loaded
    result = await session.execute(
        select(UserRole)
        .join(Role)
        .options(
            selectinload(UserRole.role),
            selectinload(UserRole.assigned_by_user),
        )
        .where(
            UserRole.user_id == request.user_id,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
        )
        .limit(limit)
        .offset(offset)
    )
    user_roles = result.scalars().all()

    return user_roles, total or 0


async def get_all_user_roles_history(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    limit: int = 100,
    offset: int = 0,
):
    """Get role history for a user within an organization."""
    request = GetUserRolesRequest(user_id=UUID(user_id))
    org_uuid = UUID(organization_id)

    # Efficient count query using func.count()
    count_result = await session.execute(
        select(func.count())
        .select_from(UserRole)
        .join(Role)
        .where(
            UserRole.user_id == request.user_id,
            UserRole.organization_id == org_uuid,
        )
    )
    total = count_result.scalar()

    # For history, include deleted (revoked) records
    result = await session.execute(
        select(UserRole)
        .join(Role)
        .options(
            selectinload(UserRole.role),
            selectinload(UserRole.assigned_by_user),
        )
        .where(
            UserRole.user_id == request.user_id,
            UserRole.organization_id == org_uuid,
        )
        .order_by(UserRole.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    user_roles = result.scalars().all()

    return user_roles, total or 0


async def user_has_role(
    session: AsyncSession, user_id: str, role_name: str, organization_id: str
):
    """Check if user has a specific role by name within an organization."""
    # Convert to UUID
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(UserRole)
        .join(Role)
        .where(
            UserRole.user_id == user_uuid,
            Role.name == role_name,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
            Role.deleted_time.is_(None),
        )
    )
    user_role = result.scalars().first()

    return user_role is not None


async def count_users_with_role(
    session: AsyncSession, role_name: str, organization_id: str
) -> int:
    """
    Count the number of active users with a specific role in an organization.

    Args:
        session: SQLAlchemy async session
        role_name: Name of the role to count (e.g., "owner")
        organization_id: UUID of the organization

    Returns:
        Count of users with the specified role
    """
    org_uuid = UUID(organization_id)

    # Use explicit join conditions to avoid ambiguity with assigned_by FK
    result = await session.execute(
        select(func.count(func.distinct(UserRole.user_id)))
        .select_from(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .join(User, UserRole.user_id == User.id)
        .where(
            Role.name == role_name,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
            Role.deleted_time.is_(None),
            User.deleted_time.is_(None),  # Only count non-deleted users
        )
    )
    count = result.scalar()
    return count or 0


async def get_role_by_id(session: AsyncSession, role_id: str) -> Role | None:
    """Get a role by its ID."""
    role_uuid = UUID(role_id) if isinstance(role_id, str) else role_id

    result = await session.execute(
        select(Role).where(Role.id == role_uuid, Role.deleted_time.is_(None))
    )
    return result.scalars().first()


# Role hierarchy - higher number = more privileged
ROLE_HIERARCHY = {
    "viewer": 1,
    "member": 2,
    "manager": 3,
    "admin": 4,
    "owner": 5,
}


async def get_user_role_names(
    session: AsyncSession, user_id: str, organization_id: str
) -> list[str]:
    """Get list of role names for a user within an organization."""
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    result = await session.execute(
        select(Role.name)
        .select_from(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_uuid,
            UserRole.organization_id == org_uuid,
            UserRole.deleted_time.is_(None),
            Role.deleted_time.is_(None),
        )
    )
    return [row[0] for row in result.all()]


def validate_role_hierarchy(current_user_roles: list[str], target_role: str) -> bool:
    """
    Validate that the user can assign the target role based on hierarchy.

    Users can only assign roles at or below their highest privilege level.

    Args:
        current_user_roles: List of role names the current user has
        target_role: The role name they want to assign

    Returns:
        True if assignment is allowed, False otherwise
    """
    if not current_user_roles:
        return False

    # Get max privilege level of current user's roles
    max_user_level = max(ROLE_HIERARCHY.get(r.lower(), 0) for r in current_user_roles)

    # Get target role level (default to highest level + 1 if unknown role)
    target_level = ROLE_HIERARCHY.get(
        target_role.lower(), max(ROLE_HIERARCHY.values()) + 1
    )

    return max_user_level >= target_level
