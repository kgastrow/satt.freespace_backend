"""
CRUD for Freespace sites (admin API, M1). Tenant rule (D2, Q2): a super admin
sees every organization; everyone else only their own. ``organization_id=None``
means "no tenant filter" (super admin).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.device import DeviceSite
from src.models.ingest_key import IngestKey
from src.models.organization import Organization
from src.models.site import Site
from src.models.site_message_template import SiteMessageTemplate
from src.models.zone import Zone


async def get_scoped_site(
    session: AsyncSession, site_id: uuid.UUID, organization_id: uuid.UUID | None
) -> Site | None:
    """Live site by id; filtered by tenant unless ``organization_id`` is None."""
    stmt = select(Site).where(Site.id == site_id, Site.deleted_time.is_(None))
    if organization_id is not None:
        stmt = stmt.where(Site.organization_id == organization_id)
    return (await session.execute(stmt)).scalars().first()


async def list_sites(
    session: AsyncSession,
    organization_id: uuid.UUID | None,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Site], int]:
    base = select(Site).where(Site.deleted_time.is_(None))
    count = select(func.count()).select_from(Site).where(Site.deleted_time.is_(None))
    if organization_id is not None:
        base = base.where(Site.organization_id == organization_id)
        count = count.where(Site.organization_id == organization_id)
    total = (await session.execute(count)).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(Site.name, Site.slug).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def organization_names(
    session: AsyncSession, organization_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Names of the given organizations (for the customer column), by id."""
    ids = set(organization_ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(Organization.id, Organization.name).where(Organization.id.in_(ids))
    )
    return {row.id: row.name for row in rows}


async def site_slug_exists(session: AsyncSession, slug: str) -> bool:
    result = await session.execute(
        select(Site.id).where(Site.slug == slug, Site.deleted_time.is_(None))
    )
    return result.first() is not None


async def organization_exists(
    session: AsyncSession, organization_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(Organization.id).where(
            Organization.id == organization_id,
            Organization.deleted_time.is_(None),
            Organization.is_active.is_(True),
        )
    )
    return result.first() is not None


def site_snapshot_values(site: Site, fields: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(site, name) for name in fields}


async def soft_delete_site(session: AsyncSession, site: Site, now: datetime) -> None:
    """Soft delete the site with its zones, templates and ingest keys, and drop
    the device selections of it (D12, as the organization cascade does). The
    caller invalidates the availability cache after commit."""
    site.deleted_time = now
    site.managed = False
    site.listed = False
    await session.execute(
        update(Zone)
        .where(Zone.site_id == site.id, Zone.deleted_time.is_(None))
        .values(deleted_time=now)
    )
    await session.execute(
        update(SiteMessageTemplate)
        .where(
            SiteMessageTemplate.site_id == site.id,
            SiteMessageTemplate.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )
    await session.execute(
        update(IngestKey)
        .where(IngestKey.site_id == site.id, IngestKey.deleted_time.is_(None))
        .values(deleted_time=now)
    )
    # Sanctioned hard delete (D12): a selection is not tenant data.
    await session.execute(delete(DeviceSite).where(DeviceSite.site_id == site.id))
    await session.flush()
