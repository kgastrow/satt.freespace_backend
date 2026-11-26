from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization import Organization
from src.models.organization_sso_settings import OrganizationSSOSettings
from src.models.organization_two_factor_settings import (
    OrganizationTwoFactorSettings,
    TwoFactorPolicy,
)
from src.serialisers.organization import (
    CreateOrganizationRequest,
    DeleteOrganizationRequest,
    GetOrganizationRequest,
    UpdateOrganizationDetailsRequest,
    UpdateOrganizationRequest,
)


# Default retention period in days if not configured
DEFAULT_RETENTION_DAYS = 30
RETENTION_CONFIG_KEY = "organization.deletion_retention_days"


async def create_organization(session: AsyncSession, request: dict):
    """
    Create a new organization.

    Args:
        session: SQLAlchemy async session
        request: Dictionary with organization data (name, slug)

    Returns:
        Created Organization object

    Raises:
        ValueError: If slug already exists
    """
    validated_request = CreateOrganizationRequest(**request)

    # Check if organization slug already exists (only non-deleted orgs)
    existing_result = await session.execute(
        select(Organization).where(
            Organization.slug == validated_request.slug,
            Organization.deleted_time.is_(None),
        )
    )
    existing_org = existing_result.scalars().first()

    if existing_org:
        raise ValueError(
            f"Organization with slug '{validated_request.slug}' already exists"
        )

    new_org = Organization(
        name=validated_request.name,
        slug=validated_request.slug,
        is_active=True,
        display_name=validated_request.display_name,
        physical_address_line1=validated_request.physical_address_line1,
        physical_address_line2=validated_request.physical_address_line2,
        city=validated_request.city,
        state_province=validated_request.state_province,
        postal_code=validated_request.postal_code,
        country=validated_request.country,
        contact_email=validated_request.contact_email,
        contact_phone=validated_request.contact_phone,
    )

    session.add(new_org)
    await session.flush()  # Get the org ID before committing

    # Create default SSO settings (disabled by default)
    sso_settings = OrganizationSSOSettings(
        organization_id=new_org.id,
        sso_allowed=False,
        google_enabled=False,
    )
    session.add(sso_settings)

    # Create default 2FA settings (disabled by default)
    two_factor_settings = OrganizationTwoFactorSettings(
        organization_id=new_org.id,
        two_factor_allowed=False,
        two_factor_policy=TwoFactorPolicy.DISABLED.value,
        grace_period_days=7,
    )
    session.add(two_factor_settings)

    await session.commit()
    await session.refresh(new_org)

    return new_org


async def get_organization_by_id(session: AsyncSession, org_id: str):
    request = GetOrganizationRequest(id=UUID(org_id))
    result = await session.execute(
        select(Organization).where(
            Organization.id == request.id, Organization.deleted_time.is_(None)
        )
    )
    org = result.scalars().first()
    return org


async def get_organization_by_slug(session: AsyncSession, slug: str):
    request = GetOrganizationRequest(slug=slug)
    result = await session.execute(
        select(Organization).where(
            Organization.slug == request.slug, Organization.deleted_time.is_(None)
        )
    )
    org = result.scalars().first()
    return org


async def get_organizations(
    session: AsyncSession, limit: int = 10, offset: int = 0
) -> tuple[list[Organization], int]:
    # Count query
    count_result = await session.execute(
        select(func.count())
        .select_from(Organization)
        .where(Organization.deleted_time.is_(None))
    )
    total_count = count_result.scalar() or 0

    # Data query
    result = await session.execute(
        select(Organization)
        .where(Organization.deleted_time.is_(None))
        .limit(limit)
        .offset(offset)
    )
    organizations = result.scalars().all()

    return list(organizations), total_count


