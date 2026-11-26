"""
CRUD operations for ApiKeyRateLimit model.
Rate limits are global (no organization_id) and define rate limits per permission type.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.api_key_rate_limit import ApiKeyRateLimit


async def create_rate_limit(
    session: AsyncSession,
    permission_code: str,
    requests_per_minute: int,
    burst_limit: int,
) -> ApiKeyRateLimit:
    """
    Create a new rate limit configuration for a permission code.

    Args:
        session: Database session
        permission_code: Permission code (e.g., 'users:read')
        requests_per_minute: Maximum requests allowed per minute
        burst_limit: Maximum burst requests allowed

    Returns:
        The created ApiKeyRateLimit

    Raises:
        ValueError: If rate limit for permission code already exists or invalid values
    """
    if requests_per_minute <= 0:
        raise ValueError("requests_per_minute must be greater than 0")

    if burst_limit <= 0:
        raise ValueError("burst_limit must be greater than 0")

    # Check for duplicate permission_code
    existing_result = await session.execute(
        select(ApiKeyRateLimit).where(
            ApiKeyRateLimit.permission_code == permission_code,
            ApiKeyRateLimit.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise ValueError(
            f"Rate limit for permission '{permission_code}' already exists"
        )

    # Create new rate limit
    rate_limit = ApiKeyRateLimit(
        permission_code=permission_code,
        requests_per_minute=requests_per_minute,
        burst_limit=burst_limit,
    )

    session.add(rate_limit)
    try:
        await session.commit()
        await session.refresh(rate_limit)
    except Exception as e:
        await session.rollback()
        raise e

    return rate_limit


async def get_rate_limit_by_permission(
    session: AsyncSession, permission_code: str
) -> Optional[ApiKeyRateLimit]:
    """
    Get a rate limit by permission code.

    Args:
        session: Database session
        permission_code: Permission code (e.g., 'users:read')

    Returns:
        ApiKeyRateLimit if found, None otherwise
    """
    result = await session.execute(
        select(ApiKeyRateLimit).where(
            ApiKeyRateLimit.permission_code == permission_code,
            ApiKeyRateLimit.deleted_time.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_all_rate_limits(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ApiKeyRateLimit], int]:
    """
    Get all rate limits with pagination.

    Args:
        session: Database session
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        Tuple of (list of rate limits, total count)
    """
    conditions: list[ColumnElement[bool]] = [ApiKeyRateLimit.deleted_time.is_(None)]

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(ApiKeyRateLimit).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query with ordering
    result = await session.execute(
        select(ApiKeyRateLimit)
        .where(*conditions)
        .order_by(ApiKeyRateLimit.permission_code)
        .limit(limit)
        .offset(offset)
    )
    rate_limits = result.scalars().all()

    return list(rate_limits), total


async def update_rate_limit(
    session: AsyncSession,
    rate_limit_id: str,
    requests_per_minute: Optional[int] = None,
    burst_limit: Optional[int] = None,
) -> ApiKeyRateLimit:
    """
    Update a rate limit configuration.

    Args:
        session: Database session
        rate_limit_id: Rate limit UUID
        requests_per_minute: Optional new requests per minute
        burst_limit: Optional new burst limit

    Returns:
        Updated ApiKeyRateLimit

    Raises:
        ValueError: If rate limit not found or invalid values
    """
    rl_uuid = UUID(rate_limit_id) if isinstance(rate_limit_id, str) else rate_limit_id

    result = await session.execute(
        select(ApiKeyRateLimit).where(
            ApiKeyRateLimit.id == rl_uuid, ApiKeyRateLimit.deleted_time.is_(None)
        )
    )
    rate_limit = result.scalar_one_or_none()

    if not rate_limit:
        raise ValueError(f"Rate limit with id {rate_limit_id} not found")

    # Update fields if provided
    if requests_per_minute is not None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be greater than 0")
        rate_limit.requests_per_minute = requests_per_minute

    if burst_limit is not None:
        if burst_limit <= 0:
            raise ValueError("burst_limit must be greater than 0")
        rate_limit.burst_limit = burst_limit

    try:
        await session.commit()
        await session.refresh(rate_limit)
    except Exception as e:
        await session.rollback()
        raise e

    return rate_limit


async def delete_rate_limit(
    session: AsyncSession, rate_limit_id: str
) -> ApiKeyRateLimit:
    """
    Soft delete a rate limit.

    Args:
        session: Database session
        rate_limit_id: Rate limit UUID

    Returns:
        Deleted ApiKeyRateLimit

    Raises:
        ValueError: If rate limit not found
    """
    rl_uuid = UUID(rate_limit_id) if isinstance(rate_limit_id, str) else rate_limit_id

    result = await session.execute(
        select(ApiKeyRateLimit).where(
            ApiKeyRateLimit.id == rl_uuid, ApiKeyRateLimit.deleted_time.is_(None)
        )
    )
    rate_limit = result.scalar_one_or_none()

    if not rate_limit:
        raise ValueError(f"Rate limit with id {rate_limit_id} not found")

    # Soft delete
    rate_limit.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(rate_limit)
    except Exception as e:
        await session.rollback()
        raise e

    return rate_limit
