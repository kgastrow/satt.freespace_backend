"""
Tests for S3 storage monitoring handler.

Tests the check_s3_storage_handler function including:
- S3 storage availability checks
- Threshold-based alerting (warning and critical)
- Error handling
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.cron.storage import check_s3_storage_handler


class TestCheckS3StorageHandler:
    """Tests for S3 storage monitoring handler."""

    @pytest.mark.asyncio
    async def test_handler_success_under_threshold(
        self, async_session: AsyncSession, test_organization
    ):
        """Test successful execution when storage is under threshold (no alert)."""
        # Mock S3 storage
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "usage_percent": 50.0,  # Under 80% warning threshold
                    "total_bytes": 1073741824,  # 1 GB
                    "used_bytes": 536870912,  # 512 MB
                }
            )

            # Execute handler with default thresholds
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 50.0
        assert result["total_bytes"] == 1073741824
        assert result["used_bytes"] == 536870912
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_warning_threshold_exceeded(
        self, async_session: AsyncSession, test_organization
    ):
        """Test warning alert is generated when warning threshold is exceeded."""
        # Mock S3 storage
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "usage_percent": 85.0,  # Exceeds 80% warning, under 95% critical
                    "total_bytes": 1073741824,
                    "used_bytes": 912680550,
                }
            )

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 85.0
        assert len(result["alerts"]) == 1
        assert "WARNING" in result["alerts"][0]
        assert "85" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_critical_threshold_exceeded(
        self, async_session: AsyncSession, test_organization
    ):
        """Test critical alert is generated when critical threshold is exceeded."""
        # Mock S3 storage
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "usage_percent": 97.0,  # Exceeds 95% critical threshold
                    "total_bytes": 1073741824,
                    "used_bytes": 1041529790,
                }
            )

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 97.0
        assert len(result["alerts"]) == 1
        assert "CRITICAL" in result["alerts"][0]
        assert "97" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_custom_thresholds(
        self, async_session: AsyncSession, test_organization
    ):
        """Test handler respects custom threshold parameters."""
        # Mock S3 storage
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "usage_percent": 65.0,  # Under 80% default but over 60% custom warning
                    "total_bytes": 1073741824,
                    "used_bytes": 697932185,
                }
            )

            # Execute handler with custom thresholds
            result = await check_s3_storage_handler(
                async_session,
                {"warning_threshold_percent": 60, "critical_threshold_percent": 85},
            )

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 65.0
        assert len(result["alerts"]) == 1
        assert "WARNING" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_s3_not_available(self, async_session: AsyncSession):
        """Test handler skips when S3 storage is not available."""
        # Mock S3 storage as not available
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = False

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "skipped"
        assert result["reason"] == "S3 storage not available"

    @pytest.mark.asyncio
    async def test_handler_s3_storage_none(self, async_session: AsyncSession):
        """Test handler skips when s3_storage is None."""
        # Mock S3 storage as None (patched at source module)
        with patch("src.services.files.s3_storage.s3_storage", None):
            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "skipped"
        assert result["reason"] == "S3 storage not available"

    @pytest.mark.asyncio
    async def test_handler_handles_exception(
        self, async_session: AsyncSession, test_organization
    ):
        """Test handler gracefully handles exceptions."""
        # Mock S3 storage to raise exception
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(side_effect=Exception("AWS API Error"))

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "error"
        assert "AWS API Error" in result["reason"]
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_empty_stats(
        self, async_session: AsyncSession, test_organization
    ):
        """Test handler handles empty stats gracefully."""
        # Mock S3 storage returning None stats
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(return_value=None)

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_handler_stats_without_usage_percent(
        self, async_session: AsyncSession, test_organization
    ):
        """Test handler handles stats without usage_percent field."""
        # Mock S3 storage returning stats without usage_percent
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "total_bytes": 1073741824,
                    "used_bytes": 536870912,
                    # No usage_percent field
                }
            )

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 0  # Default value
        assert result["alerts"] == []  # No alerts since usage is 0

    @pytest.mark.asyncio
    async def test_handler_at_exact_warning_threshold(
        self, async_session: AsyncSession, test_organization
    ):
        """Test handler at exactly the warning threshold."""
        # Mock S3 storage
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "usage_percent": 80.0,  # Exactly at warning threshold
                    "total_bytes": 1073741824,
                    "used_bytes": 858993459,
                }
            )

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 80.0
        assert len(result["alerts"]) == 1
        assert "WARNING" in result["alerts"][0]

    @pytest.mark.asyncio
    async def test_handler_at_exact_critical_threshold(
        self, async_session: AsyncSession, test_organization
    ):
        """Test handler at exactly the critical threshold."""
        # Mock S3 storage
        with patch("src.services.files.s3_storage.s3_storage") as mock_s3:
            mock_s3.is_available.return_value = True
            mock_s3.get_bucket_stats = AsyncMock(
                return_value={
                    "usage_percent": 95.0,  # Exactly at critical threshold
                    "total_bytes": 1073741824,
                    "used_bytes": 1020054733,
                }
            )

            # Execute handler
            result = await check_s3_storage_handler(async_session, {})

        # Assert
        assert result["status"] == "completed"
        assert result["usage_percent"] == 95.0
        assert len(result["alerts"]) == 1
        assert "CRITICAL" in result["alerts"][0]
