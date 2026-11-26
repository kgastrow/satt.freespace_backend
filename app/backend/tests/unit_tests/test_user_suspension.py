"""
Unit tests for user suspension functionality.
Tests CRUD operations and API endpoints for suspending/unsuspending users.
"""

import pytest

from src.crud.user import suspend_user, unsuspend_user
from src.models.user import SuspensionStatus


@pytest.mark.asyncio
async def test_suspend_user(
    async_session, test_user, test_admin_user, test_organization
):
    """Test suspending a user."""
    org_id = str(test_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    # Suspend the user
    suspended_user = await suspend_user(
        session=async_session,
        user_id=user_id,
        organization_id=org_id,
        suspended_by=admin_id,
        reason="Test suspension reason",
    )

    assert suspended_user is not None
    assert suspended_user.id == test_user.id
    assert suspended_user.suspension_status == SuspensionStatus.SUSPENDED
    assert suspended_user.suspended_time is not None
    assert str(suspended_user.suspended_by) == admin_id
    assert suspended_user.suspension_reason == "Test suspension reason"


@pytest.mark.asyncio
async def test_suspend_user_without_reason(
    async_session, test_user, test_admin_user, test_organization
):
    """Test suspending a user without providing a reason."""
    org_id = str(test_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    suspended_user = await suspend_user(
        session=async_session,
        user_id=user_id,
        organization_id=org_id,
        suspended_by=admin_id,
        reason=None,
    )

    assert suspended_user is not None
    assert suspended_user.suspension_status == SuspensionStatus.SUSPENDED
    assert suspended_user.suspended_time is not None
    assert str(suspended_user.suspended_by) == admin_id
    assert suspended_user.suspension_reason is None


@pytest.mark.asyncio
async def test_unsuspend_user(
    async_session, test_user, test_admin_user, test_organization
):
    """Test unsuspending a previously suspended user."""
    org_id = str(test_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    # First, suspend the user
    await suspend_user(
        session=async_session,
        user_id=user_id,
        organization_id=org_id,
        suspended_by=admin_id,
        reason="Test suspension",
    )

    # Now unsuspend the user
    unsuspended_user = await unsuspend_user(
        session=async_session, user_id=user_id, organization_id=org_id
    )

    assert unsuspended_user is not None
    assert unsuspended_user.id == test_user.id
    assert unsuspended_user.suspension_status == SuspensionStatus.ACTIVE
    assert unsuspended_user.suspended_time is None
    assert unsuspended_user.suspended_by is None
    assert unsuspended_user.suspension_reason is None


@pytest.mark.asyncio
async def test_suspend_nonexistent_user(
    async_session, test_admin_user, test_organization
):
    """Test that suspending a non-existent user raises an error."""
    org_id = str(test_organization.id)
    admin_id = str(test_admin_user.id)
    fake_user_id = "00000000-0000-0000-0000-000000000000"

    with pytest.raises(ValueError, match="not found"):
        await suspend_user(
            session=async_session,
            user_id=fake_user_id,
            organization_id=org_id,
            suspended_by=admin_id,
            reason="Test",
        )


@pytest.mark.asyncio
async def test_unsuspend_nonexistent_user(async_session, test_organization):
    """Test that unsuspending a non-existent user raises an error."""
    org_id = str(test_organization.id)
    fake_user_id = "00000000-0000-0000-0000-000000000000"

    with pytest.raises(ValueError, match="not found"):
        await unsuspend_user(
            session=async_session, user_id=fake_user_id, organization_id=org_id
        )


@pytest.mark.asyncio
async def test_tenant_isolation_suspend(
    async_session, test_user, test_admin_user, test_organization, second_organization
):
    """Test that users cannot be suspended across organizations."""
    org2_id = str(second_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    # Try to suspend a user from org1 using org2's context
    with pytest.raises(ValueError, match="not found"):
        await suspend_user(
            session=async_session,
            user_id=user_id,
            organization_id=org2_id,
            suspended_by=admin_id,
            reason="Cross-org test",
        )


@pytest.mark.asyncio
async def test_tenant_isolation_unsuspend(
    async_session, test_user, test_admin_user, test_organization, second_organization
):
    """Test that users cannot be unsuspended across organizations."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    # First suspend in correct org
    await suspend_user(
        session=async_session,
        user_id=user_id,
        organization_id=org1_id,
        suspended_by=admin_id,
        reason="Test",
    )

    # Try to unsuspend using wrong org context
    with pytest.raises(ValueError, match="not found"):
        await unsuspend_user(
            session=async_session, user_id=user_id, organization_id=org2_id
        )


@pytest.mark.asyncio
async def test_suspended_user_cannot_login(
    async_session, test_user, test_admin_user, test_organization, client
):
    """Test that suspended users cannot log in."""
    from src.crud.organization import get_organization_by_slug

    org_id = str(test_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    # Suspend the user
    await suspend_user(
        session=async_session,
        user_id=user_id,
        organization_id=org_id,
        suspended_by=admin_id,
        reason="Test suspension",
    )
    await async_session.commit()

    # Get org slug for login
    org = await get_organization_by_slug(async_session, test_organization.slug)
    assert org is not None

    # Attempt to login with suspended user
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": org.slug,
        },
    )

    # Should receive 403 Forbidden
    assert response.status_code == 403
    assert "suspended" in response.json()["detail_code"]


@pytest.mark.asyncio
async def test_suspended_user_cannot_refresh_token(
    async_session, test_user, test_admin_user, test_organization, client
):
    """Test that suspended users cannot refresh their tokens."""
    from src.crud.organization import get_organization_by_slug
    from src.crud.refresh_token import create_refresh_token

    org_id = str(test_organization.id)
    admin_id = str(test_admin_user.id)
    user_id = str(test_user.id)

    # Get org
    org = await get_organization_by_slug(async_session, test_organization.slug)
    assert org is not None

    # Create a refresh token before suspension
    refresh_token_value = await create_refresh_token(
        async_session, test_user.id, org_id
    )
    await async_session.commit()

    # Now suspend the user
    await suspend_user(
        session=async_session,
        user_id=user_id,
        organization_id=org_id,
        suspended_by=admin_id,
        reason="Test suspension",
    )
    await async_session.commit()

    # Attempt to refresh token via cookie
    client.cookies.set("refresh_token", refresh_token_value)
    response = await client.post("/api/v1/auth/refresh")
    client.cookies.clear()

    # Should receive 403 Forbidden
    assert response.status_code == 403
    assert "suspended" in response.json()["detail_code"]
