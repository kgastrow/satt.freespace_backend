"""
Test cases for invitation API endpoints.
Tests create, list, validate token, revoke, and permission/tenant isolation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest


# ============================================================================
# CREATE INVITATION
# ============================================================================


@pytest.mark.asyncio
async def test_create_invitation_success(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_admin_token,
):
    """Test creating an invitation as a super admin."""
    with patch(
        "src.services.tasks.task_queue.enqueue_invitation_email",
        new_callable=AsyncMock,
    ) as mock_email:
        response = await client.post(
            "/api/v1/invitations",
            json={"email": "newinvite@example.com"},
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Invitation sent successfully"
    assert data["invitation"]["email"] == "newinvite@example.com"
    assert data["invitation"]["id"] is not None
    assert data["invitation"]["invited_by_user_id"] == str(test_admin_user.id)
    mock_email.assert_called_once()


@pytest.mark.asyncio
async def test_create_invitation_with_roles(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_token,
    test_role,
):
    """Test creating an invitation with pre-assigned role IDs."""
    role_id = str(test_role.id)

    with patch(
        "src.services.tasks.task_queue.enqueue_invitation_email",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            "/api/v1/invitations",
            json={
                "email": "withroles@example.com",
                "role_ids": [role_id],
            },
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["invitation"]["role_ids"] == [role_id]


@pytest.mark.asyncio
async def test_create_invitation_duplicate_conflict(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_token,
):
    """Test that creating a duplicate pending invitation returns 409."""
    with patch(
        "src.services.tasks.task_queue.enqueue_invitation_email",
        new_callable=AsyncMock,
    ):
        await client.post(
            "/api/v1/invitations",
            json={"email": "dupe@example.com"},
            headers={"Authorization": test_admin_token},
        )

        response = await client.post(
            "/api/v1/invitations",
            json={"email": "dupe@example.com"},
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_invitation_requires_auth(client: AsyncClient):
    """Test that creating an invitation requires authentication."""
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "noauth@example.com"},
    )

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_create_invitation_requires_permission(
    client: AsyncClient,
    async_session,
    test_organization,
    test_jwt_token,
):
    """Test that a regular user without users:write permission is rejected."""
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "noperm@example.com"},
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_invitation_invalid_email(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_token,
):
    """Test that an invalid email is rejected by validation."""
    response = await client.post(
        "/api/v1/invitations",
        json={"email": "not-an-email"},
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 422


# ============================================================================
# LIST INVITATIONS
# ============================================================================


@pytest.mark.asyncio
async def test_list_invitations_success(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_admin_token,
):
    """Test listing pending invitations."""
    from src.crud.user_invitation import create_invitation

    await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="list1@example.com",
        invited_by_user_id=str(test_admin_user.id),
    )
    await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="list2@example.com",
        invited_by_user_id=str(test_admin_user.id),
    )
    await async_session.commit()

    response = await client.get(
        "/api/v1/invitations",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_invitations_requires_auth(client: AsyncClient):
    """Test that listing invitations requires authentication."""
    response = await client.get("/api/v1/invitations")

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_list_invitations_requires_permission(
    client: AsyncClient,
    async_session,
    test_organization,
    test_jwt_token,
):
    """Test that a regular user without users:read permission is rejected."""
    response = await client.get(
        "/api/v1/invitations",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_invitations_tenant_isolation(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    test_admin_user,
    test_admin_token,
):
    """Test that listing only returns invitations for the authenticated user's org."""
    from src.crud.user import create_user
    from src.crud.user_invitation import create_invitation

    # Create invitation in org A
    await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="org_a_invite@example.com",
        invited_by_user_id=str(test_admin_user.id),
    )

    # Create invitation in org B
    user_b = await create_user(
        async_session,
        {"email": "orgb_admin@test.com", "password": "Password123!"},
        str(second_organization.id),
    )
    await create_invitation(
        session=async_session,
        organization_id=str(second_organization.id),
        email="org_b_invite@example.com",
        invited_by_user_id=str(user_b.id),
    )
    await async_session.commit()

    # List as org A admin
    response = await client.get(
        "/api/v1/invitations",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["email"] == "org_a_invite@example.com"


# ============================================================================
# VALIDATE TOKEN (PUBLIC)
# ============================================================================


@pytest.mark.asyncio
async def test_validate_token_success(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
):
    """Test validating a valid invitation token (public endpoint)."""
    from src.crud.user_invitation import create_invitation

    invitation = await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="validate@example.com",
        invited_by_user_id=str(test_user.id),
    )
    await async_session.commit()

    response = await client.get(f"/api/v1/invitations/validate/{invitation.token}")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "validate@example.com"
    assert data["organization_slug"] == "test-org"
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_validate_token_invalid(client: AsyncClient):
    """Test validating a nonexistent token returns 404."""
    response = await client.get("/api/v1/invitations/validate/nonexistent-token-xyz")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_validate_token_expired(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
):
    """Test validating an expired token returns 404."""
    from src.crud.user_invitation import create_invitation

    invitation = await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="expired@example.com",
        invited_by_user_id=str(test_user.id),
    )
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await async_session.commit()

    response = await client.get(f"/api/v1/invitations/validate/{invitation.token}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_validate_token_accepted(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
):
    """Test validating an already-accepted token returns 404."""
    from src.crud.user_invitation import accept_invitation, create_invitation

    invitation = await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="already-accepted@example.com",
        invited_by_user_id=str(test_user.id),
    )
    await accept_invitation(session=async_session, token=invitation.token)
    await async_session.commit()

    response = await client.get(f"/api/v1/invitations/validate/{invitation.token}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_validate_token_no_auth_required(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
):
    """Test that the validate endpoint works without authentication."""
    from src.crud.user_invitation import create_invitation

    invitation = await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="public@example.com",
        invited_by_user_id=str(test_user.id),
    )
    await async_session.commit()

    # No Authorization header
    response = await client.get(f"/api/v1/invitations/validate/{invitation.token}")

    assert response.status_code == 200


