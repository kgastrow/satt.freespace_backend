"""Read-side queries for the Freespace back-office statistics (M8).

Devices are NOT tenant data (D2): a non-super-admin only ever sees devices
that selected a site of their organization. Nothing here returns a device id,
suffix or token - only aggregates.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
import uuid

from sqlalchemy import Select, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.device import Device, DeviceSite
from src.models.occupancy_history import OccupancyHistory
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.models.zone import Zone
from src.services.freespace.loaders import (
    site_figures_from_row,
    zone_figures_from_row,
)
from src.services.freespace.types import SnapshotView


async def list_scoped_sites(
    session: AsyncSession, organization_id: uuid.UUID | None
) -> list[Site]:
    stmt = select(Site).where(Site.deleted_time.is_(None))
    if organization_id is not None:
        stmt = stmt.where(Site.organization_id == organization_id)
    return list(
        (await session.execute(stmt.order_by(Site.name, Site.slug))).scalars().all()
    )


async def zones_by_site(
    session: AsyncSession, site_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Zone]]:
    out: dict[uuid.UUID, list[Zone]] = defaultdict(list)
    if not site_ids:
        return out
    rows = await session.execute(
        select(Zone)
        .where(Zone.site_id.in_(site_ids), Zone.deleted_time.is_(None))
        .order_by(Zone.display_order, Zone.slug)
    )
    for zone in rows.scalars():
        out[zone.site_id].append(zone)
    return out


async def snapshots_by_site(
    session: AsyncSession, site_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, SnapshotView]:
    """Latest snapshot per site in two queries (same shape as
    ``loaders.load_snapshot``)."""
    if not site_ids:
        return {}
    site_rows = {
        row.site_id: row
        for row in (
            await session.execute(
                select(SiteSnapshot).where(SiteSnapshot.site_id.in_(site_ids))
            )
        ).scalars()
    }
    zone_figs: dict[uuid.UUID, dict] = defaultdict(dict)
    zone_rows = await session.execute(
        select(ZoneSnapshot, Zone.slug)
        .join(Zone, Zone.id == ZoneSnapshot.zone_id)
        .where(ZoneSnapshot.site_id.in_(site_ids), Zone.deleted_time.is_(None))
    )
    for row, slug in zone_rows.all():
        zone_figs[row.site_id][slug] = zone_figures_from_row(row, slug)
    return {
        site_id: SnapshotView(
            site=(
                site_figures_from_row(site_rows[site_id])
                if site_id in site_rows
                else None
            ),
            zones=zone_figs.get(site_id, {}),
        )
        for site_id in site_ids
    }


async def engine_states_by_site(
    session: AsyncSession, site_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, SiteEngineState]:
    if not site_ids:
        return {}
    rows = await session.execute(
        select(SiteEngineState).where(SiteEngineState.site_id.in_(site_ids))
    )
    return {row.site_id: row for row in rows.scalars()}


def _opted_in_condition():
    return (
        Device.deleted_time.is_(None),
        Device.notifications_enabled.is_(True),
    )


async def opted_in_counts_by_site(
    session: AsyncSession, site_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Live devices with notifications on that selected each site."""
    if not site_ids:
        return {}
    rows = await session.execute(
        select(DeviceSite.site_id, func.count(distinct(DeviceSite.device_id)))
        .join(Device, Device.id == DeviceSite.device_id)
        .where(DeviceSite.site_id.in_(site_ids), *_opted_in_condition())
        .group_by(DeviceSite.site_id)
    )
    return {site_id: int(n) for site_id, n in rows.all()}


def _scoped_device_ids(
    organization_id: uuid.UUID | None, site_id: uuid.UUID | None
) -> Select:
    """Subquery of live device ids in scope. Super admin without a site: every
    live device (including those with no site). Otherwise only devices that
    selected an in-scope site."""
    if organization_id is None and site_id is None:
        return select(Device.id).where(Device.deleted_time.is_(None))
    stmt = (
        select(DeviceSite.device_id)
        .join(Site, Site.id == DeviceSite.site_id)
        .join(Device, Device.id == DeviceSite.device_id)
        .where(Site.deleted_time.is_(None), Device.deleted_time.is_(None))
    )
    if organization_id is not None:
        stmt = stmt.where(Site.organization_id == organization_id)
    if site_id is not None:
        stmt = stmt.where(Site.id == site_id)
    return stmt


async def device_statistics(
    session: AsyncSession,
    organization_id: uuid.UUID | None,
    site_id: uuid.UUID | None = None,
) -> dict:
    scope = _scoped_device_ids(organization_id, site_id).scalar_subquery()
    total = (
        await session.execute(select(func.count(Device.id)).where(Device.id.in_(scope)))
    ).scalar_one()
    opted_in = (
        await session.execute(
            select(func.count(Device.id)).where(
                Device.id.in_(scope), Device.notifications_enabled.is_(True)
            )
        )
    ).scalar_one()
    platforms = (
        await session.execute(
            select(Device.platform, func.count(Device.id))
            .where(Device.id.in_(scope))
            .group_by(Device.platform)
            .order_by(Device.platform)
        )
    ).all()
    versions = (
        await session.execute(
            select(Device.app_version, func.count(Device.id))
            .where(Device.id.in_(scope))
            .group_by(Device.app_version)
            .order_by(Device.app_version)
        )
    ).all()
    by_site_stmt = (
        select(Site.id, Site.slug, Site.name, func.count(distinct(Device.id)))
        .join(DeviceSite, DeviceSite.site_id == Site.id)
        .join(Device, Device.id == DeviceSite.device_id)
        .where(Site.deleted_time.is_(None), Device.deleted_time.is_(None))
        .group_by(Site.id, Site.slug, Site.name)
        .order_by(Site.name, Site.slug)
    )
    if organization_id is not None:
        by_site_stmt = by_site_stmt.where(Site.organization_id == organization_id)
    if site_id is not None:
        by_site_stmt = by_site_stmt.where(Site.id == site_id)
    by_site = (await session.execute(by_site_stmt)).all()
    opted_by_site = await opted_in_counts_by_site(session, [r[0] for r in by_site])
    return {
        "total": int(total),
        "opted_in": int(opted_in),
        "platforms": [(p, int(n)) for p, n in platforms],
        "versions": [(v, int(n)) for v, n in versions],
        "sites": [
            (sid, slug, name, int(n), opted_by_site.get(sid, 0))
            for sid, slug, name, n in by_site
        ],
    }


async def history_points(
    session: AsyncSession,
    site: Site,
    start: datetime,
    end: datetime,
) -> list[tuple[uuid.UUID | None, OccupancyHistory]]:
    """Site (``zone_id IS NULL``) and zone points of [start, end), by minute."""
    rows = await session.execute(
        select(OccupancyHistory)
        .where(
            OccupancyHistory.site_id == site.id,
            OccupancyHistory.organization_id == site.organization_id,
            OccupancyHistory.bucket_minute >= start,
            OccupancyHistory.bucket_minute < end,
        )
        .order_by(OccupancyHistory.bucket_minute)
    )
    return [(row.zone_id, row) for row in rows.scalars()]
