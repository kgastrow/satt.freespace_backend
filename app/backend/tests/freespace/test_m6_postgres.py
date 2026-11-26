"""BT-01 on real PostgreSQL: two evaluations of one site that start at once
produce exactly one advisory (the ``site_engine_state`` row lock, D6).

Skips unless ``TEST_DATABASE_URL_DIRECT`` points at a migrated database
(``fs_pg_engine``). Commits for real and deletes everything it created.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.constants.freespace import EngineState, EventType, Health
from src.models.organization import Organization
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.models.site_message_template import SiteMessageTemplate
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.models.zone import Zone
from src.services.freespace import evaluator
from src.services.freespace.evaluator import evaluate_site
from tests.freespace.conftest import make_site, make_zone, unique_slug


pytestmark = pytest.mark.postgres


def _counts(capacity: int, occupied: int) -> dict:
    return {
        "capacity": capacity,
        "occupied": occupied,
        "free_usable": capacity - occupied,
        "free_reserved": 0,
        "free_disabled": 0,
        "unknown": 0,
        "health": Health.OK.value,
        "reported_health": Health.OK.value,
    }


async def _cleanup(factory, org_id: uuid.UUID, site_id: uuid.UUID) -> None:
    async with factory() as session:
        for model in (ZoneSnapshot, SiteSnapshot, SiteEvent, SiteMessageTemplate):
            await session.execute(delete(model).where(model.site_id == site_id))
        await session.execute(delete(Zone).where(Zone.site_id == site_id))
        await session.execute(
            delete(SiteEngineState).where(SiteEngineState.site_id == site_id)
        )
        await session.execute(delete(Site).where(Site.id == site_id))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()


@pytest.fixture
async def pg_site(fs_pg_engine, fixed_clock):
    """A managed site, PENDING at 90 % for exactly S: the next evaluation
    raises SITE_INITIAL."""
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    slug = unique_slug("m6")
    now = fixed_clock.now()
    async with factory() as session:
        org = Organization(name=f"M6 {slug}", slug=slug, is_active=True)
        session.add(org)
        await session.commit()
        site = await make_site(session, org, slug=slug, now=now)
        zones = [
            await make_zone(session, site, f"b{i}", display_order=i) for i in (1, 2)
        ]
        session.add(
            SiteSnapshot(
                organization_id=org.id,
                site_id=site.id,
                measured_at=now,
                received_at=now,
                **_counts(1000, 900),
            )
        )
        for zone, occupied in zip(zones, (240, 150), strict=True):
            session.add(
                ZoneSnapshot(
                    organization_id=org.id,
                    site_id=site.id,
                    zone_id=zone.id,
                    measured_at=now,
                    received_at=now,
                    **_counts(250, occupied),
                )
            )
        state = (
            await session.execute(
                select(SiteEngineState).where(SiteEngineState.site_id == site.id)
            )
        ).scalar_one()
        state.state = EngineState.PENDING.value
        state.pending_since = now - timedelta(seconds=site.stabilisation_s)
        state.stale = False
        await session.commit()
    try:
        yield factory, site
    finally:
        await _cleanup(factory, org.id, site.id)


async def test_bt01_concurrent_evaluations_one_advisory(
    pg_site, fixed_clock, monkeypatch
):
    factory, site = pg_site
    # Widen the race window: each evaluation pauses after taking the lock and
    # before reading the snapshot, so both are guaranteed to overlap.
    real_load_snapshot = evaluator.load_snapshot
    entered: list[str] = []

    async def slow_load_snapshot(session, site_id):
        entered.append("in")
        await asyncio.sleep(0.3)
        return await real_load_snapshot(session, site_id)

    monkeypatch.setattr(evaluator, "load_snapshot", slow_load_snapshot)

    async def one() -> evaluator.EvaluatedSiteView:
        async with factory() as session:
            view = await evaluate_site(session, site.id, fixed_clock)
            await session.commit()
            return view

    views = await asyncio.gather(one(), one())

    assert all(v.state is EngineState.ACTIVE for v in views)
    assert sorted(len(v.fanout_event_ids) for v in views) == [0, 1]
    async with factory() as session:
        advisories = (
            (
                await session.execute(
                    select(SiteEvent).where(
                        SiteEvent.site_id == site.id,
                        SiteEvent.type == EventType.ADVISORY.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        stabilised = (
            (
                await session.execute(
                    select(SiteEvent).where(
                        SiteEvent.site_id == site.id,
                        SiteEvent.type == EventType.STATE_CHANGE.value,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(advisories) == 1
    assert len(stabilised) == 1  # the second evaluation saw ACTIVE
    assert len(entered) == 2