# ============================================================================
# REVOKE INVITATION
# ============================================================================


@pytest.mark.asyncio
async def test_revoke_invitation_success(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_user,
    test_admin_token,
):
    """Test revoking an invitation as a super admin."""
    from src.crud.user_invitation import create_invitation

    invitation = await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="to-revoke@example.com",
        invited_by_user_id=str(test_admin_user.id),
    )
    await async_session.commit()

    response = await client.delete(
        f"/api/v1/invitations/{invitation.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Invitation revoked successfully"


@pytest.mark.asyncio
async def test_revoke_invitation_not_found(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_token,
):
    """Test revoking a nonexistent invitation returns 404."""
    from uuid import uuid4

    response = await client.delete(
        f"/api/v1/invitations/{uuid4()}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoke_invitation_requires_auth(client: AsyncClient):
    """Test that revoking an invitation requires authentication."""
    from uuid import uuid4

    response = await client.delete(f"/api/v1/invitations/{uuid4()}")

    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_revoke_invitation_requires_permission(
    client: AsyncClient,
    async_session,
    test_organization,
    test_user,
    test_jwt_token,
):
    """Test that a regular user without users:write permission cannot revoke."""
    from src.crud.user_invitation import create_invitation

    invitation = await create_invitation(
        session=async_session,
        organization_id=str(test_organization.id),
        email="cant-revoke@example.com",
        invited_by_user_id=str(test_user.id),
    )
    await async_session.commit()

    response = await client.delete(
        f"/api/v1/invitations/{invitation.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_revoke_invitation_tenant_isolation(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    test_admin_user,
    test_admin_token,
):
    """Test that an admin cannot revoke an invitation from a different org."""
    from src.crud.user import create_user
    from src.crud.user_invitation import create_invitation

    user_b = await create_user(
        async_session,
        {"email": "orgb_admin2@test.com", "password": "Password123!"},
        str(second_organization.id),
    )
    invitation = await create_invitation(
        session=async_session,
        organization_id=str(second_organization.id),
        email="cross-org-revoke@example.com",
        invited_by_user_id=str(user_b.id),
    )
    await async_session.commit()

    # Try to revoke org B's invitation with org A's admin token
    response = await client.delete(
        f"/api/v1/invitations/{invitation.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404
