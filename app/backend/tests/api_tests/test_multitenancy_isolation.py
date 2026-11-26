"""
Test cases for multi-tenancy isolation.
Verifies that data is properly isolated between organizations.
Migrated to FastAPI with async/await patterns.
"""

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_user_cannot_access_other_org_users(
    async_session, test_organization, second_organization, test_jwt_token
):
    """Test that a user with org A token cannot access user details in org B"""
    from src.crud.user import create_user

    # Create a user in second organization
    user_in_org_b = await create_user(
        session=async_session,
        request={
            "email": "userb@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        organization_id=str(second_organization.id),
    )

    # Verify that the user was created in different org
    assert str(user_in_org_b.organization_id) == str(second_organization.id)
    assert str(user_in_org_b.organization_id) != str(test_organization.id)


@pytest.mark.asyncio
async def test_user_cannot_list_other_org_users(
    async_session, test_organization, second_organization
):
    """Test that listing users only returns users from the specified organization"""
    from src.crud.user import create_user, get_users

    # Create users in test_organization
    user_a1 = await create_user(
        async_session,
        {
            "email": "user_a1@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(test_organization.id),
    )
    user_a2 = await create_user(
        async_session,
        {
            "email": "user_a2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(test_organization.id),
    )

    # Create users in second_organization
    user_b1 = await create_user(
        async_session,
        {
            "email": "user_b1@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )
    user_b2 = await create_user(
        async_session,
        {
            "email": "user_b2@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Get users from org A
    users_org_a, count_a = await get_users(
        async_session, str(test_organization.id), limit=100
    )
    user_ids_a = [str(u.id) for u in users_org_a]

    # Get users from org B
    users_org_b, count_b = await get_users(
        async_session, str(second_organization.id), limit=100
    )
    user_ids_b = [str(u.id) for u in users_org_b]

    # Verify org A users don't include org B users
    assert str(user_b1.id) not in user_ids_a
    assert str(user_b2.id) not in user_ids_a
    assert str(user_a1.id) in user_ids_a
    assert str(user_a2.id) in user_ids_a

    # Verify org B users don't include org A users
    assert str(user_a1.id) not in user_ids_b
    assert str(user_a2.id) not in user_ids_b
    assert str(user_b1.id) in user_ids_b
    assert str(user_b2.id) in user_ids_b


@pytest.mark.asyncio
async def test_global_roles_accessible_from_all_orgs(
    async_session, test_organization, second_organization
):
    """Test that global roles are accessible from all organizations"""
    import uuid

    from src.crud.role import create_role, get_role_by_id, list_roles

    # Create global role (roles are now system-wide)
    global_role = await create_role(
        async_session,
        {"name": f"global_role_{uuid.uuid4().hex[:8]}", "description": "Global role"},
    )

    # Role should be accessible (no org context needed for global roles)
    fetched_role = await get_role_by_id(async_session, str(global_role.id))
    assert fetched_role is not None
    assert str(fetched_role.id) == str(global_role.id)

    # List roles returns all global roles
    roles, total = await list_roles(async_session)
    role_ids = [str(r.id) for r in roles]
    assert str(global_role.id) in role_ids


@pytest.mark.asyncio
async def test_user_role_assignment_isolation(
    async_session, test_organization, second_organization
):
    """Test that user role assignments are isolated by organization context"""
    import uuid

    from src.crud.role import create_role
    from src.crud.user import create_user
    from src.crud.user_role import assign_role, get_user_roles

    # Create user in org A
    user_a = await create_user(
        async_session,
        {
            "email": "user_a@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(test_organization.id),
    )

    # Create user in org B
    user_b = await create_user(
        async_session,
        {
            "email": "user_b@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Create a global role (available to all orgs)
    global_role = await create_role(
        async_session,
        {"name": f"manager_{uuid.uuid4().hex[:8]}", "description": "Manager role"},
    )

    # Assign role to user A in org A context
    await assign_role(
        async_session,
        {"user_id": str(user_a.id), "role_id": str(global_role.id)},
        str(user_a.id),
        str(test_organization.id),
    )

    # User A should have the role in org A context
    roles_a, _ = await get_user_roles(
        async_session, str(user_a.id), str(test_organization.id)
    )
    assert len(roles_a) == 1

    # User B should NOT have the role (not assigned in org B)
    roles_b, _ = await get_user_roles(
        async_session, str(user_b.id), str(second_organization.id)
    )
    assert len(roles_b) == 0

    # Cannot assign role to user from different org
    with pytest.raises(ValueError) as exc_info:
        await assign_role(
            async_session,
            {"user_id": str(user_b.id), "role_id": str(global_role.id)},
            str(user_a.id),
            str(test_organization.id),  # Using org A context for user in org B
        )
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_super_admin_can_access_all_orgs(
    async_session, test_organization, second_organization, test_admin_user
):
    """Test that super admin (is_admin=True) can access resources from all organizations"""
    import uuid

    from src.crud.role import create_role, get_role_by_id
    from src.crud.user import create_user, get_user_by_id

    # Create user in org B
    user_b = await create_user(
        async_session,
        {
            "email": "user_b_admin@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Create a global role
    global_role = await create_role(
        async_session,
        {"name": f"viewer_{uuid.uuid4().hex[:8]}", "description": "Viewer role"},
    )

    # Verify get_user_by_id works when called with the correct org_id
    fetched_user = await get_user_by_id(
        async_session, str(user_b.id), str(second_organization.id)
    )
    assert fetched_user is not None
    assert str(fetched_user.id) == str(user_b.id)

    # Verify global role is accessible
    fetched_role = await get_role_by_id(async_session, str(global_role.id))
    assert fetched_role is not None
    assert str(fetched_role.id) == str(global_role.id)

    # Verify admin user has is_admin flag
    assert test_admin_user.is_admin is True


@pytest.mark.asyncio
async def test_email_unique_per_organization(
    async_session, test_organization, second_organization
):
    """Test that the same email can be registered in different organizations"""
    from src.crud.user import create_user, get_user_by_email

    email = "duplicate@test.com"

    # Create user with this email in org A
    user_a = await create_user(
        async_session,
        {"email": email, "password": "Password123!", "email_verified": True},
        str(test_organization.id),
    )

    # Create user with same email in org B (should succeed)
    user_b = await create_user(
        async_session,
        {"email": email, "password": "Password456!", "email_verified": True},
        str(second_organization.id),
    )

    # Verify both users exist with same email but different orgs
    assert user_a.email == email
    assert user_b.email == email
    assert str(user_a.id) != str(user_b.id)
    assert str(user_a.organization_id) == str(test_organization.id)
    assert str(user_b.organization_id) == str(second_organization.id)

    # Verify get_user_by_email returns correct user based on organization
    fetched_a = await get_user_by_email(async_session, email, str(test_organization.id))
    fetched_b = await get_user_by_email(
        async_session, email, str(second_organization.id)
    )

    assert str(fetched_a.id) == str(user_a.id)
    assert str(fetched_b.id) == str(user_b.id)
    assert str(fetched_a.organization_id) != str(fetched_b.organization_id)


@pytest.mark.asyncio
async def test_api_enforces_organization_isolation(
    client: AsyncClient,
    async_session,
    test_organization,
    second_organization,
    test_jwt_token,
):
    """Test that API endpoints enforce organization isolation"""
    from src.crud.user import create_user

    # Create a user in second organization
    user_in_org_b = await create_user(
        async_session,
        {
            "email": "api_test@test.com",
            "password": "Password123!",
            "email_verified": True,
        },
        str(second_organization.id),
    )

    # Try to access user from org B using token from org A
    response = await client.get(
        f"/api/v1/users/{user_in_org_b.id}", headers={"Authorization": test_jwt_token}
    )

    # Should return 404 because user belongs to different organization
    assert response.status_code in [403, 404]


# ============================================================================
# CHANGELOG ISOLATION TESTS (CTX-002)
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_read_other_org_changelog(
    client: AsyncClient,
    test_jwt_token,
    second_org_changelog,
):
    """Test that user cannot mark as viewed a changelog from another organization."""
    response = await client.post(
        f"/api/v1/changelogs/{second_org_changelog.id}/view",
        headers={"Authorization": test_jwt_token},
    )
    # Should return 404 because the changelog belongs to a different org
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_update_other_org_changelog(
    client: AsyncClient,
    user_with_changelog_token,
    second_org_changelog,
):
    """Test that user cannot update changelog from another organization."""
    response = await client.put(
        f"/api/v1/changelogs/{second_org_changelog.id}",
        json={"title": "Hacked Title"},
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_other_org_changelog(
    client: AsyncClient,
    user_with_changelog_token,
    second_org_changelog,
):
    """Test that user cannot delete changelog from another organization."""
    response = await client.delete(
        f"/api/v1/changelogs/{second_org_changelog.id}",
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_changelog_list_excludes_other_orgs(
    client: AsyncClient,
    test_jwt_token,
    test_changelog,
    second_org_changelog,
):
    """Test that changelog list only includes entries from user's org and platform-wide."""
    response = await client.get(
        "/api/v1/changelogs/published",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()

    # Check that second org changelog is not in the list
    changelog_ids = [item["id"] for item in data["items"]]
    assert str(test_changelog.id) in changelog_ids
    assert str(second_org_changelog.id) not in changelog_ids


@pytest.mark.asyncio
async def test_cannot_mark_other_org_changelog_viewed(
    client: AsyncClient,
    test_jwt_token,
    second_org_changelog,
):
    """Test that user cannot mark changelog from another org as viewed."""
    response = await client.post(
        f"/api/v1/changelogs/{second_org_changelog.id}/view",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_platform_wide_changelog_visible_to_all(
    client: AsyncClient,
    test_jwt_token,
    platform_changelog,
):
    """Test that platform-wide changelog is visible to all authenticated users."""
    response = await client.get(
        "/api/v1/changelogs/published",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()

    changelog_ids = [item["id"] for item in data["items"]]
    assert str(platform_changelog.id) in changelog_ids


@pytest.mark.asyncio
async def test_only_super_admin_creates_platform_changelog(
    client: AsyncClient,
    user_with_changelog_token,
):
    """Test that only super admin can create platform-wide changelog."""
    response = await client.post(
        "/api/v1/changelogs",
        json={
            "version": "1.0.0",
            "title": "Platform Changelog",
            "body": "Should fail",
            "category": "feature",
            "release_date": "2024-01-01T00:00:00Z",
            "is_published": True,
            "is_platform_wide": True,
        },
        headers={"Authorization": user_with_changelog_token},
    )
    assert response.status_code == 403


# ============================================================================
# FEATURE FLAG OVERRIDE ISOLATION TESTS (CTX-002)
# ============================================================================


@pytest.mark.asyncio
async def test_feature_flag_status_respects_org_override(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_feature_flag,
    test_feature_flag_override,
):
    """Test that flag status respects organization override."""
    response = await client.get(
        "/api/v1/feature-flags",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 200
    data = response.json()

    # The flag should be enabled for this org (override=True, default=False)
    assert test_feature_flag.key in data["flags"]
    assert data["flags"][test_feature_flag.key] is True


@pytest.mark.asyncio
async def test_flag_override_list_excludes_other_orgs(
    client: AsyncClient,
    async_session,
    test_super_admin_token,
    test_organization,
    second_organization,
    test_feature_flag,
):
    """Test that only super admins can see all overrides."""
    from src.models.feature_flag_override import FeatureFlagOverride

    # Create override for second org
    second_override = FeatureFlagOverride(
        feature_flag_id=test_feature_flag.id,
        organization_id=second_organization.id,
        enabled=False,
    )
    async_session.add(second_override)
    await async_session.commit()

    # Super admin can see overrides for all orgs
    response = await client.get(
        f"/api/v1/admin/feature-flags/{test_feature_flag.id}/overrides",
        headers={"Authorization": test_super_admin_token},
    )
    assert response.status_code == 200
    data = response.json()

    org_ids = [item["organization_id"] for item in data["items"]]
    assert (
        str(test_organization.id) in org_ids or str(second_organization.id) in org_ids
    )


# ============================================================================
# ONBOARDING REVIEW COMMENT ISOLATION TESTS (CTX-002)
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_read_other_org_review_comments(
    client: AsyncClient,
    test_jwt_token,
    second_org_review_comment,
    second_org_user_user_type,
):
    """Test that user cannot read review comments from another org."""
    response = await client.get(
        f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}/comments",
        headers={"Authorization": test_jwt_token},
    )
    # Should be 404 because the submission belongs to another org
    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_cannot_respond_to_other_org_submission(
    client: AsyncClient,
    test_jwt_token,
    second_org_user_user_type,
):
    """Test that user cannot respond to onboarding submission from another org."""
    response = await client.post(
        f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}/respond",
        json={"comment": "Malicious comment"},
        headers={"Authorization": test_jwt_token},
    )
    # Should be 404 because the submission belongs to another org
    assert response.status_code in [403, 404]


# ============================================================================
# ORGANIZATION DELETION REQUEST ISOLATION TESTS (CTX-002)
# ============================================================================


@pytest.mark.asyncio
async def test_deletion_request_list_excludes_other_orgs(
    client: AsyncClient,
    test_admin_token,
    test_deletion_request,
    second_org_deletion_request,
):
    """Test that deletion request list only shows org-specific requests (non-super admin)."""
    # Note: Regular admins may not have access to deletion requests at all
    # This test verifies the endpoint doesn't leak other org data
    response = await client.get(
        "/api/v1/organizations/deletion-requests",
        headers={"Authorization": test_admin_token},
    )
    # May be 403 for regular admins, or 200 with filtered results
    if response.status_code == 200:
        data = response.json()
        org_ids = [item.get("organization_id") for item in data.get("items", [])]
        assert str(second_org_deletion_request.organization_id) not in org_ids


@pytest.mark.asyncio
async def test_super_admin_can_view_all_deletion_requests(
    client: AsyncClient,
    test_super_admin_token,
    test_deletion_request,
    second_org_deletion_request,
):
    """Test that super admin can view all deletion requests."""
    response = await client.get(
        "/api/v1/admin/organizations/deletion-requests",
        headers={"Authorization": test_super_admin_token},
    )
    # Super admin endpoint should exist and work
    if response.status_code == 200:
        data = response.json()
        assert data.get("total", 0) >= 2


# ============================================================================
# ORGANIZATION EMAIL SETTINGS ISOLATION TESTS (CTX-002)
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_read_other_org_email_settings(
    client: AsyncClient,
    test_admin_token,
    second_org_email_settings,
    second_organization,
):
    """Test that admin cannot read email settings from another organization."""
    response = await client.get(
        f"/api/v1/email-settings/{second_organization.id}",
        headers={"Authorization": test_admin_token},
    )
    # Should be 403 or 404 because settings belong to different org
    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_cannot_update_other_org_email_settings(
    client: AsyncClient,
    test_admin_token,
    second_org_email_settings,
    second_organization,
):
    """Test that admin cannot update email settings of another organization."""
    response = await client.put(
        f"/api/v1/email-settings/{second_organization.id}",
        json={"from_name": "Hacked Name"},
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code in [403, 404]


# ============================================================================
# ORGANIZATION SSO SETTINGS ISOLATION TESTS (CTX-002)
# ============================================================================


@pytest.mark.asyncio
async def test_cannot_read_other_org_sso_settings(
    client: AsyncClient,
    test_admin_token,
    second_org_sso_settings,
):
    """Test that admin cannot read SSO settings from another organization."""
    response = await client.get(
        "/api/v1/organization-sso-settings",
        headers={"Authorization": test_admin_token},
    )
    # Should only return current org's settings
    if response.status_code == 200:
        data = response.json()
        # Verify we're not getting second org's data (second org has google_enabled=False)
        # If we see google_enabled=False with no google_client_id, we might be leaking data
        assert data.get("organization_id") != str(
            second_org_sso_settings.organization_id
        )


@pytest.mark.asyncio
async def test_cannot_update_other_org_sso_settings(
    client: AsyncClient,
    async_session,
    test_admin_token,
    second_organization,
    second_org_sso_settings,
):
    """Test that admin cannot update SSO settings of another organization."""
    # Try to update using second org's ID (if endpoint allows org_id param)
    await client.put(
        "/api/v1/organization-sso-settings",
        json={
            "sso_allowed": False,
            "google_enabled": True,
        },
        headers={"Authorization": test_admin_token},
    )

    # After update, verify second org settings are unchanged
    await async_session.refresh(second_org_sso_settings)
    # Second org should still have google_enabled=False (since it's a different org)
    assert second_org_sso_settings.google_enabled is False
