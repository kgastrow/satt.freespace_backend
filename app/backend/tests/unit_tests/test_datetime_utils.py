"""
Tests for datetime serialization utilities.
"""

from datetime import datetime, timezone

from src.core.datetime_utils import serialize_datetime, serialize_datetime_required


class TestSerializeDatetime:
    """Tests for the serialize_datetime function."""

    def test_returns_none_for_none_input(self):
        """serialize_datetime should return None when given None."""
        result = serialize_datetime(None)
        assert result is None

    def test_returns_isoformat_for_datetime(self):
        """serialize_datetime should return ISO format string for datetime."""
        dt = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        result = serialize_datetime(dt)
        assert result == "2024-01-15T12:30:45+00:00"

    def test_handles_naive_datetime(self):
        """serialize_datetime should handle naive datetime objects."""
        dt = datetime(2024, 6, 20, 8, 0, 0)
        result = serialize_datetime(dt)
        assert result == "2024-06-20T08:00:00"


class TestSerializeDatetimeRequired:
    """Tests for the serialize_datetime_required function."""

    def test_returns_empty_string_for_none_by_default(self):
        """serialize_datetime_required should return empty string for None by default."""
        result = serialize_datetime_required(None)
        assert result == ""

    def test_returns_custom_default_for_none(self):
        """serialize_datetime_required should return custom default for None."""
        result = serialize_datetime_required(None, default="N/A")
        assert result == "N/A"

    def test_returns_isoformat_for_datetime(self):
        """serialize_datetime_required should return ISO format string for datetime."""
        dt = datetime(2024, 3, 10, 14, 45, 0, tzinfo=timezone.utc)
        result = serialize_datetime_required(dt)
        assert result == "2024-03-10T14:45:00+00:00"

    def test_handles_naive_datetime(self):
        """serialize_datetime_required should handle naive datetime objects."""
        dt = datetime(2024, 12, 25, 0, 0, 0)
        result = serialize_datetime_required(dt)
        assert result == "2024-12-25T00:00:00"
