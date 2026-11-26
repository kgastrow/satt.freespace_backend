"""
Unit tests for check_api_key_expiry_handler cron job.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.models.api_key import ApiKey
from src.services.cron.tokens import check_api_key_expiry_handler


class TestCheckApiKeyExpiryHandler:
    """Tests for the API key expiry notification handler."""

    async def _create_api_key(
        self, session, organization, user, name, expires_at, **kwargs
    ):
        key = ApiKey(
            organization_id=organization.id,
            name=name,
            key_hash="fakehash_" + name,
            prefix="pre_" + name[:4],
            expires_at=expires_at,
            created_by=user.id,
            scope="user",
            **kwargs,
        )
        session.add(key)
        await session.commit()
        await session.refresh(key)
        return key

    @pytest.mark.asyncio
    async def test_key_expiring_in_3_days_counted_as_notified(
        self, async_session, test_organization, test_user
    ):
        """Keys expiring within 7 days should be counted as notified."""
        now = datetime.now(timezone.utc)
        await self._create_api_key(
            async_session,
            test_organization,
            test_user,
            "soon-key",
            now + timedelta(days=3),
        )

        result = await check_api_key_expiry_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["notified_count"] == 1
        assert result["expired_count"] == 0

    @pytest.mark.asyncio
    async def test_expired_key_counted(
        self, async_session, test_organization, test_user
    ):
        """Already-expired keys should be counted as expired."""
        now = datetime.now(timezone.utc)
        await self._create_api_key(
            async_session,
            test_organization,
            test_user,
            "expired-key",
            now - timedelta(days=1),
        )

        result = await check_api_key_expiry_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["expired_count"] == 1
        assert result["notified_count"] == 0

    @pytest.mark.asyncio
    async def test_key_without_expiry_is_ignored(
        self, async_session, test_organization, test_user
    ):
        """Keys with no expiry date should not be processed."""
        await self._create_api_key(
            async_session,
            test_organization,
            test_user,
            "no-expiry-key",
            None,
        )

        result = await check_api_key_expiry_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["expired_count"] == 0
        assert result["notified_count"] == 0

    @pytest.mark.asyncio
    async def test_soft_deleted_key_is_ignored(
        self, async_session, test_organization, test_user
    ):
        """Soft-deleted keys should not be processed."""
        now = datetime.now(timezone.utc)
        await self._create_api_key(
            async_session,
            test_organization,
            test_user,
            "deleted-key",
            now + timedelta(days=3),
            deleted_time=now,
        )

        result = await check_api_key_expiry_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["expired_count"] == 0
        assert result["notified_count"] == 0

    @pytest.mark.asyncio
    async def test_key_expiring_in_10_days_not_counted(
        self, async_session, test_organization, test_user
    ):
        """Keys expiring more than 7 days out should not be counted."""
        now = datetime.now(timezone.utc)
        await self._create_api_key(
            async_session,
            test_organization,
            test_user,
            "far-key",
            now + timedelta(days=10),
        )

        result = await check_api_key_expiry_handler(async_session, {})

        assert result["status"] == "completed"
        assert result["expired_count"] == 0
        assert result["notified_count"] == 0

    @pytest.mark.asyncio
    async def test_custom_notify_days_before(
        self, async_session, test_organization, test_user
    ):
        """Custom notify_days_before parameter should be respected."""
        now = datetime.now(timezone.utc)
        # Key expires in 10 days - not notified with default 7 days threshold
        await self._create_api_key(
            async_session,
            test_organization,
            test_user,
            "custom-threshold-key",
            now + timedelta(days=10),
        )

        # With 14 day threshold, this key should be counted
        result = await check_api_key_expiry_handler(
            async_session, {"notify_days_before": 14}
        )

        assert result["status"] == "completed"
        assert result["notified_count"] == 1
        assert result["expired_count"] == 0
