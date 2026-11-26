"""Freespace cron handlers (BF-73, BF-81). OWNER: M9."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger
from src.services.freespace.clock import get_clock
from src.services.freespace.purge import (
    DEFAULT_BATCH_SIZE,
    purge_request_logs,
    run_purge,
)


async def freespace_daily_purge_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Daily retention purge of devices, send history, events, occupancy
    history and request logs. Retention comes from the deployment settings
    (SystemConfig), not from job parameters.

    Parameters:
        batch_size (int): rows per committed batch (default 5000)
    """
    batch_size = int(parameters.get("batch_size", DEFAULT_BATCH_SIZE))
    try:
        result = await run_purge(session, await get_clock(), batch_size=batch_size)
    except Exception as exc:
        await session.rollback()
        logger.error(f"Freespace daily purge failed: {type(exc).__name__}")
        return {"status": "error", "reason": type(exc).__name__}
    status = "completed" if not result.errors else "partial"
    return {"status": status, **result.to_dict()}


async def cleanup_old_request_logs_configured_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Drop-in replacement for ``cleanup_old_request_logs_handler`` that honours
    the ``request_logs.retention_days`` SystemConfig key (default 30)."""
    from src.services.freespace.deployment_settings import get_deployment_settings

    batch_size = int(parameters.get("batch_size", 1000))
    try:
        cfg = await get_deployment_settings(session)
        clock = await get_clock()
        deleted = await purge_request_logs(
            session, clock.now(), cfg.retention_request_logs_days, batch_size
        )
        logger.info(f"Cleaned up {deleted} old request logs")
        return {"status": "completed", "deleted_count": deleted}
    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup old request logs: {exc}")
        return {"status": "error", "reason": str(exc)}


__all__ = [
    "cleanup_old_request_logs_configured_handler",
    "freespace_daily_purge_handler",
]
