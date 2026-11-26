"""Notification-related cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def cleanup_old_notifications_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Clean up notifications older than retention period.
    Each organization can have its own retention setting.

    Parameters:
        default_retention_days (int): Default retention period (default: 90)
        batch_size (int): Number of records to process per batch (default: 1000)

    Returns:
        dict with total_deleted and by_organization counts
    """
    from src.models.notification import Notification
    from src.models.organization_notification_settings import (
        OrganizationNotificationSettings,
    )

    default_retention_days = parameters.get("default_retention_days", 90)
    batch_size = parameters.get("batch_size", 1000)
    now = datetime.now(timezone.utc)
    total_deleted = 0
    org_deleted: dict[str, int] = {}

    try:
        # Get all organization notification settings
        result = await session.execute(
            select(OrganizationNotificationSettings).where(
                OrganizationNotificationSettings.notification_retention_days.isnot(None)
            )
        )
        org_settings = result.scalars().all()

        for settings in org_settings:
            retention_days = (
                settings.notification_retention_days or default_retention_days
            )
            cutoff_date = now - timedelta(days=retention_days)
            org_count = 0

            # Process in batches
            while True:
                batch_result = await session.execute(
                    select(Notification.id)
                    .where(
                        Notification.organization_id == settings.organization_id,
                        Notification.created_time < cutoff_date,
                        Notification.deleted_time.is_(None),
                    )
                    .limit(batch_size)
                )
                notif_ids = [row[0] for row in batch_result.all()]

                if not notif_ids:
                    break

                await session.execute(
                    update(Notification)
                    .where(Notification.id.in_(notif_ids))
                    .values(deleted_time=now)
                )
                await session.commit()

                org_count += len(notif_ids)

                if len(notif_ids) < batch_size:
                    break

            if org_count > 0:
                org_deleted[str(settings.organization_id)] = org_count
                total_deleted += org_count

        # Handle system notifications (NULL organization_id)
        default_cutoff = now - timedelta(days=default_retention_days)
        system_count = 0

        while True:
            batch_result = await session.execute(
                select(Notification.id)
                .where(
                    Notification.organization_id.is_(None),
                    Notification.created_time < default_cutoff,
                    Notification.deleted_time.is_(None),
                )
                .limit(batch_size)
            )
            notif_ids = [row[0] for row in batch_result.all()]

            if not notif_ids:
                break

            await session.execute(
                update(Notification)
                .where(Notification.id.in_(notif_ids))
                .values(deleted_time=now)
            )
            await session.commit()

            system_count += len(notif_ids)

            if len(notif_ids) < batch_size:
                break

        if system_count > 0:
            org_deleted["system"] = system_count
            total_deleted += system_count

        logger.info(f"Cleaned up {total_deleted} old notifications")
        return {
            "status": "completed",
            "total_deleted": total_deleted,
            "by_organization": org_deleted,
        }

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup old notifications: {exc}")
        return {
            "status": "error",
            "reason": str(exc),
            "total_deleted": total_deleted,
            "by_organization": org_deleted,
        }


async def check_notification_health_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check the health of notification delivery.

    Parameters:
        failure_threshold_percent (int): Failure rate threshold (default: 10)
        window_hours (int): Time window to check (default: 24)

    Returns:
        dict with notification health stats
    """
    from src.models.notification import Notification

    failure_threshold = parameters.get("failure_threshold_percent", 10)
    window_hours = parameters.get("window_hours", 24)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)
    alerts: list[str] = []

    try:
        # Count total notifications in window
        total_result = await session.execute(
            select(func.count(Notification.id)).where(
                Notification.created_time > window_start,
                Notification.deleted_time.is_(None),
            )
        )
        total_count = total_result.scalar() or 0

        # Count failed notifications
        failed_result = await session.execute(
            select(func.count(Notification.id)).where(
                Notification.created_time > window_start,
                Notification.status == "failed",
                Notification.deleted_time.is_(None),
            )
        )
        failed_count = failed_result.scalar() or 0

        failure_rate = (failed_count / total_count * 100) if total_count > 0 else 0

        if failure_rate >= failure_threshold:
            alerts.append(f"WARNING: Notification failure rate is {failure_rate:.1f}%")
            logger.warning(f"High notification failure rate: {failure_rate:.1f}%")

        return {
            "status": "completed",
            "total_notifications": total_count,
            "failed_notifications": failed_count,
            "failure_rate_percent": round(failure_rate, 2),
            "alerts": alerts,
        }

    except Exception as exc:
        logger.error(f"Failed to check notification health: {exc}")
        return {"status": "error", "reason": str(exc), "alerts": alerts}


__all__ = [
    "cleanup_old_notifications_handler",
    "check_notification_health_handler",
]
