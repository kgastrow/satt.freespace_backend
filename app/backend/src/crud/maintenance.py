"""
CRUD operations for maintenance mode configuration and history.

Maintenance mode is stored in SystemConfig with key 'maintenance.mode'.
Maintenance history is tracked in the MaintenanceHistory model.
This is a global configuration (no organization scope) managed by super admins.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.crud.system_config import get_system_config_by_key, update_system_config
from src.models.maintenance_history import MaintenanceHistory, MaintenanceStatus


# Default maintenance configuration
DEFAULT_MAINTENANCE_CONFIG = {
    "enabled": False,
    "message": None,
    "scheduled_start": None,
    "scheduled_end": None,
    "allow_super_admin": True,
    "current_history_id": None,  # Track the current maintenance period
}


async def get_maintenance_config(session: AsyncSession) -> dict:
    """
    Get the current maintenance mode configuration.

    Args:
        session: Database session

    Returns:
        Dictionary with maintenance configuration
    """
    config = await get_system_config_by_key(session, "maintenance.mode")

    if not config:
        return DEFAULT_MAINTENANCE_CONFIG.copy()

    # Return the stored JSON value
    return (
        config.value
        if isinstance(config.value, dict)
        else DEFAULT_MAINTENANCE_CONFIG.copy()
    )


async def update_maintenance_config(
    session: AsyncSession,
    enabled: bool,
    message: Optional[str] = None,
    scheduled_start: Optional[datetime] = None,
    scheduled_end: Optional[datetime] = None,
    allow_super_admin: bool = True,
    updated_by_user_id: Optional[str] = None,
) -> dict:
    """
    Update maintenance mode configuration.

    Args:
        session: Database session
        enabled: Whether maintenance mode is enabled
        message: Custom maintenance message
        scheduled_start: When to automatically start maintenance
        scheduled_end: When to automatically end maintenance
        allow_super_admin: Whether super admins can access during maintenance
        updated_by_user_id: User ID of admin making the change

    Returns:
        Updated maintenance configuration dictionary
    """
    # Build the configuration dictionary
    config_value = {
        "enabled": enabled,
        "message": message,
        "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
        "scheduled_end": scheduled_end.isoformat() if scheduled_end else None,
        "allow_super_admin": allow_super_admin,
    }

    # Update in SystemConfig
    await update_system_config(
        session=session,
        key="maintenance.mode",
        value=config_value,
        description="Maintenance mode configuration",
        updated_by_user_id=updated_by_user_id,
    )

    return config_value


async def is_maintenance_active(session: AsyncSession) -> bool:
    """
    Check if maintenance mode is currently active.

    Args:
        session: Database session

    Returns:
        True if maintenance mode is active, False otherwise
    """
    config = await get_maintenance_config(session)
    return config.get("enabled", False)


# =============================================================================
# Maintenance History CRUD
# =============================================================================


async def create_maintenance_history(
    session: AsyncSession,
    *,
    scheduled_start: Optional[datetime] = None,
    scheduled_end: Optional[datetime] = None,
    actual_start: Optional[datetime] = None,
    message: Optional[str] = None,
    started_by_user_id: Optional[str] = None,
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED,
) -> MaintenanceHistory:
    """
    Create a new maintenance history record.

    Args:
        session: Database session
        scheduled_start: When maintenance was scheduled to start
        scheduled_end: When maintenance was scheduled to end
        actual_start: When maintenance actually started (for immediate maintenance)
        message: Maintenance message
        started_by_user_id: User who initiated the maintenance
        status: Initial status (SCHEDULED or ACTIVE)

    Returns:
        The created MaintenanceHistory record
    """
    history = MaintenanceHistory(
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        actual_start=actual_start,
        message=message,
        started_by_user_id=UUID(started_by_user_id) if started_by_user_id else None,
        status=status.value,
    )
    session.add(history)

    try:
        await session.commit()
        await session.refresh(history)
    except Exception as e:
        await session.rollback()
        raise e

    return history


async def get_maintenance_history_by_id(
    session: AsyncSession,
    history_id: UUID,
) -> Optional[MaintenanceHistory]:
    """
    Get a maintenance history record by ID.

    Args:
        session: Database session
        history_id: The history record ID

    Returns:
        MaintenanceHistory or None if not found
    """
    result = await session.execute(
        select(MaintenanceHistory)
        .options(
            selectinload(MaintenanceHistory.started_by),
            selectinload(MaintenanceHistory.ended_by),
        )
        .where(MaintenanceHistory.id == history_id)
    )
    return result.scalars().first()


async def get_maintenance_history(
    session: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[MaintenanceStatus] = None,
) -> tuple[list[MaintenanceHistory], int]:
    """
    Get maintenance history records with pagination.

    Args:
        session: Database session
        limit: Maximum number of records to return
        offset: Number of records to skip
        status_filter: Optional filter by status

    Returns:
        Tuple of (list of history records, total count)
    """
    base_query = select(MaintenanceHistory)

    if status_filter:
        base_query = base_query.where(MaintenanceHistory.status == status_filter.value)

    # Count query
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query with relationships
    data_query = (
        base_query.options(
            selectinload(MaintenanceHistory.started_by),
            selectinload(MaintenanceHistory.ended_by),
        )
        .order_by(desc(MaintenanceHistory.created_time))
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(data_query)
    histories = result.scalars().all()

    return list(histories), total_count


async def update_maintenance_history(
    session: AsyncSession,
    history_id: UUID,
    *,
    status: Optional[MaintenanceStatus] = None,
    actual_start: Optional[datetime] = None,
    actual_end: Optional[datetime] = None,
    ended_by_user_id: Optional[str] = None,
) -> Optional[MaintenanceHistory]:
    """
    Update a maintenance history record.

    Args:
        session: Database session
        history_id: The history record ID
        status: New status
        actual_start: When maintenance actually started
        actual_end: When maintenance actually ended
        ended_by_user_id: User who ended the maintenance

    Returns:
        Updated MaintenanceHistory or None if not found
    """
    history = await get_maintenance_history_by_id(session, history_id)
    if not history:
        return None

    if status is not None:
        history.status = status.value
    if actual_start is not None:
        history.actual_start = actual_start
    if actual_end is not None:
        history.actual_end = actual_end
    if ended_by_user_id is not None:
        history.ended_by_user_id = UUID(ended_by_user_id)

    try:
        await session.commit()
        await session.refresh(history)
    except Exception as e:
        await session.rollback()
        raise e

    return history


async def get_active_maintenance_history(
    session: AsyncSession,
) -> Optional[MaintenanceHistory]:
    """
    Get the currently active maintenance history record.

    Args:
        session: Database session

    Returns:
        The active MaintenanceHistory or None
    """
    result = await session.execute(
        select(MaintenanceHistory)
        .options(
            selectinload(MaintenanceHistory.started_by),
            selectinload(MaintenanceHistory.ended_by),
        )
        .where(MaintenanceHistory.status == MaintenanceStatus.ACTIVE.value)
        .order_by(desc(MaintenanceHistory.created_time))
        .limit(1)
    )
    return result.scalars().first()


async def start_maintenance(
    session: AsyncSession,
    *,
    scheduled_start: Optional[datetime] = None,
    scheduled_end: Optional[datetime] = None,
    message: Optional[str] = None,
    started_by_user_id: Optional[str] = None,
    is_immediate: bool = False,
) -> MaintenanceHistory:
    """
    Start a maintenance period (create history record).

    Args:
        session: Database session
        scheduled_start: When maintenance was scheduled to start
        scheduled_end: When maintenance is scheduled to end
        message: Maintenance message
        started_by_user_id: User who initiated the maintenance
        is_immediate: Whether this is immediate (not scheduled)

    Returns:
        The created MaintenanceHistory record
    """
    now = datetime.now(timezone.utc)

    return await create_maintenance_history(
        session=session,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        actual_start=now if is_immediate else None,
        message=message,
        started_by_user_id=started_by_user_id,
        status=(
            MaintenanceStatus.ACTIVE if is_immediate else MaintenanceStatus.SCHEDULED
        ),
    )


async def end_maintenance(
    session: AsyncSession,
    history_id: UUID,
    ended_by_user_id: Optional[str] = None,
) -> Optional[MaintenanceHistory]:
    """
    End a maintenance period.

    Args:
        session: Database session
        history_id: The history record ID
        ended_by_user_id: User who ended the maintenance

    Returns:
        Updated MaintenanceHistory or None if not found
    """
    now = datetime.now(timezone.utc)

    return await update_maintenance_history(
        session=session,
        history_id=history_id,
        status=MaintenanceStatus.COMPLETED,
        actual_end=now,
        ended_by_user_id=ended_by_user_id,
    )


async def cancel_scheduled_maintenance(
    session: AsyncSession,
    history_id: UUID,
    ended_by_user_id: Optional[str] = None,
) -> Optional[MaintenanceHistory]:
    """
    Cancel a scheduled maintenance period.

    Args:
        session: Database session
        history_id: The history record ID
        ended_by_user_id: User who cancelled the maintenance

    Returns:
        Updated MaintenanceHistory or None if not found
    """
    return await update_maintenance_history(
        session=session,
        history_id=history_id,
        status=MaintenanceStatus.CANCELLED,
        ended_by_user_id=ended_by_user_id,
    )
