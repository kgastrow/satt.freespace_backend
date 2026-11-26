"""Read-side queries for the Freespace event log (M8). Callers resolve the
site with tenant scoping first; every query is then filtered by ``site_id``
AND the site's ``organization_id``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.site import Site
from src.models.site_event import SiteEvent


def _filtered(
    site: Site,
    *,
    event_type: str | None,
    reason: str | None,
    start: datetime | None,
    end: datetime | None,
) -> Select[tuple[SiteEvent]]:
    stmt = select(SiteEvent).where(
        SiteEvent.site_id == site.id,
        SiteEvent.organization_id == site.organization_id,
    )
    if event_type:
        stmt = stmt.where(SiteEvent.type == event_type)
    if reason:
        stmt = stmt.where(SiteEvent.reason == reason)
    if start is not None:
        stmt = stmt.where(SiteEvent.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(SiteEvent.occurred_at < end)
    return stmt


async def list_events(
    session: AsyncSession,
    site: Site,
    *,
    event_type: str | None,
    reason: str | None,
    start: datetime | None,
    end: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[SiteEvent], int]:
    base = _filtered(site, event_type=event_type, reason=reason, start=start, end=end)
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(SiteEvent.occurred_at.desc(), SiteEvent.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def count_events(
    session: AsyncSession,
    site: Site,
    *,
    event_type: str | None,
    reason: str | None,
    start: datetime | None,
    end: datetime | None,
) -> int:
    base = _filtered(site, event_type=event_type, reason=reason, start=start, end=end)
    return int(
        (
            await session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
    )


async def export_events(
    session: AsyncSession,
    site: Site,
    *,
    event_type: str | None,
    reason: str | None,
    start: datetime | None,
    end: datetime | None,
    limit: int,
) -> list[SiteEvent]:
    base = _filtered(site, event_type=event_type, reason=reason, start=start, end=end)
    rows = (
        (
            await session.execute(
                base.order_by(SiteEvent.occurred_at.desc(), SiteEvent.id).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
