"""
Unit tests for user type expiry feature.

Tests cover:
1. get_user_permissions() excludes expired user types
2. get_expired_user_types() finds expired assignments
3. mark_expiry_notified() sets notification timestamp
4. Cron handler processes expired assignments correctly
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid as uuid_module

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_user_type import OnboardingStatus


class TestUserTypeExpiryQueries:
    """Test expiry-related CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_expired_user_types_finds_expired_assignments(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that get_expired_user_types returns expired assignments."""
        from src.crud.user_type import create as create_user_type
        from src.crud.user_user_type import (
            create,
            get_expired_user_types,
        )

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )

        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        # Create an expired assignment (should be returned)
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            expired_assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        expired_assignment.onboarding_status = OnboardingStatus.APPROVED
        expired_assignment.expires_at = past
        expired_assignment.expiry_notified_at = None
        await async_session.commit()

        # Get expired user types
        expired = await get_expired_user_types(async_session, now)

        # Should find our expired assignment
        assert len(expired) >= 1
        expired_ids = [str(e.id) for e in expired]
        assert str(expired_assignment.id) in expired_ids

    @pytest.mark.asyncio
    async def test_get_expired_user_types_excludes_not_yet_expired(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that get_expired_user_types excludes not-yet-expired assignments."""
        from src.crud.user_type import create as create_user_type
        from src.crud.user_user_type import (
            create,
            get_expired_user_types,
        )

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )

        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        # Create a not-yet-expired assignment (should NOT be returned)
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            future_assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        future_assignment.onboarding_status = OnboardingStatus.APPROVED
        future_assignment.expires_at = future
        future_assignment.expiry_notified_at = None
        await async_session.commit()

        # Get expired user types
        expired = await get_expired_user_types(async_session, now)

        # Should NOT find our future assignment
        expired_ids = [str(e.id) for e in expired]
        assert str(future_assignment.id) not in expired_ids

    @pytest.mark.asyncio
    async def test_get_expired_user_types_excludes_already_notified(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that get_expired_user_types excludes already-notified assignments."""
        from src.crud.user_type import create as create_user_type
        from src.crud.user_user_type import (
            create,
            get_expired_user_types,
        )

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )

        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        # Create an expired but already notified assignment
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            notified_assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        notified_assignment.onboarding_status = OnboardingStatus.APPROVED
        notified_assignment.expires_at = past
        notified_assignment.expiry_notified_at = past  # Already notified
        await async_session.commit()

        # Get expired user types
        expired = await get_expired_user_types(async_session, now)

        # Should NOT find our already-notified assignment
        expired_ids = [str(e.id) for e in expired]
        assert str(notified_assignment.id) not in expired_ids

    @pytest.mark.asyncio
    async def test_get_expired_user_types_excludes_non_approved(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that get_expired_user_types excludes non-approved assignments."""
        from src.crud.user_type import create as create_user_type
        from src.crud.user_user_type import (
            create,
            get_expired_user_types,
        )

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )

        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        # Create an expired but non-approved assignment
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            pending_assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        pending_assignment.onboarding_status = OnboardingStatus.PENDING
        pending_assignment.expires_at = past
        pending_assignment.expiry_notified_at = None
        await async_session.commit()

        # Get expired user types
        expired = await get_expired_user_types(async_session, now)

        # Should NOT find our non-approved assignment
        expired_ids = [str(e.id) for e in expired]
        assert str(pending_assignment.id) not in expired_ids

    @pytest.mark.asyncio
    async def test_mark_expiry_notified_sets_timestamp(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that mark_expiry_notified sets the notification timestamp."""
        from src.crud.user_type import create as create_user_type
        from src.crud.user_user_type import (
            create,
            mark_expiry_notified,
        )

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )

        now = datetime.now(timezone.utc)

        # Create an assignment
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        assert assignment.expiry_notified_at is None

        # Mark as notified
        updated = await mark_expiry_notified(async_session, str(assignment.id), now)

        # Should have the timestamp set
        assert updated is not None
        assert updated.expiry_notified_at.replace(tzinfo=None) == now.replace(
            tzinfo=None
        )


class TestUserPermissionsWithExpiry:
    """Test that get_user_permissions correctly handles expiry."""

    @pytest.mark.asyncio
    async def test_get_user_permissions_excludes_expired_user_type(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that expired user type permissions are excluded."""
        from src.crud.permission import create_permission
        from src.crud.role_permission import get_user_permissions
        from src.crud.user_type import create as create_user_type
        from src.crud.user_type_permission import grant_permission_to_user_type
        from src.crud.user_user_type import create

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )
        permission = await create_permission(
            async_session,
            code=f"expiry:{''.join(chr(97 + (b % 26)) for b in uuid_module.uuid4().bytes[:6])}",
            name="Expiry Test Permission",
        )

        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        # Create user type with permission
        with patch("src.crud.user_type_permission.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            await grant_permission_to_user_type(
                async_session,
                str(user_type.id),
                str(permission.id),
                str(test_user.id),
            )

        # Create expired user-user type assignment
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        assignment.onboarding_status = OnboardingStatus.APPROVED
        assignment.expires_at = past  # Expired
        await async_session.commit()

        # Get user permissions
        with patch("src.crud.role_permission.cache_service") as mock_cache:
            mock_cache.get_user_permissions = AsyncMock(return_value=None)
            mock_cache.set_user_permissions = AsyncMock()
            permissions = await get_user_permissions(
                async_session,
                str(test_user.id),
                str(test_organization.id),
            )

        # Should NOT include the permission from the expired user type
        assert permission.code not in permissions

    @pytest.mark.asyncio
    async def test_get_user_permissions_includes_non_expired_user_type(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that non-expired user type permissions are included."""
        from src.crud.permission import create_permission
        from src.crud.role_permission import get_user_permissions
        from src.crud.user_type import create as create_user_type
        from src.crud.user_type_permission import grant_permission_to_user_type
        from src.crud.user_user_type import create

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )
        permission = await create_permission(
            async_session,
            code=f"expiry:{''.join(chr(97 + (b % 26)) for b in uuid_module.uuid4().bytes[:6])}",
            name="Expiry Test Permission",
        )

        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        # Create user type with permission
        with patch("src.crud.user_type_permission.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            await grant_permission_to_user_type(
                async_session,
                str(user_type.id),
                str(permission.id),
                str(test_user.id),
            )

        # Create non-expired user-user type assignment
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        assignment.onboarding_status = OnboardingStatus.APPROVED
        assignment.expires_at = future  # Not expired yet
        await async_session.commit()

        # Get user permissions
        with patch("src.crud.role_permission.cache_service") as mock_cache:
            mock_cache.get_user_permissions = AsyncMock(return_value=None)
            mock_cache.set_user_permissions = AsyncMock()
            permissions = await get_user_permissions(
                async_session,
                str(test_user.id),
                str(test_organization.id),
            )

        # Should include the permission from the non-expired user type
        assert permission.code in permissions

    @pytest.mark.asyncio
    async def test_get_user_permissions_includes_no_expiry_user_type(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that user type without expiry has permissions included."""
        from src.crud.permission import create_permission
        from src.crud.role_permission import get_user_permissions
        from src.crud.user_type import create as create_user_type
        from src.crud.user_type_permission import grant_permission_to_user_type
        from src.crud.user_user_type import create

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )
        permission = await create_permission(
            async_session,
            code=f"expiry:{''.join(chr(97 + (b % 26)) for b in uuid_module.uuid4().bytes[:6])}",
            name="Expiry Test Permission",
        )

        # Create user type with permission
        with patch("src.crud.user_type_permission.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            await grant_permission_to_user_type(
                async_session,
                str(user_type.id),
                str(permission.id),
                str(test_user.id),
            )

        # Create user-user type assignment without expiry
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        assignment.onboarding_status = OnboardingStatus.APPROVED
        assignment.expires_at = None  # No expiry
        await async_session.commit()

        # Get user permissions
        with patch("src.crud.role_permission.cache_service") as mock_cache:
            mock_cache.get_user_permissions = AsyncMock(return_value=None)
            mock_cache.set_user_permissions = AsyncMock()
            permissions = await get_user_permissions(
                async_session,
                str(test_user.id),
                str(test_organization.id),
            )

        # Should include the permission from the user type without expiry
        assert permission.code in permissions