async def update_organization(session: AsyncSession, request: dict):
    validated_request = UpdateOrganizationRequest(**request)
    org = await get_organization_by_id(session, str(validated_request.id))

    if not org:
        raise ValueError(f"Organization with id {validated_request.id} not found")

    # Check slug uniqueness if being updated (only non-deleted orgs)
    if validated_request.slug:
        existing_result = await session.execute(
            select(Organization).where(
                Organization.slug == validated_request.slug,
                Organization.id != org.id,
                Organization.deleted_time.is_(None),
            )
        )
        existing_org = existing_result.scalars().first()

        if existing_org:
            raise ValueError(
                f"Organization with slug '{validated_request.slug}' already exists"
            )
        org.slug = validated_request.slug

    if validated_request.name:
        org.name = validated_request.name

    active_changed = (
        validated_request.is_active is not None
        and validated_request.is_active != org.is_active
    )
    if validated_request.is_active is not None:
        org.is_active = validated_request.is_active

    await session.commit()
    await session.refresh(org)
    if active_changed:
        await _invalidate_site_availability_caches(session, org.id)
    return org


async def _invalidate_site_availability_caches(
    session: AsyncSession, organization_id: UUID
) -> None:
    """Drop the 5 s Freespace availability cache of every site of an
    organization whose ``is_active`` flag changed, so the app stops (or starts)
    serving its sites at once instead of after the cache TTL."""
    from src.models.site import Site
    from src.services.freespace.availability_cache import (
        invalidate_availability_cache,
    )

    slugs = (
        (
            await session.execute(
                select(Site.slug).where(Site.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    for slug in slugs:
        await invalidate_availability_cache(slug)


async def delete_organization(session: AsyncSession, org_id: str):
    """
    Soft-delete an organization and all its related data.

    This is the main deletion function that performs cascade soft-delete
    of the organization and all associated records.

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        The soft-deleted Organization object

    Raises:
        ValueError: If organization not found
    """
    request = DeleteOrganizationRequest(id=UUID(org_id))
    # Use cascade soft-delete to delete organization and all related data
    return await soft_delete_organization_cascade(session, str(request.id))


async def request_organization_deletion(
    session: AsyncSession, org_id: str, requested_by_user_id: str
):
    """
    Request deletion of an organization. Creates an OrganizationDeletionRequest record.
    The actual deletion must be performed by a super admin.

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization
        requested_by_user_id: UUID of the user requesting deletion (must be owner)

    Returns:
        Created OrganizationDeletionRequest object

    Raises:
        ValueError: If organization not found or deletion already requested
    """
    from uuid import UUID

    from src.models.organization_deletion_request import OrganizationDeletionRequest

    org = await get_organization_by_id(session, org_id)

    if not org:
        raise ValueError(f"Organization with id {org_id} not found")

    # Only an ACTIVE request blocks a new one. Cancelled requests are
    # soft-deleted and must not keep the organization pending deletion forever.
    active_result = await session.execute(
        select(OrganizationDeletionRequest).where(
            OrganizationDeletionRequest.organization_id == UUID(org_id),
            OrganizationDeletionRequest.deleted_time.is_(None),
        )
    )
    if active_result.scalars().first() is not None:
        raise ValueError("Deletion has already been requested for this organization")

    # Re-activate the most recent cancelled request instead of inserting a
    # second row: the table holds at most one row per organization
    # (uq_organization_deletion_request_org_active).
    cancelled_result = await session.execute(
        select(OrganizationDeletionRequest)
        .where(
            OrganizationDeletionRequest.organization_id == UUID(org_id),
            OrganizationDeletionRequest.deleted_time.is_not(None),
        )
        .order_by(OrganizationDeletionRequest.created_time.desc())
    )
    cancelled_request = cancelled_result.scalars().first()

    if cancelled_request is not None:
        cancelled_request.deleted_time = None
        cancelled_request.requested_by_id = UUID(requested_by_user_id)
        cancelled_request.created_time = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(cancelled_request)
        return cancelled_request

    deletion_request = OrganizationDeletionRequest(
        organization_id=UUID(org_id), requested_by_id=UUID(requested_by_user_id)
    )

    session.add(deletion_request)
    await session.commit()
    await session.refresh(deletion_request)
    return deletion_request


async def cancel_organization_deletion_request(session: AsyncSession, org_id: str):
    """
    Cancel a pending deletion request for an organization.

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        Organization object

    Raises:
        ValueError: If organization not found or no deletion request exists
    """
    from uuid import UUID

    from src.models.organization_deletion_request import OrganizationDeletionRequest

    org = await get_organization_by_id(session, org_id)

    if not org:
        raise ValueError(f"Organization with id {org_id} not found")

    # Find the ACTIVE deletion request (cancelled ones are soft-deleted)
    result = await session.execute(
        select(OrganizationDeletionRequest).where(
            OrganizationDeletionRequest.organization_id == UUID(org_id),
            OrganizationDeletionRequest.deleted_time.is_(None),
        )
    )
    deletion_request = result.scalars().first()

    if not deletion_request:
        raise ValueError("No deletion request exists for this organization")

    # Soft delete so the request is no longer active but history is preserved.
    deletion_request.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    return org


async def get_organization_deletion_request(session: AsyncSession, org_id: str):
    """
    Get the deletion request for an organization if one exists.

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        The active OrganizationDeletionRequest object, or None if there is no
        pending (non-cancelled) request
    """
    from src.models.organization_deletion_request import OrganizationDeletionRequest

    result = await session.execute(
        select(OrganizationDeletionRequest).where(
            OrganizationDeletionRequest.organization_id == UUID(org_id),
            OrganizationDeletionRequest.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_retention_days(session: AsyncSession) -> int:
    """
    Get the configured retention period for soft-deleted organization data.

    Args:
        session: SQLAlchemy async session

    Returns:
        Number of days to retain soft-deleted data before hard-delete is allowed
    """
    from src.crud.system_config import get_system_config_by_key

    config = await get_system_config_by_key(session, RETENTION_CONFIG_KEY)
    if config and config.value is not None:
        try:
            return int(config.value)
        except (ValueError, TypeError):
            pass
    return DEFAULT_RETENTION_DAYS


async def can_hard_delete_organization(
    session: AsyncSession, org_id: str
) -> tuple[bool, int, Optional[datetime]]:
    """
    Check if an organization can be hard-deleted based on retention period.

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        Tuple of (can_delete, days_remaining, deleted_time)
        - can_delete: True if retention period has passed
        - days_remaining: Number of days until hard-delete is allowed (0 if can delete)
        - deleted_time: When the organization was soft-deleted (None if not deleted)
    """
    # Get the organization (including soft-deleted)
    result = await session.execute(
        select(Organization).where(Organization.id == UUID(org_id))
    )
    org = result.scalars().first()

    if not org:
        raise ValueError(f"Organization with id {org_id} not found")

    if org.deleted_time is None:
        # Organization is not soft-deleted, check for deletion request
        deletion_request = await get_organization_deletion_request(session, org_id)
        if not deletion_request:
            raise ValueError(
                "Organization has not been soft-deleted or requested for deletion"
            )
        # Use deletion request time as reference
        reference_time = deletion_request.created_time
    else:
        reference_time = org.deleted_time

    retention_days = await get_retention_days(session)
    retention_period = timedelta(days=retention_days)
    earliest_hard_delete = reference_time + retention_period
    now = datetime.now(timezone.utc)

    if now >= earliest_hard_delete:
        return True, 0, org.deleted_time
    else:
        days_remaining = (earliest_hard_delete - now).days + 1
        return False, days_remaining, org.deleted_time


async def soft_delete_organization_cascade(
    session: AsyncSession, org_id: str
) -> Organization:
    """
    Soft-delete an organization and all its related data.

    This sets deleted_time on the organization and all related records:
    - Users
    - UserRoles
    - RefreshTokens
    - UserOTPs
    - NotificationTemplates (org-scoped only)
    - Notifications
    - BulkNotifications
    - NotificationCategories (org-scoped only)
    - UserNotificationPreferences
    - UserCategoryPreferences
    - Files
    - FileUsages
    - OrganizationNotificationSettings
    - OrganizationFileSettings
    - OrganizationSSOSettings
    - OrganizationTwoFactorSettings
    - OrganizationDeletionRequest (hard delete since it's transient)

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        The soft-deleted Organization object

    Raises:
        ValueError: If organization not found
    """
    from src.models.bulk_notification import BulkNotification
    from src.models.device import DeviceSite
    from src.models.file import File
    from src.models.file_usage import FileUsage
    from src.models.ingest_key import IngestKey
    from src.models.notification import Notification
    from src.models.notification_category import NotificationCategory
    from src.models.notification_template import NotificationTemplate
    from src.models.organization_deletion_request import OrganizationDeletionRequest
    from src.models.organization_file_settings import OrganizationFileSettings
    from src.models.organization_notification_settings import (
        OrganizationNotificationSettings,
    )
    from src.models.refresh_token import RefreshToken
    from src.models.site import Site
    from src.models.site_message_template import SiteMessageTemplate
    from src.models.user import User
    from src.models.user_notification_preference import (
        UserCategoryPreference,
        UserNotificationPreference,
    )
    from src.models.user_otp import UserOTP
    from src.models.user_role import UserRole
    from src.models.zone import Zone

    org = await get_organization_by_id(session, org_id)
    if not org:
        raise ValueError(f"Organization with id {org_id} not found")

    now = datetime.now(timezone.utc)
    org_uuid = UUID(org_id)

    # Soft-delete all related records
    # Users
    await session.execute(
        update(User)
        .where(User.organization_id == org_uuid, User.deleted_time.is_(None))
        .values(deleted_time=now)
    )

    # UserRoles
    await session.execute(
        update(UserRole)
        .where(UserRole.organization_id == org_uuid, UserRole.deleted_time.is_(None))
        .values(deleted_time=now)
    )

    # RefreshTokens
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.organization_id == org_uuid,
            RefreshToken.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # UserOTPs
    await session.execute(
        update(UserOTP)
        .where(UserOTP.organization_id == org_uuid, UserOTP.deleted_time.is_(None))
        .values(deleted_time=now)
    )

    # NotificationTemplates (org-scoped only, not system templates)
    await session.execute(
        update(NotificationTemplate)
        .where(
            NotificationTemplate.organization_id == org_uuid,
            NotificationTemplate.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # Notifications
    await session.execute(
        update(Notification)
        .where(
            Notification.organization_id == org_uuid,
            Notification.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # BulkNotifications
    await session.execute(
        update(BulkNotification)
        .where(
            BulkNotification.organization_id == org_uuid,
            BulkNotification.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # NotificationCategories (org-scoped only)
    await session.execute(
        update(NotificationCategory)
        .where(
            NotificationCategory.organization_id == org_uuid,
            NotificationCategory.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # UserNotificationPreferences
    await session.execute(
        update(UserNotificationPreference)
        .where(
            UserNotificationPreference.organization_id == org_uuid,
            UserNotificationPreference.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # UserCategoryPreferences
    await session.execute(
        update(UserCategoryPreference)
        .where(
            UserCategoryPreference.organization_id == org_uuid,
            UserCategoryPreference.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # Files
    await session.execute(
        update(File)
        .where(File.organization_id == org_uuid, File.deleted_time.is_(None))
        .values(deleted_time=now)
    )

    # FileUsages
    await session.execute(
        update(FileUsage)
        .where(FileUsage.organization_id == org_uuid, FileUsage.deleted_time.is_(None))
        .values(deleted_time=now)
    )

    # OrganizationNotificationSettings
    await session.execute(
        update(OrganizationNotificationSettings)
        .where(
            OrganizationNotificationSettings.organization_id == org_uuid,
            OrganizationNotificationSettings.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # OrganizationFileSettings
    await session.execute(
        update(OrganizationFileSettings)
        .where(
            OrganizationFileSettings.organization_id == org_uuid,
            OrganizationFileSettings.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # OrganizationSSOSettings
    await session.execute(
        update(OrganizationSSOSettings)
        .where(
            OrganizationSSOSettings.organization_id == org_uuid,
            OrganizationSSOSettings.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # OrganizationTwoFactorSettings
    await session.execute(
        update(OrganizationTwoFactorSettings)
        .where(
            OrganizationTwoFactorSettings.organization_id == org_uuid,
            OrganizationTwoFactorSettings.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    # Freespace: sites, zones, message templates and ingest keys (BF-10, BF-30).
    # Public /v1 endpoints also check the organization itself, so this is the
    # belt to that braces. Devices are not tenant data: only their selections of
    # this organization's sites go (D12 sanctions that hard delete).
    site_slugs = list(
        (
            await session.execute(
                select(Site.slug).where(
                    Site.organization_id == org_uuid, Site.deleted_time.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    org_site_ids = select(Site.id).where(Site.organization_id == org_uuid)
    await session.execute(
        sql_delete(DeviceSite).where(DeviceSite.site_id.in_(org_site_ids))
    )
    for freespace_model in (IngestKey, SiteMessageTemplate, Zone):
        await session.execute(
            update(freespace_model)
            .where(
                freespace_model.organization_id == org_uuid,
                freespace_model.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )
    await session.execute(
        update(Site)
        .where(Site.organization_id == org_uuid, Site.deleted_time.is_(None))
        .values(deleted_time=now, managed=False, listed=False)
    )

    # Hard-delete the deletion request (it's transient)
    await session.execute(
        sql_delete(OrganizationDeletionRequest).where(
            OrganizationDeletionRequest.organization_id == org_uuid
        )
    )

    # Finally, soft-delete the organization itself
    org.deleted_time = now

    await session.commit()
    await session.refresh(org)

    # Do not let the 5 s availability cache outlive the sites (fails open).
    from src.services.freespace.availability_cache import (
        invalidate_availability_cache,
    )

    for slug in site_slugs:
        await invalidate_availability_cache(slug)
    return org


async def _hard_delete_freespace_rows(
    session: AsyncSession, org_uuid: UUID, stats: dict[str, Any]
) -> None:
    """Hard-delete the Freespace rows of an organization, children first.

    Order (FK constraints): push_send -> site_event; occupancy_history,
    zone_snapshot -> zone; device_site, snapshots, engine state, ingest keys,
    templates, zones -> site. Devices themselves are not tenant data (a phone
    is not owned by an organization); only their selection of this
    organization's sites goes. ``created_by`` of app keys points at a user of
    the organization, so it is cleared before the users are deleted.
    """
    from sqlalchemy import update as sql_update

    from src.models.app_key import AppKey
    from src.models.device import DeviceSite
    from src.models.ingest_key import IngestKey
    from src.models.occupancy_history import OccupancyHistory
    from src.models.push_send import PushSend
    from src.models.site import Site
    from src.models.site_engine_state import SiteEngineState
    from src.models.site_event import SiteEvent
    from src.models.site_message_template import SiteMessageTemplate
    from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
    from src.models.user import User
    from src.models.zone import Zone

    site_ids = select(Site.id).where(Site.organization_id == org_uuid)
    deleted = stats["records_deleted"]

    steps: list[tuple[str, Any]] = [
        (
            "freespace_push_sends",
            sql_delete(PushSend).where(PushSend.organization_id == org_uuid),
        ),
        (
            "freespace_site_events",
            sql_delete(SiteEvent).where(SiteEvent.organization_id == org_uuid),
        ),
        (
            "freespace_occupancy_history",
            sql_delete(OccupancyHistory).where(
                OccupancyHistory.organization_id == org_uuid
            ),
        ),
        (
            "freespace_device_sites",
            sql_delete(DeviceSite).where(DeviceSite.site_id.in_(site_ids)),
        ),
        (
            "freespace_zone_snapshots",
            sql_delete(ZoneSnapshot).where(ZoneSnapshot.organization_id == org_uuid),
        ),
        (
            "freespace_site_snapshots",
            sql_delete(SiteSnapshot).where(SiteSnapshot.organization_id == org_uuid),
        ),
        (
            "freespace_site_engine_states",
            sql_delete(SiteEngineState).where(
                SiteEngineState.organization_id == org_uuid
            ),
        ),
        (
            "freespace_ingest_keys",
            sql_delete(IngestKey).where(IngestKey.organization_id == org_uuid),
        ),
        (
            "freespace_site_message_templates",
            sql_delete(SiteMessageTemplate).where(
                SiteMessageTemplate.organization_id == org_uuid
            ),
        ),
        ("freespace_zones", sql_delete(Zone).where(Zone.organization_id == org_uuid)),
        ("freespace_sites", sql_delete(Site).where(Site.organization_id == org_uuid)),
    ]
    for name, stmt in steps:
        result = await session.execute(stmt)
        deleted[name] = result.rowcount

    # App keys are global; only the creator reference may block the user purge.
    await session.execute(
        sql_update(AppKey)
        .where(
            AppKey.created_by.in_(
                select(User.id).where(User.organization_id == org_uuid)
            )
        )
        .values(created_by=None)
    )


async def hard_delete_organization(session: AsyncSession, org_id: str) -> dict:
    """
    Permanently delete an organization and all its related data.

    This function:
    1. Checks that the retention period has passed
    2. Deletes all S3 files
    3. Hard-deletes all database records in the correct order (FK constraints)

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        Dictionary with deletion stats

    Raises:
        ValueError: If organization not found or retention period hasn't passed
    """
    from src.models.audit_log import AuditLog
    from src.models.bulk_notification import BulkNotification
    from src.models.file import File
    from src.models.file_usage import FileUsage
    from src.models.notification import Notification
    from src.models.notification_category import NotificationCategory
    from src.models.notification_template import NotificationTemplate
    from src.models.organization_deletion_request import OrganizationDeletionRequest
    from src.models.organization_file_settings import OrganizationFileSettings
    from src.models.organization_notification_settings import (
        OrganizationNotificationSettings,
    )
    from src.models.refresh_token import RefreshToken
    from src.models.user import User
    from src.models.user_notification_preference import (
        UserCategoryPreference,
        UserNotificationPreference,
    )
    from src.models.user_otp import UserOTP
    from src.models.user_role import UserRole
    from src.services.files.s3_storage import s3_storage

    org_uuid = UUID(org_id)

    # Check retention period
    can_delete, days_remaining, _ = await can_hard_delete_organization(session, org_id)
    if not can_delete:
        raise ValueError(
            f"Cannot hard-delete organization. {days_remaining} days remaining in retention period."
        )

    # Get the organization (including soft-deleted)
    result = await session.execute(
        select(Organization).where(Organization.id == org_uuid)
    )
    org = result.scalars().first()

    if not org:
        raise ValueError(f"Organization with id {org_id} not found")

    stats: dict[str, Any] = {
        "organization_id": org_id,
        "organization_name": org.name,
        "s3_files_deleted": 0,
        "records_deleted": {},
    }

    # Delete S3 files first
    if s3_storage:
        file_result = await session.execute(
            select(File).where(File.organization_id == org_uuid)
        )
        files = file_result.scalars().all()
        for file in files:
            if file.storage_key:
                try:
                    await s3_storage.delete(file.storage_key)
                    stats["s3_files_deleted"] += 1
                except Exception:
                    pass  # Log but continue

    # Hard-delete all records in order (respecting FK constraints)
    # Order matters - delete child records first

    # 0. Freespace rows (children of Site first; some reference User/Device)
    await _hard_delete_freespace_rows(session, org_uuid, stats)

    # 1. UserCategoryPreference (references User, NotificationCategory)
    result = await session.execute(
        sql_delete(UserCategoryPreference).where(
            UserCategoryPreference.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["user_category_preferences"] = result.rowcount

    # 2. UserNotificationPreference (references User)
    result = await session.execute(
        sql_delete(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["user_notification_preferences"] = result.rowcount

    # 3. Notifications (references User, NotificationTemplate, NotificationCategory)
    result = await session.execute(
        sql_delete(Notification).where(Notification.organization_id == org_uuid)
    )
    stats["records_deleted"]["notifications"] = result.rowcount

    # 4. BulkNotifications (references NotificationTemplate)
    result = await session.execute(
        sql_delete(BulkNotification).where(BulkNotification.organization_id == org_uuid)
    )
    stats["records_deleted"]["bulk_notifications"] = result.rowcount

    # 5. NotificationTemplates (org-scoped)
    result = await session.execute(
        sql_delete(NotificationTemplate).where(
            NotificationTemplate.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["notification_templates"] = result.rowcount

    # 6. NotificationCategories (org-scoped)
    result = await session.execute(
        sql_delete(NotificationCategory).where(
            NotificationCategory.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["notification_categories"] = result.rowcount

    # 7. RefreshTokens (references User)
    result = await session.execute(
        sql_delete(RefreshToken).where(RefreshToken.organization_id == org_uuid)
    )
    stats["records_deleted"]["refresh_tokens"] = result.rowcount

    # 8. UserOTPs (references User)
    result = await session.execute(
        sql_delete(UserOTP).where(UserOTP.organization_id == org_uuid)
    )
    stats["records_deleted"]["user_otps"] = result.rowcount

    # 9. UserRoles (references User, Role)
    result = await session.execute(
        sql_delete(UserRole).where(UserRole.organization_id == org_uuid)
    )
    stats["records_deleted"]["user_roles"] = result.rowcount

    # 10. Files (references User as uploaded_by)
    result = await session.execute(
        sql_delete(File).where(File.organization_id == org_uuid)
    )
    stats["records_deleted"]["files"] = result.rowcount

    # 11. FileUsages (references User)
    result = await session.execute(
        sql_delete(FileUsage).where(FileUsage.organization_id == org_uuid)
    )
    stats["records_deleted"]["file_usages"] = result.rowcount

    # 12. OrganizationNotificationSettings
    result = await session.execute(
        sql_delete(OrganizationNotificationSettings).where(
            OrganizationNotificationSettings.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["organization_notification_settings"] = result.rowcount

    # 13. OrganizationFileSettings
    result = await session.execute(
        sql_delete(OrganizationFileSettings).where(
            OrganizationFileSettings.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["organization_file_settings"] = result.rowcount

    # 14. OrganizationSSOSettings
    result = await session.execute(
        sql_delete(OrganizationSSOSettings).where(
            OrganizationSSOSettings.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["organization_sso_settings"] = result.rowcount

    # 15. OrganizationTwoFactorSettings
    result = await session.execute(
        sql_delete(OrganizationTwoFactorSettings).where(
            OrganizationTwoFactorSettings.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["organization_two_factor_settings"] = result.rowcount

    # 16. AuditLogs
    result = await session.execute(
        sql_delete(AuditLog).where(AuditLog.organization_id == org_uuid)
    )
    stats["records_deleted"]["audit_logs"] = result.rowcount

    # 17. Users
    result = await session.execute(
        sql_delete(User).where(User.organization_id == org_uuid)
    )
    stats["records_deleted"]["users"] = result.rowcount

    # 18. OrganizationDeletionRequest
    result = await session.execute(
        sql_delete(OrganizationDeletionRequest).where(
            OrganizationDeletionRequest.organization_id == org_uuid
        )
    )
    stats["records_deleted"]["organization_deletion_requests"] = result.rowcount

    # 19. Finally, the Organization itself
    await session.execute(sql_delete(Organization).where(Organization.id == org_uuid))
    stats["records_deleted"]["organization"] = 1

    await session.commit()
    return stats


async def get_organization_details(session: AsyncSession, org_id: str) -> Organization:
    """
    Get organization details including all contact and address fields.

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization

    Returns:
        Organization object with all detail fields

    Raises:
        ValueError: If organization not found
    """
    org = await get_organization_by_id(session, org_id)
    if not org:
        raise ValueError(f"Organization with id {org_id} not found")
    return org


async def update_organization_details(
    session: AsyncSession, org_id: str, request: dict
) -> Organization:
    """
    Update organization details (contact info, address, logo).

    Args:
        session: SQLAlchemy async session
        org_id: UUID of the organization
        request: Dictionary with update fields

    Returns:
        Updated Organization object

    Raises:
        ValueError: If organization not found or logo_file_id invalid
    """
    validated_request = UpdateOrganizationDetailsRequest(**request)
    org = await get_organization_by_id(session, org_id)

    if not org:
        raise ValueError(f"Organization with id {org_id} not found")

    # Validate logo_file_id if provided
    if validated_request.logo_file_id is not None:
        from src.models.file import File

        file_result = await session.execute(
            select(File).where(
                File.id == validated_request.logo_file_id,
                File.organization_id == UUID(org_id),
                File.deleted_time.is_(None),
            )
        )
        file = file_result.scalar_one_or_none()
        if not file:
            raise ValueError(
                f"File with id {validated_request.logo_file_id} not found or does not belong to organization"
            )

    # Update only provided fields
    update_data = validated_request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)

    await session.commit()
    await session.refresh(org)
    return org
