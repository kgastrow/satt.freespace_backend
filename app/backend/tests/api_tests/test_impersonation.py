"""
Comprehensive API tests for impersonation endpoints.
Tests super admin user impersonation functionality, including session management,
audit logging, and permission checks.
"""

from datetime import datetime, timezone

from httpx import AsyncClient
import pytest
from sqlalchemy import select

from src.models.audit_log import AuditAction, AuditLog
from src.models.impersonation_session import ImpersonationSession
from src.models.user import User


# ============================================================================
# Fixtures for Impersonation Testing
# ============================================================================


@pytest.fixture
async def inactive_organization(async_session):
    """Create an inactive organization for testing."""
    from src.models.organization import Organization

    org = Organization(
        name="Inactive Organization", slug="inactive-org", is_active=False
    )
    async_session.add(org)
    await async_session.commit()
    await async_session.refresh(org)
    return org


@pytest.fixture
async def target_user(async_session, test_organization):
    """Create a target user to be impersonated."""
    from src.core.security import hash_password

    user = User(
        email="target@test.com",
        password=hash_password("TargetUser123!"),
        email_verified=True,
        organization_id=test_organization.id,
        is_admin=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def unverified_user(async_session, test_organization):
    """Create a user with unverified email."""
    from src.core.security import hash_password

    user = User(
        email="unverified@test.com",
        password=hash_password("Unverified123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def inactive_org_user(async_session, inactive_organization):
    """Create a user in an inactive organization."""
    from src.core.security import hash_password

    user = User(
        email="inactive@test.com",
        password=hash_password("Inactive123!"),
        email_verified=True,
        organization_id=inactive_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def another_super_admin(async_session, test_organization):
    """Create another super admin user."""
    from src.core.security import hash_password

    user = User(
        email="superadmin2@test.com",
        password=hash_password("SuperAdmin123!"),
        email_verified=True,
        organization_id=test_organization.id,
        is_admin=True,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


# ============================================================================
# Start Impersonation Tests
# ============================================================================


class TestStartImpersonation:
    """Tests for POST /api/v1/admin/impersonate/{user_id}."""

    @pytest.mark.asyncio
    async def test_start_impersonation_requires_super_admin(
        self, client: AsyncClient, test_jwt_token, target_user
    ):
        """Test that starting impersonation requires super admin."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_jwt_token},
        )

        # Regular user should not have access
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_start_impersonation_success(
        self, client: AsyncClient, test_super_admin_token, target_user, async_session
    ):
        """Test successful impersonation start."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "impersonation_token" in data
        assert "session" in data
        assert "message" in data
        assert data["session"]["target_user_id"] == str(target_user.id)

        # Verify session was created
        result = await async_session.execute(
            select(ImpersonationSession).where(
                ImpersonationSession.target_user_id == target_user.id
            )
        )
        session = result.scalars().first()
        assert session is not None
        assert session.ended_time is None  # Active session

        # Verify audit log was created
        result = await async_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.IMPERSONATE_START)
        )
        audit = result.scalars().first()
        assert audit is not None
        assert audit.resource_type == "ImpersonationSession"

    @pytest.mark.asyncio
    async def test_cannot_impersonate_self(
        self, client: AsyncClient, test_super_admin_token, test_admin_user
    ):
        """Test that super admin cannot impersonate themselves."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{test_admin_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 400
        assert "yourself" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_impersonate_another_super_admin(
        self, client: AsyncClient, test_super_admin_token, another_super_admin
    ):
        """Test that super admin cannot impersonate another super admin."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{another_super_admin.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 400
        assert "super admin" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_impersonate_unverified_user(
        self, client: AsyncClient, test_super_admin_token, unverified_user
    ):
        """Test that cannot impersonate user with unverified email."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{unverified_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 400
        assert "unverified" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_impersonate_user_in_inactive_org(
        self, client: AsyncClient, test_super_admin_token, inactive_org_user
    ):
        """Test that cannot impersonate user in inactive organization."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{inactive_org_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 400
        assert "inactive" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_impersonate_deleted_user(
        self, client: AsyncClient, test_super_admin_token, target_user, async_session
    ):
        """Test that cannot impersonate soft-deleted user."""
        # Soft delete the target user
        target_user.deleted_time = datetime.now(timezone.utc)
        await async_session.commit()

        response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 400
        assert "deleted" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cannot_impersonate_nonexistent_user(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test that impersonating non-existent user fails."""
        from uuid import uuid4

        fake_user_id = uuid4()
        response = await client.post(
            f"/api/v1/admin/impersonate/{fake_user_id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_starting_new_session_auto_ends_existing(
        self,
        client: AsyncClient,
        test_super_admin_token,
        target_user,
        second_org_user,
        async_session,
    ):
        """Test that starting a new impersonation session auto-ends any existing session."""
        # Start first session
        response1 = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response1.status_code == 200
        first_session_id = response1.json()["session"]["id"]

        # Start second session - should auto-end first
        response2 = await client.post(
            f"/api/v1/admin/impersonate/{second_org_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert response2.status_code == 200
        second_session_id = response2.json()["session"]["id"]

        # Verify first session was ended
        from uuid import UUID

        result = await async_session.execute(
            select(ImpersonationSession).where(
                ImpersonationSession.id == UUID(first_session_id)
            )
        )
        first_session = result.scalars().first()
        assert first_session.ended_time is not None

        # Verify second session is active
        result = await async_session.execute(
            select(ImpersonationSession).where(
                ImpersonationSession.id == UUID(second_session_id)
            )
        )
        second_session = result.scalars().first()
        assert second_session.ended_time is None

    @pytest.mark.asyncio
    async def test_impersonation_token_contains_context(
        self, client: AsyncClient, test_super_admin_token, target_user
    ):
        """Test that impersonation token contains proper context."""
        response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        token = data["impersonation_token"]

        # Decode and verify token contains impersonation context
        import jwt

        from src.core.config import settings

        decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        assert "impersonator_id" in decoded
        assert "impersonation_session_id" in decoded
        assert decoded["user_id"] == str(target_user.id)


# ============================================================================
# End Impersonation Tests
# ============================================================================


class TestEndImpersonation:
    """Tests for POST /api/v1/admin/impersonate/end."""

    @pytest.mark.asyncio
    async def test_end_impersonation_success(
        self, client: AsyncClient, test_super_admin_token, target_user, async_session
    ):
        """Test successful impersonation end."""
        # Start impersonation
        start_response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        assert start_response.status_code == 200
        impersonation_token = start_response.json()["impersonation_token"]

        # End impersonation
        end_response = await client.post(
            "/api/v1/admin/impersonate/end",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        assert end_response.status_code == 200
        data = end_response.json()
        assert "access_token" in data
        assert "session" in data
        assert "message" in data
        assert data["session"]["ended_time"] is not None

        # Verify session was ended
        result = await async_session.execute(
            select(ImpersonationSession).where(
                ImpersonationSession.target_user_id == target_user.id
            )
        )
        session = result.scalars().first()
        assert session is not None
        assert session.ended_time is not None  # Session ended

        # Verify audit log was created
        result = await async_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.IMPERSONATE_END)
        )
        audit = result.scalars().first()
        assert audit is not None
        assert audit.resource_type == "ImpersonationSession"

    @pytest.mark.asyncio
    async def test_end_impersonation_returns_admin_token(
        self, client: AsyncClient, test_super_admin_token, target_user, test_admin_user
    ):
        """Test that ending impersonation returns original admin token."""
        # Start impersonation
        start_response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        impersonation_token = start_response.json()["impersonation_token"]

        # End impersonation
        end_response = await client.post(
            "/api/v1/admin/impersonate/end",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        assert end_response.status_code == 200
        admin_token = end_response.json()["access_token"]

        # Verify admin token works for admin endpoints
        import jwt

        from src.core.config import settings

        decoded = jwt.decode(admin_token, settings.JWT_SECRET, algorithms=["HS256"])
        assert decoded["user_id"] == str(test_admin_user.id)
        assert "impersonator_id" not in decoded  # No impersonation context

    @pytest.mark.asyncio
    async def test_cannot_end_without_impersonating(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test that ending impersonation fails if not currently impersonating."""
        response = await client.post(
            "/api/v1/admin/impersonate/end",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 400
        assert "not currently impersonating" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_audit_log_includes_duration(
        self, client: AsyncClient, test_super_admin_token, target_user, async_session
    ):
        """Test that audit log includes session duration."""
        # Start impersonation
        start_response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        impersonation_token = start_response.json()["impersonation_token"]

        # End impersonation
        await client.post(
            "/api/v1/admin/impersonate/end",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        # Check audit log
        result = await async_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.IMPERSONATE_END)
        )
        audit = result.scalars().first()
        assert audit is not None
        assert audit.changes is not None
        assert "duration_seconds" in audit.changes


# ============================================================================
# Get Current Session Tests
# ============================================================================


class TestGetCurrentSession:
    """Tests for GET /api/v1/admin/impersonate/session."""

    @pytest.mark.asyncio
    async def test_get_current_session_while_impersonating(
        self, client: AsyncClient, test_super_admin_token, target_user
    ):
        """Test getting current session while impersonating."""
        # Start impersonation
        start_response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        impersonation_token = start_response.json()["impersonation_token"]

        # Get current session
        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is True
        assert data["session"]["target_user_id"] == str(target_user.id)
        assert data["session"]["ended_time"] is None

    @pytest.mark.asyncio
    async def test_get_current_session_not_impersonating(
        self, client: AsyncClient, test_super_admin_token
    ):
        """Test getting current session when not impersonating."""
        response = await client.get(
            "/api/v1/admin/impersonate/session",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False
        assert data["session"] is None


# ============================================================================
# Get Impersonation History Tests
# ============================================================================


class TestGetImpersonationHistory:
    """Tests for GET /api/v1/admin/impersonate/history."""

    @pytest.mark.asyncio
    async def test_get_history_requires_super_admin(
        self, client: AsyncClient, test_jwt_token
    ):
        """Test that getting history requires super admin."""
        response = await client.get(
            "/api/v1/admin/impersonate/history",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_history_empty(self, client: AsyncClient, test_super_admin_token):
        """Test getting history with no sessions."""
        response = await client.get(
            "/api/v1/admin/impersonate/history",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_history_with_sessions(
        self, client: AsyncClient, test_super_admin_token, target_user
    ):
        """Test getting history with impersonation sessions."""
        # Create a session
        start_response = await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )
        impersonation_token = start_response.json()["impersonation_token"]

        # End the session
        await client.post(
            "/api/v1/admin/impersonate/end",
            headers={"Authorization": f"Bearer {impersonation_token}"},
        )

        # Get history
        response = await client.get(
            "/api/v1/admin/impersonate/history",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
        assert data["items"][0]["target_user_id"] == str(target_user.id)

    @pytest.mark.asyncio
    async def test_get_history_with_filters(
        self, client: AsyncClient, test_super_admin_token, target_user, test_admin_user
    ):
        """Test getting history with filters."""
        # Create a session
        await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        # Get history filtered by impersonator
        response = await client.get(
            f"/api/v1/admin/impersonate/history?impersonator_id={test_admin_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

        # Get history filtered by target user
        response = await client.get(
            f"/api/v1/admin/impersonate/history?target_user_id={target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_get_history_pagination(
        self, client: AsyncClient, test_super_admin_token, target_user
    ):
        """Test history pagination."""
        # Create multiple sessions
        for _ in range(3):
            start_response = await client.post(
                f"/api/v1/admin/impersonate/{target_user.id}",
                headers={"Authorization": test_super_admin_token},
            )
            impersonation_token = start_response.json()["impersonation_token"]
            await client.post(
                "/api/v1/admin/impersonate/end",
                headers={"Authorization": f"Bearer {impersonation_token}"},
            )

        # Get first page
        response = await client.get(
            "/api/v1/admin/impersonate/history?limit=2&offset=0",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 0

        # Get second page
        response = await client.get(
            "/api/v1/admin/impersonate/history?limit=2&offset=2",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3


# ============================================================================
# Audit Logging Tests
# ============================================================================


class TestImpersonationAuditLogging:
    """Tests for audit logging of impersonation actions."""

    @pytest.mark.asyncio
    async def test_audit_log_uses_impersonator_as_actor(
        self,
        client: AsyncClient,
        test_super_admin_token,
        target_user,
        test_admin_user,
        async_session,
    ):
        """Test that audit logs use impersonator's ID as actor."""
        # Start impersonation
        await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        # Check audit log
        result = await async_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.IMPERSONATE_START)
        )
        audit = result.scalars().first()
        assert audit is not None
        assert (
            audit.actor_id == test_admin_user.id
        )  # Admin is the actor, not target user

    @pytest.mark.asyncio
    async def test_audit_log_includes_ip_and_user_agent(
        self, client: AsyncClient, test_super_admin_token, target_user, async_session
    ):
        """Test that audit logs include IP address and user agent."""
        # Start impersonation with custom headers
        await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={
                "Authorization": test_super_admin_token,
                "User-Agent": "TestClient/1.0",
            },
        )

        # Check audit log
        result = await async_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.IMPERSONATE_START)
        )
        audit = result.scalars().first()
        assert audit is not None
        assert audit.user_agent is not None

    @pytest.mark.asyncio
    async def test_audit_log_organization_context(
        self,
        client: AsyncClient,
        test_super_admin_token,
        target_user,
        test_organization,
        async_session,
    ):
        """Test that audit logs use target user's organization."""
        # Start impersonation
        await client.post(
            f"/api/v1/admin/impersonate/{target_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        # Check audit log
        result = await async_session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.IMPERSONATE_START)
        )
        audit = result.scalars().first()
        assert audit is not None
        assert audit.organization_id == test_organization.id  # Target user's org
