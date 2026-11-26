"""
CRUD operations for OrganizationSSOSettings model.

Each organization has exactly one SSO settings record.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization_sso_settings import OrganizationSSOSettings


async def get_organization_sso_settings(
    session: AsyncSession,
    organization_id: str,
) -> Optional[OrganizationSSOSettings]:
    """
    Get organization SSO settings.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationSSOSettings or None if not found
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(OrganizationSSOSettings).where(
            OrganizationSSOSettings.organization_id == org_uuid,
            OrganizationSSOSettings.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_organization_sso_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: dict[str, Any],
) -> OrganizationSSOSettings:
    """
    Create organization SSO settings.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: SSO settings data (google_enabled, google_client_id, etc.)

    Returns:
        The created OrganizationSSOSettings

    Raises:
        ValueError: If settings already exist for this organization
    """
    org_uuid = UUID(organization_id)

    # Check if settings already exist
    existing = await get_organization_sso_settings(session, organization_id)
    if existing:
        raise ValueError(
            f"SSO settings already exist for organization {organization_id}"
        )

    # Create new settings
    settings = OrganizationSSOSettings(
        organization_id=org_uuid,
        sso_allowed=settings_data.get("sso_allowed", False),
        google_enabled=settings_data.get("google_enabled", False),
        google_client_id=settings_data.get("google_client_id"),
        google_client_secret=settings_data.get("google_client_secret"),
    )

    session.add(settings)
    try:
        await session.commit()
        await session.refresh(settings)
    except Exception as e:
        await session.rollback()
        raise e

    return settings


async def update_organization_sso_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: dict[str, Any],
) -> OrganizationSSOSettings:
    """
    Update organization SSO settings.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: Fields to update (all optional):
            - google_enabled
            - google_client_id
            - google_client_secret

    Returns:
        The updated OrganizationSSOSettings

    Raises:
        ValueError: If settings don't exist for this organization
    """
    # Get existing settings
    settings = await get_organization_sso_settings(session, organization_id)

    if not settings:
        raise ValueError(f"SSO settings not found for organization {organization_id}")

    # Update allowed fields
    updatable_fields = [
        "sso_allowed",
        "google_enabled",
        "google_client_id",
        "google_client_secret",
    ]

    for field in updatable_fields:
        if field in settings_data:
            setattr(settings, field, settings_data[field])

    try:
        await session.commit()
        await session.refresh(settings)
    except Exception as e:
        await session.rollback()
        raise e

    return settings


async def get_enabled_providers(
    session: AsyncSession,
    organization_id: str,
) -> list[str]:
    """
    Get list of enabled SSO providers for an organization.

    Only returns providers if SSO is allowed by super admin AND
    the specific provider is enabled by the org admin.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        List of enabled provider names (e.g., ['google'])
    """
    settings = await get_organization_sso_settings(session, organization_id)

    if not settings:
        return []

    # SSO must be allowed by super admin
    if not settings.sso_allowed:
        return []

    enabled_providers = []
    if settings.google_enabled:
        enabled_providers.append("google")

    return enabled_providers
