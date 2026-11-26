"""Maintenance and data lifecycle cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def process_hard_deletions_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Process hard deletions for soft-deleted records past retention.

    Parameters:
        retention_days (int): Days before hard delete (default: 30)
        batch_size (int): Number of records to process per batch (default: 100)

    Returns:
        dict with counts by entity type
    """
    retention_days = parameters.get("retention_days", 30)
    batch_size = parameters.get("batch_size", 100)
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=retention_days)
    deleted_counts: dict[str, int] = {}

    try:
        # Import models that support hard deletion
        from src.models.user_otp import UserOTP

        # Hard delete old soft-deleted OTPs
        result = await session.execute(
            select(UserOTP)
            .where(
                UserOTP.deleted_time.isnot(None),
                UserOTP.deleted_time < cutoff_date,
            )
            .limit(batch_size)
        )
        old_otps = result.scalars().all()
        for otp in old_otps:
            await session.delete(otp)
        deleted_counts["otps"] = len(old_otps)

        await session.commit()

        total = sum(deleted_counts.values())
        logger.info(f"Hard deleted {total} old records: {deleted_counts}")
        return {
            "status": "completed",
            "total_deleted": total,
            "by_type": deleted_counts,
        }

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to process hard deletions: {exc}")
        return {"status": "error", "reason": str(exc), "by_type": deleted_counts}


async def update_geoip_database_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Update the GeoIP database if needed.

    Parameters:
        force_update (bool): Force update even if recent (default: False)

    Returns:
        dict with update status
    """
    _force_update = parameters.get("force_update", False)

    try:
        # This would integrate with your GeoIP service
        # For now, return a placeholder
        return {
            "status": "completed",
            "updated": False,
            "reason": "GeoIP update not implemented",
        }

    except Exception as exc:
        logger.error(f"Failed to update GeoIP database: {exc}")
        return {"status": "error", "reason": str(exc)}


__all__ = [
    "process_hard_deletions_handler",
    "update_geoip_database_handler",
]
