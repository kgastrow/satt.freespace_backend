"""M3 occupancy history (BF-4, D14): at most one point per minute per site and
per zone, last value in the minute wins. SQLite via the API, plus a
PostgreSQL-only test of the partial-index upsert."""

from __future__ import annotations

from datetime import timedelta, timezone

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.crud.freespace_history import bucket_minute, upsert_history_point
from src.models.occupancy_history import OccupancyHistory
from src.models.organization import Organization
from src.models.site import Site
from src.models.zone import Zone
from src.services.freespace.clock import ensure_utc
from tests.freespace.conftest import FIXED_START, unique_slug
from tests.freespace.test_m3_intake import OCCUPANCY, body, zone_block


async def _history(session, **where):
    query = select(OccupancyHistory).order_by(OccupancyHistory.bucket_minute)
    for column, value in where.items():
        column_attr = getattr(OccupancyHistory, column)
        query = query.where(
            column_attr.is_(None) if value is None else column_attr == value
        )
    result = await session.execute(query.execution_options(populate_existing=True))
    return list(result.scalars().all())


def test_bucket_minute_truncates():
    value = FIXED_START.replace(second=59, microsecond=999_999)
    assert bucket_minute(value) == FIXED_START.replace(second=0)


async def test_history_one_point_per_minute_last_wins(
    client, async_session, fixed_clock, fs_site, fs_zones, fs_ingest_headers
):
    fixed_clock.set(FIXED_START + timedelta(seconds=5))
    await client.post(
        OCCUPANCY,
        json=body(
            measured_at=fixed_clock.now(),
            occupied=100,
            zones=[zone_block("b1", occupied=10)],
        ),
        headers=fs_ingest_headers,
    )
    fixed_clock.advance(30)  # 05:45:35, same minute
    await client.post(
        OCCUPANCY,
        json=body(
            measured_at=fixed_clock.now(),
            occupied=150,
            zones=[zone_block("b1", occupied=20)],
        ),
        headers=fs_ingest_headers,
    )
    site_points = await _history(async_session, site_id=fs_site.id, zone_id=None)
    assert len(site_points) == 1
    point = site_points[0]
    assert (point.occupied, point.capacity, point.free_usable, point.health) == (
        150,
        400,
        250,
        "OK",
    )
    assert ensure_utc(point.bucket_minute) == FIXED_START
    zone_points = await _history(async_session, zone_id=fs_zones["b1"].id)
    assert [p.occupied for p in zone_points] == [20]

    fixed_clock.advance(30)  # 05:46:05, next minute
    await client.post(
        OCCUPANCY,
        json=body(
            measured_at=fixed_clock.now(),
            occupied=160,
            zones=[zone_block("b1", occupied=30)],
        ),
        headers=fs_ingest_headers,
    )
    site_points = await _history(async_session, site_id=fs_site.id, zone_id=None)
    assert [p.occupied for p in site_points] == [150, 160]
    assert ensure_utc(site_points[1].bucket_minute) == FIXED_START + timedelta(
        minutes=1
    )
    zone_points = await _history(async_session, zone_id=fs_zones["b1"].id)
    assert [p.occupied for p in zone_points] == [20, 30]
    # A zone not in the submissions gets no points.
    assert await _history(async_session, zone_id=fs_zones["b2"].id) == []
    assert all(p.organization_id == fs_site.organization_id for p in site_points)


async def test_history_bucketed_on_received_at(
    client, async_session, fs_site, fs_zones, fs_ingest_headers
):
    await client.post(
        OCCUPANCY,
        json=body(measured_at=FIXED_START - timedelta(minutes=7)),
        headers=fs_ingest_headers,
    )
    points = await _history(async_session, site_id=fs_site.id, zone_id=None)
    assert ensure_utc(points[0].bucket_minute) == FIXED_START


@pytest.mark.postgres
async def test_postgres_history_upsert_partial_indexes(fs_pg_engine):
    """Both partial unique indexes take the ON CONFLICT upsert on PostgreSQL."""
    maker = async_sessionmaker(fs_pg_engine, expire_on_commit=False)
    slug = unique_slug("m3")
    async with maker() as session:
        org = Organization(name=f"M3 {slug}", slug=slug, is_active=True)
        session.add(org)
        await session.flush()
        site = Site(
            organization_id=org.id, slug=slug, name="M3 PG", fcm_topic=f"fs-{slug}"
        )
        session.add(site)
        await session.flush()
        zone = Zone(
            organization_id=org.id, site_id=site.id, slug="b1", name="B1", enabled=True
        )
        session.add(zone)
        await session.commit()
        org_id, site_id, zone_id = org.id, site.id, zone.id

    try:
        at = FIXED_START.astimezone(timezone.utc)
        async with maker() as session:
            for occupied, offset in ((10, 1), (20, 40), (30, 70)):
                for target in (None, zone_id):
                    await upsert_history_point(
                        session,
                        organization_id=org_id,
                        site_id=site_id,
                        zone_id=target,
                        at=at + timedelta(seconds=offset),
                        occupied=occupied,
                        capacity=100,
                        free_usable=100 - occupied,
                        health="OK",
                    )
            await session.commit()

        async with maker() as session:
            rows = (
                (
                    await session.execute(
                        select(OccupancyHistory)
                        .where(OccupancyHistory.site_id == site_id)
                        .order_by(
                            OccupancyHistory.zone_id.nulls_first(),
                            OccupancyHistory.bucket_minute,
                        )
                    )
                )
                .scalars()
                .all()
            )
            summary = [(r.zone_id, r.bucket_minute, r.occupied) for r in rows]
            assert summary == [
                (None, at, 20),
                (None, at + timedelta(minutes=1), 30),
                (zone_id, at, 20),
                (zone_id, at + timedelta(minutes=1), 30),
            ]
    finally:
        async with maker() as session:
            await session.execute(
                delete(OccupancyHistory).where(OccupancyHistory.site_id == site_id)
            )
            await session.execute(delete(Zone).where(Zone.id == zone_id))
            await session.execute(
                text("DELETE FROM site_engine_state WHERE site_id = :id"),
                {"id": site_id},
            )
            await session.execute(delete(Site).where(Site.id == site_id))
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.commit()
