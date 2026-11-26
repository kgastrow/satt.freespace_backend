from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import OrganizationTwoFactorSettings, TwoFactorPolicy
from src.services.tasks import task_queue


async def get_by_organization_id(
    session: AsyncSession, organization_id: str
) -> OrganizationTwoFactorSettings | None:
    """Get 2FA settings for an organization."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(OrganizationTwoFactorSettings).where(
            OrganizationTwoFactorSettings.organization_id == org_uuid,
            OrganizationTwoFactorSettings.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_settings(
    session: AsyncSession, data: dict, organization_id: str
) -> OrganizationTwoFactorSettings:
    """Create 2FA settings for an organization."""
    org_uuid = UUID(organization_id)

    existing = await get_by_organization_id(session, organization_id)
    if existing:
        raise ValueError("2FA settings already exist for this organization")

    settings = OrganizationTwoFactorSettings(
        organization_id=org_uuid,
        two_factor_allowed=data.get("two_factor_allowed", False),
        two_factor_policy=data.get("two_factor_policy", TwoFactorPolicy.DISABLED.value),
        grace_period_days=data.get("grace_period_days", 7),
    )
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings


async def update_settings(
    session: AsyncSession, data: dict, organization_id: str
) -> OrganizationTwoFactorSettings:
    """Update 2FA settings for an organization."""
    settings = await get_by_organization_id(session, organization_id)
    if not settings:
        raise ValueError("2FA settings not found for this organization")

    should_notify = False

    if "two_factor_allowed" in data:
        settings.two_factor_allowed = data["two_factor_allowed"]
    if "two_factor_policy" in data:
        old_policy = settings.two_factor_policy
        new_policy = data["two_factor_policy"]
        settings.two_factor_policy = new_policy

        if (
            old_policy
            in [TwoFactorPolicy.DISABLED.value, TwoFactorPolicy.OPTIONAL.value]
            and new_policy == TwoFactorPolicy.MANDATORY.value
        ):
            settings.enforcement_start_time = datetime.now(timezone.utc)
            should_notify = True

    if "grace_period_days" in data:
        settings.grace_period_days = data["grace_period_days"]

    await session.commit()
    await session.refresh(settings)

    # Enqueue notification task if policy changed to mandatory
    if should_notify:
        await task_queue.enqueue_job(
            "notify_2fa_mandatory_change", organization_id=organization_id
        )

    return settings


async def update_allowed_by_super_admin(
    session: AsyncSession, organization_id: str, two_factor_allowed: bool
) -> OrganizationTwoFactorSettings:
    """Super admin endpoint to allow/disallow 2FA for an organization."""
    settings = await get_by_organization_id(session, organization_id)

    if not settings:
        settings = OrganizationTwoFactorSettings(
            organization_id=UUID(organization_id),
            two_factor_allowed=two_factor_allowed,
            two_factor_policy=TwoFactorPolicy.DISABLED.value,
        )
        session.add(settings)
    else:
        settings.two_factor_allowed = two_factor_allowed
        if not two_factor_allowed:
            settings.two_factor_policy = TwoFactorPolicy.DISABLED.value
            settings.enforcement_start_time = None

    await session.commit()
    await session.refresh(settings)
    return settings
