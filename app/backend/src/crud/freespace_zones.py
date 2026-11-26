"""CRUD for Freespace zones (admin API, M1). The parent site is resolved and
tenant-checked first (``freespace_sites.get_scoped_site``); every query here
is then filtered by that ``site_id``."""

from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.zone import Zone


async def list_zones(
    session: AsyncSession, site_id: uuid.UUID, *, discovered: bool | None = None
) -> list[Zone]:
    stmt = select(Zone).where(Zone.site_id == site_id, Zone.deleted_time.is_(None))
    if discovered is not None:
        stmt = stmt.where(Zone.discovered.is_(discovered))
    stmt = stmt.order_by(Zone.display_order, Zone.slug)
    return list((await session.execute(stmt)).scalars().all())


async def get_zone(
    session: AsyncSession, site_id: uuid.UUID, zone_id: uuid.UUID
) -> Zone | None:
    result = await session.execute(
        select(Zone).where(
            Zone.id == zone_id, Zone.site_id == site_id, Zone.deleted_time.is_(None)
        )
    )
    return result.scalars().first()


async def zone_slug_exists(
    session: AsyncSession, site_id: uuid.UUID, slug: str
) -> bool:
    result = await session.execute(
        select(func.count())
        .select_from(Zone)
        .where(Zone.site_id == site_id, Zone.slug == slug, Zone.deleted_time.is_(None))
    )
    return result.scalar_one() > 0


async def soft_delete_zone(session: AsyncSession, zone: Zone, now: datetime) -> None:
    zone.deleted_time = now
    await session.flush()