class TestApprovalWithExpiry:
    """Test approval endpoint with expiry date."""

    @pytest.mark.asyncio
    async def test_update_status_sets_expires_at(
        self,
        async_session: AsyncSession,
        test_organization,
        test_user,
    ):
        """Test that update_status can set expires_at."""
        from src.crud.user_type import create as create_user_type
        from src.crud.user_user_type import create, update_status

        user_type = await create_user_type(
            async_session,
            {
                "name": f"ExpiryType_{uuid_module.uuid4().hex[:8]}",
                "code": f"expiry_type_{uuid_module.uuid4().hex[:8]}",
                "description": "Test user type for expiry",
            },
        )

        now = datetime.now(timezone.utc)
        future = now + timedelta(days=30)

        # Create assignment
        with patch("src.crud.user_user_type.cache_service") as mock_cache:
            mock_cache.invalidate_user_permissions = AsyncMock()
            assignment = await create(
                async_session,
                {"user_id": str(test_user.id), "user_type_id": str(user_type.id)},
                str(test_organization.id),
            )
        assert assignment.expires_at is None

        # Update status with expiry
        updated = await update_status(
            async_session,
            str(assignment.id),
            OnboardingStatus.APPROVED,
            str(test_organization.id),
            onboarded_at=now,
            expires_at=future,
        )

        # Should have the expiry date set
        assert updated.expires_at.replace(tzinfo=None) == future.replace(tzinfo=None)
        assert updated.onboarding_status == OnboardingStatus.APPROVED
