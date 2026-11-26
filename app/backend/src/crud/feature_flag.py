"""
CRUD operations for FeatureFlag and FeatureFlagOverride models.
Feature flags are global, while overrides are tenant-scoped.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.feature_flag import FeatureFlag
from src.models.feature_flag_override import FeatureFlagOverride
from src.models.organization import Organization
from src.services.feature_flag_cache import feature_flag_cache


# FeatureFlag CRUD operations


async def create_feature_flag(session: AsyncSession, data: dict) -> FeatureFlag:
    """Create a new global feature flag."""
    key = data.get("key")
    if not key:
        raise ValueError("key is required")

    existing_result = await session.execute(
        select(FeatureFlag).where(
            FeatureFlag.key == key, FeatureFlag.deleted_time.is_(None)
        )
    )
    if existing_result.scalars().first():
        raise ValueError(f"Feature flag with key '{key}' already exists")

    flag = FeatureFlag(
        key=key,
        name=data.get("name", key),
        description=data.get("description"),
        default_enabled=data.get("default_enabled", False),
    )
    session.add(flag)
    await session.commit()
    await session.refresh(flag)
    return flag


async def get_feature_flag_by_id(
    session: AsyncSession, flag_id: str
) -> FeatureFlag | None:
    """Get a feature flag by ID."""
    result = await session.execute(
        select(FeatureFlag).where(
            FeatureFlag.id == UUID(flag_id), FeatureFlag.deleted_time.is_(None)
        )
    )
    return result.scalars().first()


async def get_feature_flag_by_key(
    session: AsyncSession, key: str
) -> FeatureFlag | None:
    """Get a feature flag by key."""
    result = await session.execute(
        select(FeatureFlag).where(
            FeatureFlag.key == key, FeatureFlag.deleted_time.is_(None)
        )
    )
    return result.scalars().first()


async def get_all_feature_flags(
    session: AsyncSession, limit: int = 100, offset: int = 0
) -> tuple[list[FeatureFlag], int]:
    """Get all feature flags with pagination."""
    count_result = await session.execute(
        select(func.count())
        .select_from(FeatureFlag)
        .where(FeatureFlag.deleted_time.is_(None))
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(FeatureFlag)
        .where(FeatureFlag.deleted_time.is_(None))
        .order_by(FeatureFlag.key)
        .limit(limit)
        .offset(offset)
    )
    flags = result.scalars().all()
    return list(flags), total


async def get_all_feature_flags_with_overrides(
    session: AsyncSession, limit: int = 100, offset: int = 0
) -> tuple[list[dict], int]:
    """Get all feature flags with their overrides and org names."""
    count_result = await session.execute(
        select(func.count())
        .select_from(FeatureFlag)
        .where(FeatureFlag.deleted_time.is_(None))
    )
    total = count_result.scalar() or 0

    result = await session.execute(
        select(FeatureFlag)
        .options(selectinload(FeatureFlag.overrides))
        .where(FeatureFlag.deleted_time.is_(None))
        .order_by(FeatureFlag.key)
        .limit(limit)
        .offset(offset)
    )
    flags = result.scalars().all()

    # Get all org IDs from overrides
    org_ids = set()
    for flag in flags:
        for override in flag.overrides:
            if override.deleted_time is None:
                org_ids.add(override.organization_id)

    # Fetch org names in one query
    org_names: dict[UUID, str] = {}
    if org_ids:
        org_result = await session.execute(
            select(Organization.id, Organization.name).where(
                Organization.id.in_(org_ids)
            )
        )
        for org_id, org_name in org_result:
            org_names[org_id] = org_name

    # Build response with override summaries
    flags_with_overrides = []
    for flag in flags:
        active_overrides = [
            {
                "organization_id": override.organization_id,
                "organization_name": org_names.get(override.organization_id, "Unknown"),
                "enabled": override.enabled,
            }
            for override in flag.overrides
            if override.deleted_time is None
        ]
        flags_with_overrides.append(
            {
                "flag": flag,
                "overrides": active_overrides,
            }
        )

    return flags_with_overrides, total


async def update_feature_flag(
    session: AsyncSession, flag_id: str, data: dict
) -> FeatureFlag:
    """Update a feature flag."""
    flag = await get_feature_flag_by_id(session, flag_id)
    if not flag:
        raise ValueError(f"Feature flag with id {flag_id} not found")

    if "key" in data and data["key"] != flag.key:
        existing_result = await session.execute(
            select(FeatureFlag).where(
                FeatureFlag.key == data["key"],
                FeatureFlag.id != flag.id,
                FeatureFlag.deleted_time.is_(None),
            )
        )
        if existing_result.scalars().first():
            raise ValueError(f"Feature flag with key '{data['key']}' already exists")
        flag.key = data["key"]

    if "name" in data:
        flag.name = data["name"]
    if "description" in data:
        flag.description = data["description"]
    if "default_enabled" in data:
        flag.default_enabled = data["default_enabled"]

    await session.commit()
    await session.refresh(flag)

    # Invalidate cache for ALL organizations since default_enabled may have changed
    # Organizations without overrides rely on the default value
    await feature_flag_cache.invalidate_all_feature_flags()

    return flag


async def delete_feature_flag(session: AsyncSession, flag_id: str) -> FeatureFlag:
    """Soft delete a feature flag."""
    flag = await get_feature_flag_by_id(session, flag_id)
    if not flag:
        raise ValueError(f"Feature flag with id {flag_id} not found")

    flag.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(flag)

    # Invalidate cache for ALL organizations since flag is being deleted
    # All orgs (with or without overrides) need to reflect this change
    await feature_flag_cache.invalidate_all_feature_flags()

    return flag


# FeatureFlagOverride CRUD operations


async def create_override(
    session: AsyncSession, flag_id: str, organization_id: str, enabled: bool
) -> FeatureFlagOverride:
    """Create or update an organization override for a feature flag."""
    flag_uuid = UUID(flag_id)
    org_uuid = UUID(organization_id)

    flag = await get_feature_flag_by_id(session, flag_id)
    if not flag:
        raise ValueError(f"Feature flag with id {flag_id} not found")

    existing_result = await session.execute(
        select(FeatureFlagOverride).where(
            FeatureFlagOverride.feature_flag_id == flag_uuid,
            FeatureFlagOverride.organization_id == org_uuid,
            FeatureFlagOverride.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        existing.enabled = enabled
        await session.commit()
        await session.refresh(existing)
        await feature_flag_cache.invalidate_org_feature_flags(organization_id)
        return existing

    override = FeatureFlagOverride(
        feature_flag_id=flag_uuid, organization_id=org_uuid, enabled=enabled
    )
    session.add(override)
    await session.commit()
    await session.refresh(override)
    await feature_flag_cache.invalidate_org_feature_flags(organization_id)
    return override


async def get_override(
    session: AsyncSession, flag_id: str, organization_id: str
) -> FeatureFlagOverride | None:
    """Get an organization's override for a feature flag."""
    result = await session.execute(
        select(FeatureFlagOverride).where(
            FeatureFlagOverride.feature_flag_id == UUID(flag_id),
            FeatureFlagOverride.organization_id == UUID(organization_id),
            FeatureFlagOverride.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def delete_override(
    session: AsyncSession, flag_id: str, organization_id: str
) -> FeatureFlagOverride:
    """Soft delete an organization's override for a feature flag."""
    override = await get_override(session, flag_id, organization_id)
    if not override:
        raise ValueError(
            f"Override for flag {flag_id} and organization {organization_id} not found"
        )

    override.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(override)
    await feature_flag_cache.invalidate_org_feature_flags(organization_id)
    return override


async def get_overrides_for_flag(
    session: AsyncSession, flag_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[FeatureFlagOverride], int]:
    """Get all organization overrides for a specific feature flag with pagination."""
    flag_uuid = UUID(flag_id)

    # Count total
    count_result = await session.execute(
        select(func.count())
        .select_from(FeatureFlagOverride)
        .where(
            FeatureFlagOverride.feature_flag_id == flag_uuid,
            FeatureFlagOverride.deleted_time.is_(None),
        )
    )
    total = count_result.scalar() or 0

    # Fetch paginated results
    result = await session.execute(
        select(FeatureFlagOverride)
        .where(
            FeatureFlagOverride.feature_flag_id == flag_uuid,
            FeatureFlagOverride.deleted_time.is_(None),
        )
        .order_by(FeatureFlagOverride.organization_id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def get_resolved_flags_for_organization(
    session: AsyncSession, organization_id: str
) -> dict[str, bool]:
    """
    Get resolved feature flags for an organization.
    Returns dict mapping flag key to enabled status.
    Override takes precedence over default_enabled.
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(FeatureFlag)
        .options(selectinload(FeatureFlag.overrides))
        .where(FeatureFlag.deleted_time.is_(None))
    )
    flags = result.scalars().all()

    resolved = {}
    for flag in flags:
        override = next(
            (
                o
                for o in flag.overrides
                if o.organization_id == org_uuid and o.deleted_time is None
            ),
            None,
        )
        resolved[flag.key] = override.enabled if override else flag.default_enabled

    return resolved
