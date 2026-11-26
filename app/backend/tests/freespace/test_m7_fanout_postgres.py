"""BT-02 on real PostgreSQL: a fan-out killed mid-way and restarted (and two
concurrent runs) never send an advisory to any device twice.

Skips unless ``TEST_DATABASE_URL_DIRECT`` points at a migrated database
(``fs_pg_engine``). Commits for real and deletes everything it created.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.constants.freespace import DeviceOutcome, FanoutStatus
from src.models.device import Device, DeviceSite
from src.models.organization import Organization
from src.models.push_send import PushSend
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.models.site_message_template import SiteMessageTemplate
from src.services.freespace import fanout as fanout_module
from src.services.freespace.fanout import run_fanout
from tests.freespace.conftest import make_site, unique_slug
from tests.freespace.test_m7_support import (
    drive_fanout,
    install_engine_recorder,
    make_advisory_event,
    make_devices,
)


pytestmark = pytest.mark.postgres


class Crash(RuntimeError):
    pass


async def _cleanup(factory, org_id: uuid.UUID, site_id: uuid.UUID, device_ids):
    async with factory() as session:
        await session.execute(delete(PushSend).where(PushSend.site_id == site_id))
        await session.execute(delete(SiteEvent).where(SiteEvent.site_id == site_id))
        await session.execute(
            delete(DeviceSite).where(DeviceSite.device_id.in_(device_ids))
        )
        await session.execute(delete(Device).where(Device.id.in_(device_ids)))
        await session.execute(
            delete(SiteMessageTemplate).where(SiteMessageTemplate.site_id == site_id)
        )
        await session.execute(
            delete(SiteEngineState).where(SiteEngineState.site_id == site_id)
        )
        await session.execute(delete(Site).where(Site.id == site_id))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()


@pytest.fixture
async def pg_setup(fs_pg_engine, fixed_clock, monkeypatch):
    install_engine_recorder(monkeypatch)
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    slug = unique_slug("m7")
    async with factory() as session:
        org = Organization(name=f"M7 {slug}", slug=slug, is_active=True)
        session.add(org)
        await session.commit()
        site = await make_site(session, org, slug=slug, now=fixed_clock.now())
        devices = await make_devices(
            session, [site], 40, now=fixed_clock.now(), prefix=slug
        )
        event = await make_advisory_event(session, site, now=fixed_clock.now())
    try:
        yield factory, site, devices, event
    finally:
        await _cleanup(factory, org.id, site.id, [d.id for d in devices])


async def _rows(factory, event_id):
    async with factory() as session:
        return list(
            (
                await session.execute(
                    select(PushSend).where(PushSend.event_id == event_id)
                )
            )
            .scalars()
            .all()
        )


async def test_bt02_killed_mid_fanout_then_restarted(
    pg_setup, fixed_clock, fake_fcm, monkeypatch
):
    factory, site, devices, event = pg_setup
    # chunk 1 completes
    first = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=10
    )
    assert first.reenqueue_in_s == 0
    # chunk 2: killed after FCM accepted, before the outcomes were written
    real_record = fanout_module._record_outcomes

    async def die(*args, **kwargs):
        raise Crash("SIGKILL after send")

    monkeypatch.setattr(fanout_module, "_record_outcomes", die)
    with pytest.raises(Crash):
        await run_fanout(
            factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=10
        )
    monkeypatch.setattr(fanout_module, "_record_outcomes", real_record)
    # chunk 3: killed after the rows were committed, before FCM was called
    real_send = fanout_module._send_claimed

    async def die_before_send(*args, **kwargs):
        raise Crash("SIGKILL before send")

    monkeypatch.setattr(fanout_module, "_send_claimed", die_before_send)
    with pytest.raises(Crash):
        await run_fanout(
            factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=10
        )
    monkeypatch.setattr(fanout_module, "_send_claimed", real_send)

    # Restart (fresh "process"): resume to the end.
    await drive_fanout(factory, event.id, fixed_clock, fake_fcm, chunk_size=10)

    sent = fake_fcm.sent_tokens
    assert len(sent) == len(set(sent)) == 30  # 10 lost before send, none twice
    rows = await _rows(factory, event.id)
    assert len(rows) == len({r.device_id for r in rows}) == 40
    counts = {}
    for row in rows:
        counts[row.outcome] = counts.get(row.outcome, 0) + 1
    # BF-62: the 20 crashed rows finish as SEND_FAILED / UNKNOWN_AFTER_CRASH
    assert counts == {
        DeviceOutcome.SENT.value: 20,
        DeviceOutcome.SEND_FAILED.value: 20,
    }
    assert {r.error_code for r in rows if r.outcome != "SENT"} == {
        "UNKNOWN_AFTER_CRASH"
    }
    async with factory() as session:
        stored = await session.get(SiteEvent, event.id)
        assert stored is not None
        assert stored.fanout_status == FanoutStatus.COMPLETED.value


async def test_concurrent_runs_never_double_send(pg_setup, fixed_clock, fake_fcm):
    """Several workers on the same event at once (duplicate jobs)."""
    factory, site, devices, event = pg_setup

    async def worker():
        return await drive_fanout(
            factory, event.id, fixed_clock, fake_fcm, chunk_size=7
        )

    await asyncio.gather(*(worker() for _ in range(4)))
    # Duplicates that hit a held lease stop; finish whatever is left.
    await drive_fanout(factory, event.id, fixed_clock, fake_fcm, chunk_size=7)

    sent = fake_fcm.sent_tokens
    assert len(sent) == len(set(sent)) == 40
    rows = await _rows(factory, event.id)
    assert len(rows) == 40 and {r.outcome for r in rows} == {"SENT"}
