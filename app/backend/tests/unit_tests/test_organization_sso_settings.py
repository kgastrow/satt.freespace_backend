"""
Unit tests for organization SSO settings CRUD operations.
"""

import pytest

from src.crud.organization import create_organization
from src.crud.organization_sso_settings import (
    create_organization_sso_settings,
    get_enabled_providers,
    get_organization_sso_settings,
    update_organization_sso_settings,
)


@pytest.mark.asyncio
async def test_create_organization_sso_settings(async_session):
    """Test that organization SSO settings are auto-created with organization.

    Note: create_organization() now auto-creates default SSO settings,
    so we verify they exist with correct values after organization creation.
    """
    # Create an organization first
    org_data = {"name": "Test Org", "slug": "test-org-sso-1"}
    org = await create_organization(async_session, org_data)

    # Verify SSO settings were auto-created
    settings = await get_organization_sso_settings(async_session, str(org.id))

    assert settings is not None
    assert settings.organization_id == org.id
    assert settings.sso_allowed is False  # Default value
    assert settings.google_enabled is False  # Default value
    assert settings.google_client_id is None
    assert settings.google_client_secret is None
    assert settings.deleted_time is None


@pytest.mark.asyncio
async def test_create_organization_sso_settings_defaults(async_session):
    """Test creating organization SSO settings with defaults.

    Note: create_organization() now auto-creates default SSO settings,
    so we verify those defaults instead of creating new ones.
    """
    # Create an organization first
    org_data = {"name": "Test Org", "slug": "test-org-sso-2"}
    org = await create_organization(async_session, org_data)

    # Get the auto-created SSO settings
    settings = await get_organization_sso_settings(async_session, str(org.id))

    assert settings is not None
    assert settings.organization_id == org.id
    assert settings.google_enabled is False
    assert settings.google_client_id is None
    assert settings.google_client_secret is None


@pytest.mark.asyncio
async def test_create_organization_sso_settings_duplicate(async_session):
    """Test creating duplicate organization SSO settings raises error.

    Note: create_organization() now auto-creates default SSO settings,
    so we test that we can't create when auto-created settings exist.
    """
    # Create an organization first (auto-creates SSO settings)
    org_data = {"name": "Test Org", "slug": "test-org-sso-3"}
    org = await create_organization(async_session, org_data)

    # Try to create SSO settings when they already exist (auto-created)
    settings_data = {"google_enabled": True}
    with pytest.raises(ValueError, match="already exist"):
        await create_organization_sso_settings(
            async_session, str(org.id), settings_data
        )


@pytest.mark.asyncio
async def test_get_organization_sso_settings(async_session):
    """Test retrieving organization SSO settings."""
    # Create an organization first (auto-creates SSO settings)
    org_data = {"name": "Test Org", "slug": "test-org-sso-4"}
    org = await create_organization(async_session, org_data)

    # Update the auto-created SSO settings
    settings_data = {
        "google_enabled": True,
        "google_client_id": "test-client-id",
    }
    updated_settings = await update_organization_sso_settings(
        async_session, str(org.id), settings_data
    )

    # Retrieve settings
    settings = await get_organization_sso_settings(async_session, str(org.id))

    assert settings is not None
    assert settings.id == updated_settings.id
    assert settings.organization_id == org.id
    assert settings.google_enabled is True
    assert settings.google_client_id == "test-client-id"


@pytest.mark.asyncio
async def test_get_organization_sso_settings_not_found(async_session):
    """Test retrieving soft-deleted organization SSO settings returns None."""
    from datetime import datetime, timezone

    # Create an organization first (auto-creates SSO settings)
    org_data = {"name": "Test Org", "slug": "test-org-sso-5"}
    org = await create_organization(async_session, org_data)

    # Soft-delete the auto-created settings
    settings = await get_organization_sso_settings(async_session, str(org.id))
    settings.deleted_time = datetime.now(timezone.utc)
    await async_session.commit()

    # Try to get settings that are soft-deleted
    settings = await get_organization_sso_settings(async_session, str(org.id))

    assert settings is None


@pytest.mark.asyncio
async def test_update_organization_sso_settings(async_session):
    """Test updating organization SSO settings."""
    # Create an organization first (auto-creates SSO settings with google_enabled=False)
    org_data = {"name": "Test Org", "slug": "test-org-sso-6"}
    org = await create_organization(async_session, org_data)

    # Update settings
    update_data = {
        "google_enabled": True,
        "google_client_id": "new-client-id",
        "google_client_secret": "new-client-secret",
    }
    updated_settings = await update_organization_sso_settings(
        async_session, str(org.id), update_data
    )

    assert updated_settings.google_enabled is True
    assert updated_settings.google_client_id == "new-client-id"
    assert updated_settings.google_client_secret == "new-client-secret"


