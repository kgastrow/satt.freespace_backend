"""Storage monitoring cron handlers."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger
from src.services.cron._common import MAX_THRESHOLD_PERCENT, MIN_THRESHOLD_PERCENT


# Optional dependency for S3 storage monitoring
try:
    import aioboto3
except ImportError:
    # Create a mock module for testing purposes
    from types import ModuleType

    aioboto3 = ModuleType("aioboto3")  # type: ignore
    aioboto3.Session = None  # type: ignore


async def check_s3_storage_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Monitor S3 storage usage and alert if thresholds are exceeded.

    Parameters:
        warning_threshold_percent (int): Warning threshold (default: 80)
        critical_threshold_percent (int): Critical threshold (default: 95)

    Returns:
        dict with storage stats and any alerts
    """
    from src.services.files.s3_storage import s3_storage

    warning_threshold = parameters.get("warning_threshold_percent", 80)
    critical_threshold = parameters.get("critical_threshold_percent", 95)
    alerts: list[str] = []

    try:
        if not s3_storage or not s3_storage.is_available():
            return {"status": "skipped", "reason": "S3 storage not available"}

        # Get storage stats
        stats = await s3_storage.get_bucket_stats()

        if stats:
            usage_percent = stats.get("usage_percent", 0)

            if usage_percent >= critical_threshold:
                alerts.append(f"CRITICAL: S3 storage at {usage_percent}%")
                logger.error(f"S3 storage critical: {usage_percent}% used")
            elif usage_percent >= warning_threshold:
                alerts.append(f"WARNING: S3 storage at {usage_percent}%")
                logger.warning(f"S3 storage warning: {usage_percent}% used")

            return {
                "status": "completed",
                "usage_percent": usage_percent,
                "total_bytes": stats.get("total_bytes", 0),
                "used_bytes": stats.get("used_bytes", 0),
                "alerts": alerts,
            }

        return {"status": "completed", "alerts": []}

    except Exception as exc:
        logger.error(f"Failed to check S3 storage: {exc}")
        return {"status": "error", "reason": str(exc), "alerts": alerts}


async def check_local_storage_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Monitor local storage usage and alert if thresholds are exceeded.

    Parameters:
        path (str): Path to monitor (default: "/")
        warning_threshold_percent (int): Warning threshold (default: 80)
        critical_threshold_percent (int): Critical threshold (default: 95)

    Returns:
        dict with storage stats and any alerts
    """
    import shutil

    path = parameters.get("path", "/")
    warning_threshold = parameters.get("warning_threshold_percent", 80)
    critical_threshold = parameters.get("critical_threshold_percent", 95)
    alerts: list[str] = []

    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        usage_percent = (usage.used / usage.total) * 100

        if usage_percent >= critical_threshold:
            alerts.append(f"CRITICAL: Local storage at {usage_percent:.1f}%")
            logger.error(f"Local storage critical: {usage_percent:.1f}% used")
        elif usage_percent >= warning_threshold:
            alerts.append(f"WARNING: Local storage at {usage_percent:.1f}%")
            logger.warning(f"Local storage warning: {usage_percent:.1f}% used")

        return {
            "status": "completed",
            "path": path,
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "usage_percent": round(usage_percent, 2),
            "alerts": alerts,
        }

    except Exception as exc:
        logger.error(f"Failed to check local storage: {exc}")
        return {"status": "error", "reason": str(exc), "alerts": alerts}


async def check_disk_usage_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Check disk usage across multiple paths.

    Parameters:
        paths (list): List of paths to check (default: ["/", "/tmp"])
        warning_threshold_percent (int): Warning threshold (default: 80)

    Returns:
        dict with disk usage stats per path
    """
    import shutil

    paths = parameters.get("paths", ["/", "/tmp"])
    warning_threshold = parameters.get("warning_threshold_percent", 80)
    results: dict[str, Any] = {}

    try:
        for path in paths:
            try:
                usage = shutil.disk_usage(path)
                usage_percent = (usage.used / usage.total) * 100
                results[path] = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "usage_percent": round(usage_percent, 2),
                    "alert": usage_percent >= warning_threshold,
                }
            except Exception as e:
                results[path] = {"error": str(e)}

        return {"status": "completed", "disk_usage": results}

    except Exception as exc:
        logger.error(f"Failed to check disk usage: {exc}")
        return {"status": "error", "reason": str(exc)}


async def s3_migration_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Handle S3 storage migration tasks.

    Parameters:
        batch_size (int): Number of files to migrate per run (default: 100)

    Returns:
        dict with migration status
    """
    _batch_size = parameters.get("batch_size", 100)
    files_migrated = 0

    try:
        # This would handle S3 migration tasks
        # For now, return a placeholder
        return {"status": "completed", "files_migrated": files_migrated}

    except Exception as exc:
        logger.error(f"Failed to process S3 migration: {exc}")
        return {"status": "error", "reason": str(exc), "files_migrated": files_migrated}


__all__ = [
    "check_s3_storage_handler",
    "check_local_storage_handler",
    "check_disk_usage_handler",
    "s3_migration_handler",
    # Re-export constants that may be useful to callers
    "MIN_THRESHOLD_PERCENT",
    "MAX_THRESHOLD_PERCENT",
]
