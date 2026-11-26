"""
CRUD operations for OrganizationEmailSettings model.

Each organization can have one email settings record to override platform defaults.
Credentials are stored encrypted and decrypted on retrieval.
"""

from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.encryption import decrypt_field, encrypt_field
from src.models.organization_email_settings import OrganizationEmailSettings


@dataclass
class EmailConfig:
    """Effective email configuration for an organization."""

    provider: str  # 'smtp' or 'sendgrid'

    # SMTP settings
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    # SendGrid settings
    sendgrid_api_key: Optional[str] = None

    # Branding
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None
    reply_to_email: Optional[str] = None


async def get_organization_email_settings(
    session: AsyncSession,
    organization_id: str,
) -> Optional[OrganizationEmailSettings]:
    """
    Get organization email settings.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationEmailSettings or None if not found
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(OrganizationEmailSettings).where(
            OrganizationEmailSettings.organization_id == org_uuid,
            OrganizationEmailSettings.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_or_create_organization_email_settings(
    session: AsyncSession,
    organization_id: str,
) -> OrganizationEmailSettings:
    """
    Get organization email settings, creating defaults if not exists.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationEmailSettings (existing or newly created)
    """
    email_settings = await get_organization_email_settings(session, organization_id)

    if email_settings:
        return email_settings

    # Create default settings (all NULL = use platform defaults)
    org_uuid = UUID(organization_id)

    email_settings = OrganizationEmailSettings(
        organization_id=org_uuid,
        # All other fields default to NULL (use platform defaults)
    )

    session.add(email_settings)
    try:
        await session.commit()
        await session.refresh(email_settings)
    except Exception as e:
        await session.rollback()
        raise e

    return email_settings


async def update_organization_email_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: dict[str, Any],
) -> OrganizationEmailSettings:
    """
    Update organization email settings.

    Creates default settings if they don't exist, then updates.
    Credentials are encrypted before storage.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: Fields to update (all optional):
            - provider: 'smtp', 'sendgrid', or None (platform default)
            - smtp_host, smtp_port, smtp_username, smtp_password
            - smtp_use_tls, smtp_use_ssl
            - sendgrid_api_key
            - sender_email, sender_name, reply_to_email

    Returns:
        The updated OrganizationEmailSettings
    """
    # Get or create settings
    email_settings = await get_or_create_organization_email_settings(
        session, organization_id
    )

    # Fields that require encryption
    encrypted_fields = ["smtp_username", "smtp_password", "sendgrid_api_key"]

    # All updatable fields
    updatable_fields = [
        "provider",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_use_tls",
        "smtp_use_ssl",
        "sendgrid_api_key",
        "sender_email",
        "sender_name",
        "reply_to_email",
    ]

    for field in updatable_fields:
        if field in settings_data:
            value = settings_data[field]
            # Encrypt sensitive fields
            if field in encrypted_fields and value is not None:
                value = encrypt_field(value)
            setattr(email_settings, field, value)

    try:
        await session.commit()
        await session.refresh(email_settings)
    except Exception as e:
        await session.rollback()
        raise e

    return email_settings


async def delete_organization_email_settings(
    session: AsyncSession,
    organization_id: str,
) -> bool:
    """
    Soft delete organization email settings (reset to platform defaults).

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        True if deleted, False if not found
    """
    from datetime import datetime, timezone

    email_settings = await get_organization_email_settings(session, organization_id)

    if not email_settings:
        return False

    email_settings.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return True


async def get_platform_email_config(session: AsyncSession) -> EmailConfig:
    """
    Get platform-wide email configuration from SystemConfig and settings.

    Args:
        session: Database session

    Returns:
        EmailConfig with platform defaults
    """
    from src.crud.system_config import get_system_config_by_key

    # Try to get provider from SystemConfig
    provider_config = await get_system_config_by_key(session, "email.default_provider")
    provider = provider_config.value if provider_config else "smtp"

    # Get SMTP settings from SystemConfig or fall back to config.json
    smtp_host_config = await get_system_config_by_key(session, "email.smtp.host")
    smtp_port_config = await get_system_config_by_key(session, "email.smtp.port")

    smtp_host = (
        smtp_host_config.value
        if smtp_host_config and smtp_host_config.value
        else settings.EMAIL_SERVER
    )
    smtp_port = (
        int(smtp_port_config.value)
        if smtp_port_config and smtp_port_config.value
        else settings.EMAIL_PORT
    )

    # SendGrid from SystemConfig
    sendgrid_config = await get_system_config_by_key(session, "email.sendgrid.api_key")
    sendgrid_api_key = (
        decrypt_field(sendgrid_config.value)
        if sendgrid_config and sendgrid_config.value
        else None
    )

    # Sender from SystemConfig or config.json
    sender_email_config = await get_system_config_by_key(
        session, "email.default_sender_email"
    )
    sender_name_config = await get_system_config_by_key(
        session, "email.default_sender_name"
    )

    sender_email = (
        sender_email_config.value
        if sender_email_config and sender_email_config.value
        else settings.EMAIL_SENDER
    )
    sender_name = (
        sender_name_config.value
        if sender_name_config and sender_name_config.value
        else None
    )

    return EmailConfig(
        provider=provider,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=settings.EMAIL_USERNAME or None,
        smtp_password=settings.EMAIL_PASSWORD or None,
        smtp_use_tls=settings.EMAIL_USE_TLS,
        smtp_use_ssl=settings.EMAIL_USE_SSL,
        sendgrid_api_key=sendgrid_api_key,
        sender_email=sender_email,
        sender_name=sender_name,
        reply_to_email=None,
    )


async def get_effective_email_config(
    session: AsyncSession,
    organization_id: str,
) -> EmailConfig:
    """
    Get the effective email configuration for an organization.

    Merges organization settings with platform defaults:
    1. Organization settings take precedence if set
    2. Falls back to platform config from SystemConfig
    3. Falls back to config.json values

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        EmailConfig with merged configuration
    """
    # Get platform defaults
    platform_config = await get_platform_email_config(session)

    # Get organization settings
    org_settings = await get_organization_email_settings(session, organization_id)

    if not org_settings:
        return platform_config

    # Merge organization settings with platform defaults
    provider = org_settings.provider or platform_config.provider

    # Decrypt credentials if org has them
    org_smtp_username = decrypt_field(org_settings.smtp_username)
    org_smtp_password = decrypt_field(org_settings.smtp_password)
    org_sendgrid_api_key = decrypt_field(org_settings.sendgrid_api_key)

    return EmailConfig(
        provider=provider,
        smtp_host=org_settings.smtp_host or platform_config.smtp_host,
        smtp_port=org_settings.smtp_port or platform_config.smtp_port,
        smtp_username=org_smtp_username or platform_config.smtp_username,
        smtp_password=org_smtp_password or platform_config.smtp_password,
        smtp_use_tls=(
            org_settings.smtp_use_tls
            if org_settings.smtp_use_tls is not None
            else platform_config.smtp_use_tls
        ),
        smtp_use_ssl=(
            org_settings.smtp_use_ssl
            if org_settings.smtp_use_ssl is not None
            else platform_config.smtp_use_ssl
        ),
        sendgrid_api_key=org_sendgrid_api_key or platform_config.sendgrid_api_key,
        sender_email=org_settings.sender_email or platform_config.sender_email,
        sender_name=org_settings.sender_name or platform_config.sender_name,
        reply_to_email=org_settings.reply_to_email or platform_config.reply_to_email,
    )


def get_decrypted_settings(
    email_settings: OrganizationEmailSettings,
) -> dict[str, Any]:
    """
    Get email settings with decrypted credentials.

    Args:
        email_settings: The OrganizationEmailSettings instance

    Returns:
        Dictionary with decrypted values
    """
    return {
        "id": str(email_settings.id),
        "organization_id": str(email_settings.organization_id),
        "provider": email_settings.provider,
        "smtp_host": email_settings.smtp_host,
        "smtp_port": email_settings.smtp_port,
        "smtp_username": decrypt_field(email_settings.smtp_username),
        "smtp_password": decrypt_field(email_settings.smtp_password),
        "smtp_use_tls": email_settings.smtp_use_tls,
        "smtp_use_ssl": email_settings.smtp_use_ssl,
        "sendgrid_api_key": decrypt_field(email_settings.sendgrid_api_key),
        "sender_email": email_settings.sender_email,
        "sender_name": email_settings.sender_name,
        "reply_to_email": email_settings.reply_to_email,
        "created_time": email_settings.created_time,
        "updated_time": email_settings.updated_time,
    }
