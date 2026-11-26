"""
DateTime serialization utilities.

Provides consistent datetime serialization patterns across the codebase.
"""

from datetime import datetime


def serialize_datetime(dt: datetime | None) -> str | None:
    """
    Serialize a datetime to ISO 8601 format string.

    Args:
        dt: The datetime to serialize, or None.

    Returns:
        ISO 8601 formatted string if dt is not None, otherwise None.

    Example:
        >>> from datetime import datetime, timezone
        >>> serialize_datetime(datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))
        '2024-01-15T12:00:00+00:00'
        >>> serialize_datetime(None)
        None
    """
    return dt.isoformat() if dt else None


def serialize_datetime_required(dt: datetime | None, default: str = "") -> str:
    """
    Serialize a datetime to ISO 8601 format string, with a default for None values.

    Use this when the field is required and cannot be None in the response.

    Args:
        dt: The datetime to serialize, or None.
        default: The default string to return if dt is None. Defaults to empty string.

    Returns:
        ISO 8601 formatted string if dt is not None, otherwise the default value.

    Example:
        >>> from datetime import datetime, timezone
        >>> serialize_datetime_required(datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc))
        '2024-01-15T12:00:00+00:00'
        >>> serialize_datetime_required(None)
        ''
    """
    return dt.isoformat() if dt else default
