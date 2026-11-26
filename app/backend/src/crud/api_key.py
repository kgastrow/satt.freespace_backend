"""
CRUD operations for API keys.

Provides async functions for managing API keys:
- create_api_key: Generate and store a new API key
- get_api_key_by_id: Retrieve an API key by ID
- get_api_keys_by_organization: List all API keys for an organization
- update_api_key: Update API key name (expiration cannot be modified after creation)
- delete_api_key: Soft delete an API key
- validate_api_key: Validate an API key by prefix and hash
- assign_permissions: Assign permissions to an API key
- remove_permissions: Remove permissions from an API key

All operations enforce organization-level isolation.
"""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional
from uuid import UUID

import bcrypt
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.api_key import ApiKey, ApiKeyScope
from src.models.api_key_permission import ApiKeyPermission
from src.models.permission import Permission


async def create_api_key(
    session: AsyncSession,
    name: str,
    organization_id: str,
    created_by: str,
    expires_at: Optional[datetime] = None,
    scope: ApiKeyScope = ApiKeyScope.USER,
) -> tuple[ApiKey, str]:
    """
    Create a new API key with secure random generation.

    Generates a secure random key, stores bcrypt hash, and returns full key only once.

    Args:
        session: Database session
        name: Human-readable name for the API key
        organization_id: Organization UUID
        created_by: User UUID who created the key
        expires_at: Optional expiration datetime
        scope: The scope of the API key (user, organization, or platform)

    Returns:
        Tuple of (ApiKey model, full_key string)
        The full_key is returned ONLY on creation and cannot be retrieved later

    Raises:
        ValueError: If name already exists in organization
    """
    org_uuid = UUID(organization_id)
    created_by_uuid = UUID(created_by)

    # Check name uniqueness within organization
    existing_result = await session.execute(
        select(ApiKey).where(
            ApiKey.name == name,
            ApiKey.organization_id == org_uuid,
            ApiKey.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        raise ValueError(
            f"API key with name '{name}' already exists in this organization"
        )

    # Generate secure random key (32 bytes = 43 characters in base64)
    full_key = secrets.token_urlsafe(32)

    # Extract prefix (first 8 characters) for identification
    prefix = full_key[:8]

    # Hash the full key for storage
    key_hash = bcrypt.hashpw(full_key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Create API key record
    api_key = ApiKey(
        organization_id=org_uuid,
        name=name,
        key_hash=key_hash,
        prefix=prefix,
        expires_at=expires_at,
        created_by=created_by_uuid,
        scope=scope.value,
    )

    session.add(api_key)
    try:
        await session.commit()
        await session.refresh(api_key)
    except Exception as e:
        await session.rollback()
        raise e

    return api_key, full_key


async def get_api_key_by_id(
    session: AsyncSession, api_key_id: str, organization_id: str
) -> Optional[ApiKey]:
    """
    Get an API key by ID within organization context.

    Args:
        session: Database session
        api_key_id: API key UUID
        organization_id: Organization UUID

    Returns:
        ApiKey model or None if not found
    """
    key_uuid = UUID(api_key_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(ApiKey).where(
            ApiKey.id == key_uuid,
            ApiKey.organization_id == org_uuid,
            ApiKey.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_api_keys_by_organization(
    session: AsyncSession,
    organization_id: str,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[ApiKey], int]:
    """
    Get all API keys for an organization with pagination.

    Args:
        session: Database session
        organization_id: Organization UUID
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        Tuple of (list of ApiKey models, total count)
    """
    org_uuid = UUID(organization_id)

    # Build conditions
    conditions: list[ColumnElement[bool]] = [
        ApiKey.organization_id == org_uuid,
        ApiKey.deleted_time.is_(None),
    ]

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(ApiKey).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query
    result = await session.execute(
        select(ApiKey).where(*conditions).limit(limit).offset(offset)
    )
    api_keys = result.scalars().all()

    return list(api_keys), total


async def update_api_key(
    session: AsyncSession,
    api_key_id: str,
    organization_id: str,
    name: Optional[str] = None,
) -> ApiKey:
    """
    Update API key name.

    The key itself and expiration cannot be changed after creation.

    Args:
        session: Database session
        api_key_id: API key UUID
        organization_id: Organization UUID
        name: New name (optional)

    Returns:
        Updated ApiKey model

    Raises:
        ValueError: If API key not found or name conflicts
    """
    key_uuid = UUID(api_key_id)
    org_uuid = UUID(organization_id)

    # Get existing API key
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.id == key_uuid,
            ApiKey.organization_id == org_uuid,
            ApiKey.deleted_time.is_(None),
        )
    )
    api_key = result.scalars().first()

    if not api_key:
        raise ValueError(f"API key with id {api_key_id} not found")

    # Check name uniqueness if changing name
    if name and name != api_key.name:
        existing_result = await session.execute(
            select(ApiKey).where(
                ApiKey.name == name,
                ApiKey.organization_id == org_uuid,
                ApiKey.deleted_time.is_(None),
            )
        )
        existing = existing_result.scalars().first()

        if existing:
            raise ValueError(
                f"API key with name '{name}' already exists in this organization"
            )

        api_key.name = name

    try:
        await session.commit()
        await session.refresh(api_key)
    except Exception as e:
        await session.rollback()
        raise e

    return api_key


async def delete_api_key(
    session: AsyncSession, api_key_id: str, organization_id: str
) -> ApiKey:
    """
    Soft delete an API key.

    Sets deleted_time to mark the key as revoked.

    Args:
        session: Database session
        api_key_id: API key UUID
        organization_id: Organization UUID

    Returns:
        Deleted ApiKey model

    Raises:
        ValueError: If API key not found
    """
    key_uuid = UUID(api_key_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(ApiKey).where(
            ApiKey.id == key_uuid,
            ApiKey.organization_id == org_uuid,
            ApiKey.deleted_time.is_(None),
        )
    )
    api_key = result.scalars().first()

    if not api_key:
        raise ValueError(f"API key with id {api_key_id} not found")

    api_key.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(api_key)
    except Exception as e:
        await session.rollback()
        raise e

    return api_key


async def validate_api_key(session: AsyncSession, full_key: str) -> Optional[ApiKey]:
    """
    Validate an API key by prefix and hash verification.

    Looks up by prefix, verifies hash, checks expiration and deletion status.

    Args:
        session: Database session
        full_key: The full API key string to validate

    Returns:
        ApiKey model if valid, None if invalid or expired

    Updates last_used_at timestamp on successful validation.
    """
    if len(full_key) < 8:
        return None

    prefix = full_key[:8]

    # Look up by prefix
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.prefix == prefix,
            ApiKey.deleted_time.is_(None),
        )
    )
    api_key = result.scalars().first()

    if not api_key:
        return None

    # Verify hash
    try:
        if not bcrypt.checkpw(
            full_key.encode("utf-8"), api_key.key_hash.encode("utf-8")
        ):
            return None
    except Exception:
        return None

    # Check expiration (handle both timezone-aware and naive datetimes for SQLite compatibility)
    if api_key.expires_at:
        now = datetime.now(timezone.utc)
        expires = api_key.expires_at
        # If expires_at is naive (SQLite), make it aware for comparison
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            return None

    # Update last used timestamp
    api_key.last_used_at = datetime.now(timezone.utc)
    try:
        await session.commit()
        await session.refresh(api_key)
    except Exception:
        await session.rollback()

    return api_key


async def assign_permissions(
    session: AsyncSession,
    api_key_id: str,
    organization_id: str,
    permissions: list[str],
) -> list[ApiKeyPermission]:
    """
    Assign permissions to an API key.

    Creates ApiKeyPermission records for each permission code.
    Skips permissions that are already assigned.

    Args:
        session: Database session
        api_key_id: API key UUID
        organization_id: Organization UUID
        permissions: List of permission codes (e.g., "users:read") to assign

    Returns:
        List of created ApiKeyPermission models

    Raises:
        ValueError: If API key not found or permission code not found
    """
    key_uuid = UUID(api_key_id)
    org_uuid = UUID(organization_id)

    # Verify API key exists
    api_key = await get_api_key_by_id(session, api_key_id, organization_id)
    if not api_key:
        raise ValueError(f"API key with id {api_key_id} not found")

    # Look up permission IDs by code
    permission_result = await session.execute(
        select(Permission).where(
            Permission.code.in_(permissions),
            Permission.deleted_time.is_(None),
        )
    )
    permission_map = {p.code: p.id for p in permission_result.scalars().all()}

    # Validate all permission codes exist
    missing_permissions = set(permissions) - set(permission_map.keys())
    if missing_permissions:
        raise ValueError(
            f"Permission codes not found: {', '.join(missing_permissions)}"
        )

    # Get existing assigned permission IDs
    existing_result = await session.execute(
        select(ApiKeyPermission.permission_id).where(
            ApiKeyPermission.api_key_id == key_uuid,
            ApiKeyPermission.organization_id == org_uuid,
            ApiKeyPermission.deleted_time.is_(None),
        )
    )
    existing_permission_ids = {p for p in existing_result.scalars().all()}

    # Create new permission records
    created_permissions = []
    for permission_code in permissions:
        permission_id = permission_map[permission_code]
        if permission_id not in existing_permission_ids:
            api_key_permission = ApiKeyPermission(
                api_key_id=key_uuid,
                organization_id=org_uuid,
                permission_id=permission_id,
            )
            session.add(api_key_permission)
            created_permissions.append(api_key_permission)

    if created_permissions:
        try:
            await session.commit()
            for perm in created_permissions:
                await session.refresh(perm)
        except Exception as e:
            await session.rollback()
            raise e

    return created_permissions


async def remove_permissions(
    session: AsyncSession,
    api_key_id: str,
    organization_id: str,
    permissions: list[str],
) -> int:
    """
    Remove permissions from an API key.

    Soft deletes ApiKeyPermission records by setting deleted_time.

    Args:
        session: Database session
        api_key_id: API key UUID
        organization_id: Organization UUID
        permissions: List of permission codes to remove

    Returns:
        Number of permissions removed

    Raises:
        ValueError: If API key not found
    """
    key_uuid = UUID(api_key_id)
    org_uuid = UUID(organization_id)

    # Verify API key exists
    api_key = await get_api_key_by_id(session, api_key_id, organization_id)
    if not api_key:
        raise ValueError(f"API key with id {api_key_id} not found")

    # Look up permission IDs by code
    permission_result = await session.execute(
        select(Permission.id).where(
            Permission.code.in_(permissions),
            Permission.deleted_time.is_(None),
        )
    )
    permission_ids = list(permission_result.scalars().all())

    if not permission_ids:
        return 0

    # Find matching api_key_permissions by permission_id
    result = await session.execute(
        select(ApiKeyPermission).where(
            ApiKeyPermission.api_key_id == key_uuid,
            ApiKeyPermission.organization_id == org_uuid,
            ApiKeyPermission.permission_id.in_(permission_ids),
            ApiKeyPermission.deleted_time.is_(None),
        )
    )
    permissions_to_remove = result.scalars().all()

    # Soft delete permissions
    count = 0
    for perm in permissions_to_remove:
        perm.deleted_time = datetime.now(timezone.utc)
        count += 1

    if count > 0:
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e

    return count


async def get_api_keys_expiring_soon(
    session: AsyncSession, now: datetime
) -> list[ApiKey]:
    """Get API keys expiring within 7 days that haven't been warned yet."""
    seven_days = now + timedelta(days=7)
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.expires_at.isnot(None),
            ApiKey.expires_at > now,
            ApiKey.expires_at <= seven_days,
            ApiKey.expiry_warning_sent_at.is_(None),
            ApiKey.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def get_expired_api_keys(session: AsyncSession, now: datetime) -> list[ApiKey]:
    """Get expired API keys that haven't been notified yet."""
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.expires_at.isnot(None),
            ApiKey.expires_at <= now,
            ApiKey.expiry_notice_sent_at.is_(None),
            ApiKey.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def get_api_key_permissions(
    session: AsyncSession, api_key_id: str, organization_id: str
) -> list[str]:
    """
    Get all active permission codes for an API key.

    Args:
        session: Database session
        api_key_id: API key UUID
        organization_id: Organization UUID

    Returns:
        List of permission codes (e.g., "users:read", "api-keys:write")
    """
    key_uuid = UUID(api_key_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(Permission.code)
        .join(
            ApiKeyPermission,
            ApiKeyPermission.permission_id == Permission.id,
        )
        .where(
            ApiKeyPermission.api_key_id == key_uuid,
            ApiKeyPermission.organization_id == org_uuid,
            ApiKeyPermission.deleted_time.is_(None),
            Permission.deleted_time.is_(None),
        )
    )
    return [perm for perm in result.scalars().all()]
