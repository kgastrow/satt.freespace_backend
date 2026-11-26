"""Common utilities and constants for cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


# Threshold percentage constants for storage monitoring
MIN_THRESHOLD_PERCENT = 1
MAX_THRESHOLD_PERCENT = 99


def get_cutoff_date(days: int) -> datetime:
    """Calculate cutoff date for cleanup operations."""
    return datetime.now(timezone.utc) - timedelta(days=days)


__all__ = [
    # Re-exports from standard library
    "datetime",
    "timedelta",
    "timezone",
    "Any",
    # Re-exports from SQLAlchemy
    "delete",
    "func",
    "select",
    "update",
    "AsyncSession",
    # Re-exports from project
    "logger",
    # Constants
    "MIN_THRESHOLD_PERCENT",
    "MAX_THRESHOLD_PERCENT",
    # Utilities
    "get_cutoff_date",
]
