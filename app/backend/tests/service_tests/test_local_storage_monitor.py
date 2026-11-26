"""
Tests for local storage monitoring handler.

Tests the check_local_storage_handler function including:
- Disk usage calculation using shutil.disk_usage
- Warning and critical threshold alerting
- Path-based monitoring
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.cron_handlers import check_local_storage_handler


class TestCheckLocalStorageHandler:
    """Tests for local storage monitoring handler."""

    @pytest.mark.asyncio
    async def test_handler_success_under_threshold(self, async_session: AsyncSession):
        """Test successful execution when storage is under threshold (no alerts)."""
        # Mock disk usage: 50% used
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 50 * (1024**3)  # 50 GB
        mock_usage.free = 50 * (1024**3)  # 50 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["path"] == "/"
        assert result["total_gb"] == 100.0
        assert result["used_gb"] == 50.0
        assert result["free_gb"] == 50.0
        assert result["usage_percent"] == 50.0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_warning_threshold_exceeded(
        self, async_session: AsyncSession
    ):
        """Test warning alert when storage exceeds warning threshold."""
        # Mock disk usage: 85% used (above default 80% warning)
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 85 * (1024**3)  # 85 GB
        mock_usage.free = 15 * (1024**3)  # 15 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["usage_percent"] == 85.0
        assert len(result["alerts"]) == 1
        assert "WARNING" in result["alerts"][0]
        assert "85.0%" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_critical_threshold_exceeded(
        self, async_session: AsyncSession
    ):
        """Test critical alert when storage exceeds critical threshold."""
        # Mock disk usage: 96% used (above default 95% critical)
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 96 * (1024**3)  # 96 GB
        mock_usage.free = 4 * (1024**3)  # 4 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["usage_percent"] == 96.0
        assert len(result["alerts"]) == 1
        assert "CRITICAL" in result["alerts"][0]
        assert "96.0%" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_custom_warning_threshold(self, async_session: AsyncSession):
        """Test custom warning threshold parameter."""
        # Mock disk usage: 75% used
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 75 * (1024**3)  # 75 GB
        mock_usage.free = 25 * (1024**3)  # 25 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            # Custom warning threshold of 70%
            result = await check_local_storage_handler(
                async_session, {"warning_threshold_percent": 70}
            )

        assert result["status"] == "completed"
        assert result["usage_percent"] == 75.0
        assert len(result["alerts"]) == 1
        assert "WARNING" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_custom_critical_threshold(self, async_session: AsyncSession):
        """Test custom critical threshold parameter."""
        # Mock disk usage: 92% used
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 92 * (1024**3)  # 92 GB
        mock_usage.free = 8 * (1024**3)  # 8 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            # Custom critical threshold of 90%
            result = await check_local_storage_handler(
                async_session, {"critical_threshold_percent": 90}
            )

        assert result["status"] == "completed"
        assert result["usage_percent"] == 92.0
        assert len(result["alerts"]) == 1
        assert "CRITICAL" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_custom_path(self, async_session: AsyncSession):
        """Test custom path parameter."""
        mock_usage = MagicMock()
        mock_usage.total = 50 * (1024**3)  # 50 GB
        mock_usage.used = 10 * (1024**3)  # 10 GB
        mock_usage.free = 40 * (1024**3)  # 40 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(
                async_session, {"path": "/var/data"}
            )

        assert result["status"] == "completed"
        assert result["path"] == "/var/data"
        assert result["total_gb"] == 50.0
        assert result["used_gb"] == 10.0
        assert result["free_gb"] == 40.0

    @pytest.mark.asyncio
    async def test_handler_zero_storage_usage(self, async_session: AsyncSession):
        """Test handler works correctly with zero storage usage."""
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 0
        mock_usage.free = 100 * (1024**3)  # 100 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["used_gb"] == 0.0
        assert result["usage_percent"] == 0.0
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_full_storage(self, async_session: AsyncSession):
        """Test handler works correctly with 100% storage usage."""
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 100 * (1024**3)  # 100 GB
        mock_usage.free = 0

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["usage_percent"] == 100.0
        assert len(result["alerts"]) == 1
        assert "CRITICAL" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_error_handling(self, async_session: AsyncSession):
        """Test error handling when disk_usage fails."""
        with patch("shutil.disk_usage", side_effect=OSError("Path not found")):
            result = await check_local_storage_handler(
                async_session, {"path": "/nonexistent"}
            )

        assert result["status"] == "error"
        assert "Path not found" in result["reason"]
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_permission_error(self, async_session: AsyncSession):
        """Test error handling when permission is denied."""
        with patch(
            "shutil.disk_usage", side_effect=PermissionError("Permission denied")
        ):
            result = await check_local_storage_handler(
                async_session, {"path": "/root/secure"}
            )

        assert result["status"] == "error"
        assert "Permission denied" in result["reason"]

    @pytest.mark.asyncio
    async def test_handler_boundary_at_warning_threshold(
        self, async_session: AsyncSession
    ):
        """Test behavior exactly at warning threshold boundary."""
        # Mock disk usage: exactly 80% used (at default warning threshold)
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 80 * (1024**3)  # 80 GB
        mock_usage.free = 20 * (1024**3)  # 20 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["usage_percent"] == 80.0
        # At exactly 80%, warning should be triggered (>= threshold)
        assert len(result["alerts"]) == 1
        assert "WARNING" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_boundary_at_critical_threshold(
        self, async_session: AsyncSession
    ):
        """Test behavior exactly at critical threshold boundary."""
        # Mock disk usage: exactly 95% used (at default critical threshold)
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)  # 100 GB
        mock_usage.used = 95 * (1024**3)  # 95 GB
        mock_usage.free = 5 * (1024**3)  # 5 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["usage_percent"] == 95.0
        # At exactly 95%, critical should be triggered (>= threshold)
        assert len(result["alerts"]) == 1
        assert "CRITICAL" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_just_below_warning_threshold(
        self, async_session: AsyncSession
    ):
        """Test no alert when just below warning threshold."""
        # Mock disk usage: 79.9% used (just below 80% warning)
        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024**3)  # 1000 GB
        mock_usage.used = 799 * (1024**3)  # 799 GB
        mock_usage.free = 201 * (1024**3)  # 201 GB

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["usage_percent"] == 79.9
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_gb_rounding(self, async_session: AsyncSession):
        """Test that GB values are properly rounded to 2 decimal places."""
        # Mock disk usage with values that need rounding
        mock_usage = MagicMock()
        mock_usage.total = int(123.456789 * (1024**3))
        mock_usage.used = int(45.123456 * (1024**3))
        mock_usage.free = int(78.333333 * (1024**3))

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = await check_local_storage_handler(async_session, {})

        assert result["status"] == "completed"
        # Values should be rounded to 2 decimal places
        assert isinstance(result["total_gb"], float)
        assert isinstance(result["used_gb"], float)
        assert isinstance(result["free_gb"], float)
        # Check that rounding was applied (values should have at most 2 decimal places)
        assert result["total_gb"] == round(result["total_gb"], 2)
        assert result["used_gb"] == round(result["used_gb"], 2)
        assert result["free_gb"] == round(result["free_gb"], 2)

    @pytest.mark.asyncio
    async def test_handler_default_parameters(self, async_session: AsyncSession):
        """Test that default parameters are applied correctly."""
        mock_usage = MagicMock()
        mock_usage.total = 100 * (1024**3)
        mock_usage.used = 50 * (1024**3)
        mock_usage.free = 50 * (1024**3)

        with patch("shutil.disk_usage", return_value=mock_usage) as mock_disk:
            result = await check_local_storage_handler(async_session, {})

        # Default path should be "/"
        mock_disk.assert_called_once_with("/")
        assert result["path"] == "/"
