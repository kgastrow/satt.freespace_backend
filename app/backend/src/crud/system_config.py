"""
CRUD operations for SystemConfig model.

System configuration is global (no organization scope) and is managed by super admins.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.system_config import SystemConfig


async def get_all_system_configs(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SystemConfig], int]:
    """
    Get all system configuration entries.

    Args:
        session: Database session
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of configs, total count)
    """
    base_query = select(SystemConfig)

    # Count query
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total_count = count_result.scalar()

    # Data query with eager loading of updated_by relationship
    data_query = (
        base_query.options(selectinload(SystemConfig.updated_by))
        .order_by(SystemConfig.key.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(data_query)
    configs = result.scalars().all()

    return list(configs), total_count or 0


async def get_system_config_by_key(
    session: AsyncSession,
    key: str,
    load_updated_by: bool = False,
) -> Optional[SystemConfig]:
    """
    Get a system config by key.

    Args:
        session: Database session
        key: Config key
        load_updated_by: Whether to eager load the updated_by relationship

    Returns:
        SystemConfig or None if not found
    """
    query = select(SystemConfig).where(SystemConfig.key == key)
    if load_updated_by:
        query = query.options(selectinload(SystemConfig.updated_by))
    result = await session.execute(query)
    return result.scalars().first()


async def update_system_config(
    session: AsyncSession,
    key: str,
    value: Any,
    description: Optional[str] = None,
    updated_by_user_id: Optional[str] = None,
) -> SystemConfig:
    """
    Update or create a system config.

    Args:
        session: Database session
        key: Config key
        value: Config value (will be stored as JSON)
        description: Optional description
        updated_by_user_id: User ID of admin making the change

    Returns:
        The updated or created SystemConfig
    """
    config = await get_system_config_by_key(session, key)

    if config:
        config.value = value
        if description is not None:
            config.description = description
        if updated_by_user_id:
            config.updated_by_user_id = UUID(updated_by_user_id)
    else:
        config = SystemConfig(
            key=key,
            value=value,
            description=description,
            updated_by_user_id=UUID(updated_by_user_id) if updated_by_user_id else None,
        )
        session.add(config)

    try:
        await session.commit()
        await session.refresh(config)
    except Exception as e:
        await session.rollback()
        raise e

    return config


async def delete_system_config(
    session: AsyncSession,
    key: str,
) -> bool:
    """
    Delete a system config.

    Args:
        session: Database session
        key: Config key

    Returns:
        True if deleted, False if not found
    """
    config = await get_system_config_by_key(session, key)

    if not config:
        return False

    await session.delete(config)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return True


async def get_s3_config(session: AsyncSession) -> Optional[dict]:
    """
    Get S3 storage configuration.

    Args:
        session: Database session

    Returns:
        Dictionary with S3 config or None if not configured
    """
    enabled_config = await get_system_config_by_key(session, "storage.s3.enabled")
    if not enabled_config or not enabled_config.value:
        return None

    bucket_config = await get_system_config_by_key(session, "storage.s3.bucket")
    region_config = await get_system_config_by_key(session, "storage.s3.region")
    endpoint_config = await get_system_config_by_key(session, "storage.s3.endpoint_url")

    return {
        "enabled": enabled_config.value,
        "bucket": bucket_config.value if bucket_config else None,
        "region": region_config.value if region_config else "us-east-1",
        "endpoint_url": endpoint_config.value if endpoint_config else None,
    }


async def is_s3_enabled(session: AsyncSession) -> bool:
    """
    Check if S3 storage is enabled and configured.

    Args:
        session: Database session

    Returns:
        True if S3 is enabled and has required config, False otherwise
    """
    config = await get_s3_config(session)
    if not config or not config.get("enabled"):
        return False

    return config.get("bucket") is not None
