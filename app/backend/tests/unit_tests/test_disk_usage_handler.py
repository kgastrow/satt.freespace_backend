"""
Unit tests for check_disk_usage_handler cron job.
"""

from collections import namedtuple
from unittest.mock import patch

import pytest

from src.services.cron_handlers import check_disk_usage_handler


DiskUsage = namedtuple("DiskUsage", ["total", "used", "free"])


class TestCheckDiskUsageHandler:
    """Tests for the disk usage monitoring handler."""

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_returns_completed_status_with_disk_stats(
        self,
        mock_disk_usage,
        async_session,
    ):
        """Should return completed status with disk usage stats for each path."""
        # 90% used (90GB of 100GB)
        mock_disk_usage.return_value = DiskUsage(
            total=100 * 1024**3,
            used=90 * 1024**3,
            free=10 * 1024**3,
        )

        result = await check_disk_usage_handler(async_session, {})

        assert result["status"] == "completed"
        assert "disk_usage" in result
        # Default paths are "/" and "/tmp"
        assert "/" in result["disk_usage"]
        assert "/tmp" in result["disk_usage"]

        # Verify stats structure for root path
        root_stats = result["disk_usage"]["/"]
        assert root_stats["usage_percent"] == 90.0
        assert root_stats["total_gb"] == 100.0
        assert root_stats["used_gb"] == 90.0
        assert root_stats["free_gb"] == 10.0
        assert root_stats["alert"] is True  # 90% >= 80% threshold

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_no_alert_when_usage_below_threshold(
        self, mock_disk_usage, async_session
    ):
        """Should not set alert when disk usage is below threshold."""
        # 50% used
        mock_disk_usage.return_value = DiskUsage(
            total=100 * 1024**3,
            used=50 * 1024**3,
            free=50 * 1024**3,
        )

        result = await check_disk_usage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["disk_usage"]["/"]["usage_percent"] == 50.0
        assert result["disk_usage"]["/"]["alert"] is False

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_alert_when_usage_exceeds_threshold(
        self, mock_disk_usage, async_session
    ):
        """Should set alert when disk usage exceeds warning threshold."""
        # 85% used
        mock_disk_usage.return_value = DiskUsage(
            total=100 * 1024**3,
            used=85 * 1024**3,
            free=15 * 1024**3,
        )

        result = await check_disk_usage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["disk_usage"]["/"]["usage_percent"] == 85.0
        assert result["disk_usage"]["/"]["alert"] is True

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_uses_custom_warning_threshold(self, mock_disk_usage, async_session):
        """Should use custom warning threshold from parameters."""
        # 70% used
        mock_disk_usage.return_value = DiskUsage(
            total=100 * 1024**3,
            used=70 * 1024**3,
            free=30 * 1024**3,
        )

        # With 60% threshold, 70% should trigger alert
        result = await check_disk_usage_handler(
            async_session, {"warning_threshold_percent": 60}
        )

        assert result["status"] == "completed"
        assert result["disk_usage"]["/"]["usage_percent"] == 70.0
        assert result["disk_usage"]["/"]["alert"] is True

        # With 80% threshold (default), 70% should not trigger alert
        result = await check_disk_usage_handler(async_session, {})

        assert result["disk_usage"]["/"]["alert"] is False

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_uses_custom_paths(self, mock_disk_usage, async_session):
        """Should check the configured paths from parameters."""
        mock_disk_usage.return_value = DiskUsage(
            total=100 * 1024**3,
            used=50 * 1024**3,
            free=50 * 1024**3,
        )

        custom_paths = ["/data", "/var/log"]
        result = await check_disk_usage_handler(async_session, {"paths": custom_paths})

        assert result["status"] == "completed"
        assert "/data" in result["disk_usage"]
        assert "/var/log" in result["disk_usage"]
        # Default paths should not be present when custom paths specified
        mock_disk_usage.assert_any_call("/data")
        mock_disk_usage.assert_any_call("/var/log")

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_handles_per_path_error(self, mock_disk_usage, async_session):
        """Should record error for individual path that fails."""

        def disk_usage_side_effect(path):
            if path == "/nonexistent":
                raise OSError("No such file or directory")
            return DiskUsage(
                total=100 * 1024**3,
                used=50 * 1024**3,
                free=50 * 1024**3,
            )

        mock_disk_usage.side_effect = disk_usage_side_effect

        result = await check_disk_usage_handler(
            async_session, {"paths": ["/", "/nonexistent"]}
        )

        # Overall status should still be completed
        assert result["status"] == "completed"
        # Valid path should have stats
        assert "usage_percent" in result["disk_usage"]["/"]
        # Invalid path should have error
        assert "error" in result["disk_usage"]["/nonexistent"]
        assert (
            "No such file or directory" in result["disk_usage"]["/nonexistent"]["error"]
        )

    @pytest.mark.asyncio
    @patch("shutil.disk_usage")
    async def test_all_paths_fail_still_returns_completed(
        self, mock_disk_usage, async_session
    ):
        """Should return completed status even when all paths fail with per-path errors."""
        mock_disk_usage.side_effect = OSError("No such file or directory")

        result = await check_disk_usage_handler(async_session, {"paths": ["/"]})

        # Per-path errors are caught, so this results in completed with error in path
        assert result["status"] == "completed"
        assert "error" in result["disk_usage"]["/"]