@pytest.mark.asyncio
async def test_update_organization_sso_settings_partial(async_session):
    """Test partially updating organization SSO settings."""
    # Create an organization first (auto-creates SSO settings)
    org_data = {"name": "Test Org", "slug": "test-org-sso-7"}
    org = await create_organization(async_session, org_data)

    # First update: set initial values
    settings_data = {
        "google_enabled": True,
        "google_client_id": "original-client-id",
        "google_client_secret": "original-secret",
    }
    await update_organization_sso_settings(async_session, str(org.id), settings_data)

    # Second update: only update one field
    update_data = {"google_enabled": False}
    updated_settings = await update_organization_sso_settings(
        async_session, str(org.id), update_data
    )

    assert updated_settings.google_enabled is False
    assert updated_settings.google_client_id == "original-client-id"
    assert updated_settings.google_client_secret == "original-secret"


@pytest.mark.asyncio
async def test_update_organization_sso_settings_not_found(async_session):
    """Test updating soft-deleted organization SSO settings raises error."""
    from datetime import datetime, timezone

    # Create an organization first (auto-creates SSO settings)
    org_data = {"name": "Test Org", "slug": "test-org-sso-8"}
    org = await create_organization(async_session, org_data)

    # Soft-delete the auto-created settings
    settings = await get_organization_sso_settings(async_session, str(org.id))
    settings.deleted_time = datetime.now(timezone.utc)
    await async_session.commit()

    # Try to update soft-deleted settings
    update_data = {"google_enabled": True}
    with pytest.raises(ValueError, match="not found"):
        await update_organization_sso_settings(async_session, str(org.id), update_data)


@pytest.mark.asyncio
async def test_get_enabled_providers(async_session):
    """Test getting list of enabled SSO providers."""
    # Create an organization first (auto-creates SSO settings)
    org_data = {"name": "Test Org", "slug": "test-org-sso-9"}
    org = await create_organization(async_session, org_data)

    # Update SSO settings with Google enabled (sso_allowed must be True)
    settings_data = {"sso_allowed": True, "google_enabled": True}
    await update_organization_sso_settings(async_session, str(org.id), settings_data)

    # Get enabled providers
    providers = await get_enabled_providers(async_session, str(org.id))

    assert providers == ["google"]


@pytest.mark.asyncio
async def test_get_enabled_providers_none_enabled(async_session):
    """Test getting enabled providers when none are enabled."""
    # Create an organization first (auto-creates SSO settings with google_enabled=False)
    org_data = {"name": "Test Org", "slug": "test-org-sso-10"}
    org = await create_organization(async_session, org_data)

    # SSO settings are auto-created with google_enabled=False by default
    # Get enabled providers
    providers = await get_enabled_providers(async_session, str(org.id))

    assert providers == []


@pytest.mark.asyncio
async def test_get_enabled_providers_no_settings(async_session):
    """Test getting enabled providers when settings don't exist."""
    # Create an organization first
    org_data = {"name": "Test Org", "slug": "test-org-sso-11"}
    org = await create_organization(async_session, org_data)

    # Get enabled providers without creating settings
    providers = await get_enabled_providers(async_session, str(org.id))

    assert providers == []


@pytest.mark.asyncio
async def test_multi_tenancy_isolation(async_session):
    """Test that SSO settings are isolated between organizations."""
    # Create two organizations (each auto-creates SSO settings)
    org1_data = {"name": "Org 1", "slug": "test-org-sso-12"}
    org1 = await create_organization(async_session, org1_data)

    org2_data = {"name": "Org 2", "slug": "test-org-sso-13"}
    org2 = await create_organization(async_session, org2_data)

    # Update SSO settings for org1 (sso_allowed must be True)
    settings_data_1 = {
        "sso_allowed": True,
        "google_enabled": True,
        "google_client_id": "org1-client-id",
    }
    await update_organization_sso_settings(async_session, str(org1.id), settings_data_1)

    # Update SSO settings for org2 (sso_allowed=True but google_enabled=False)
    settings_data_2 = {
        "sso_allowed": True,
        "google_enabled": False,
        "google_client_id": "org2-client-id",
    }
    await update_organization_sso_settings(async_session, str(org2.id), settings_data_2)

    # Verify org1 settings
    org1_settings = await get_organization_sso_settings(async_session, str(org1.id))
    assert org1_settings.google_enabled is True
    assert org1_settings.google_client_id == "org1-client-id"

    # Verify org2 settings
    org2_settings = await get_organization_sso_settings(async_session, str(org2.id))
    assert org2_settings.google_enabled is False
    assert org2_settings.google_client_id == "org2-client-id"

    # Verify providers are isolated
    org1_providers = await get_enabled_providers(async_session, str(org1.id))
    org2_providers = await get_enabled_providers(async_session, str(org2.id))
    assert org1_providers == ["google"]
    assert org2_providers == []
