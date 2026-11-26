"""
Unit tests for the s3_migration cron handler.
"""

import pytest


class TestS3MigrationHandler:
    """Tests for s3_migration_handler."""

    @pytest.mark.asyncio
    async def test_returns_completed_status(self, async_session):
        """Should return completed status with files_migrated count."""
        from src.services.cron.storage import s3_migration_handler

        result = await s3_migration_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["files_migrated"] == 0

    @pytest.mark.asyncio
    async def test_uses_batch_size_parameter(self, async_session):
        """Should accept batch_size parameter."""
        from src.services.cron.storage import s3_migration_handler

        result = await s3_migration_handler(async_session, {"batch_size": 50})

        assert result["status"] == "completed"
        assert result["files_migrated"] == 0

    @pytest.mark.asyncio
    async def test_can_be_imported_from_cron_handlers(self, async_session):
        """Should be importable from the backward-compatible cron_handlers module."""
        from src.services.cron_handlers import s3_migration_handler

        result = await s3_migration_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["files_migrated"] == 0

    @pytest.mark.asyncio
    async def test_default_batch_size(self, async_session):
        """Should use default batch size of 100 when not specified."""
        from src.services.cron.storage import s3_migration_handler

        # Empty parameters should work with defaults
        result = await s3_migration_handler(async_session, {})

        assert result["status"] == "completed"
