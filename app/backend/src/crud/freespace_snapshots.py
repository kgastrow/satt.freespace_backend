"""
Latest-snapshot rows (BF-3): one ``site_snapshot`` per site and one
``zone_snapshot`` per zone, overwritten on every accepted submission. OWNER: M3.

Callers resolve the site first (intake: by ingest key). Every query is also
filtered by the site's ``organization_id`` (CLAUDE.md rule 1). Flush only;
the caller owns the transaction. Timestamps come from the caller (Freespace
clock), never from column defaults.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.site import Site
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot


@dataclass(frozen=True)
class SnapshotValues:
    """Figures written to a snapshot row (``health`` = effective, BF-12)."""

    capacity: int
    occupied: int
    free_usable: int
    free_reserved: int
    free_disabled: int
    unknown: int
    health: str
    reported_health: str
    measured_at: datetime
    received_at: datetime

    def as_columns(self) -> dict[str, Any]:
        return {
            "capacity": self.capacity,
            "occupied": self.occupied,
            "free_usable": self.free_usable,
            "free_reserved": self.free_reserved,
            "free_disabled": self.free_disabled,
            "unknown": self.unknown,
            "health": self.health,
            "reported_health": self.reported_health,
            "measured_at": self.measured_at,
            "received_at": self.received_at,
        }


async def get_site_snapshot(session: AsyncSession, site: Site) -> SiteSnapshot | None:
    """The site's latest snapshot row, if any."""
    result = await session.execute(
        select(SiteSnapshot).where(
            SiteSnapshot.site_id == site.id,
            SiteSnapshot.organization_id == site.organization_id,
        )
    )
    return result.scalars().first()


async def get_zone_snapshots(
    session: AsyncSession, site: Site, zone_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, ZoneSnapshot]:
    """Latest snapshot rows of the given zones of ``site``, keyed by zone id."""
    ids = list(zone_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(ZoneSnapshot).where(
            ZoneSnapshot.site_id == site.id,
            ZoneSnapshot.organization_id == site.organization_id,
            ZoneSnapshot.zone_id.in_(ids),
        )
    )
    return {row.zone_id: row for row in result.scalars().all()}


async def upsert_site_snapshot(
    session: AsyncSession,
    site: Site,
    values: SnapshotValues,
    *,
    publisher: dict[str, Any] | None,
    existing: SiteSnapshot | None = None,
) -> SiteSnapshot:
    """Overwrite (or create) the site's snapshot row. Pass ``existing`` when
    already loaded to save a query."""
    row = existing if existing is not None else await get_site_snapshot(session, site)
    if row is None:
        row = SiteSnapshot(
            organization_id=site.organization_id,
            site_id=site.id,
            publisher=publisher,
            **values.as_columns(),
        )
        session.add(row)
    else:
        for column, value in values.as_columns().items():
            setattr(row, column, value)
        row.publisher = publisher
    await session.flush()
    return row


async def upsert_zone_snapshot(
    session: AsyncSession,
    site: Site,
    zone_id: uuid.UUID,
    values: SnapshotValues,
    *,
    existing: ZoneSnapshot | None = None,
) -> ZoneSnapshot:
    """Overwrite (or create) one zone's snapshot row. The caller passes the
    row from ``get_zone_snapshots`` (``None`` = create)."""
    row = existing
    if row is None:
        row = ZoneSnapshot(
            organization_id=site.organization_id,
            site_id=site.id,
            zone_id=zone_id,
            **values.as_columns(),
        )
        session.add(row)
    else:
        for column, value in values.as_columns().items():
            setattr(row, column, value)
    await session.flush()
    return row
