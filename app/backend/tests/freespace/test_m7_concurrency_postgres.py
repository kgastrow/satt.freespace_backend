"""BT-08 / BF-63 on real PostgreSQL: concurrent fan-outs of DIFFERENT events
(two sites going ACTIVE in the same tick) never both send to one phone in
``limitScope = DEVICE``; the claim locks the chunk's device rows. Plus the
5 000-device throughput with that lock.

Skips unless ``TEST_DATABASE_URL_DIRECT`` points at a migrated database
(``fs_pg_engine``). Commits for real and deletes everything it created.
"""

from __future__ import annotations

import asyncio
from collections import Counter
import time
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.constants.freespace import DeviceOutcome
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
    reload_event,
    use_deployment_settings,
)


pytestmark = pytest.mark.postgres


async def _cleanup(factory, org_id: uuid.UUID, site_ids, device_ids) -> None:
    async with factory() as session:
        for site_id in site_ids:
            await session.execute(delete(PushSend).where(PushSend.site_id == site_id))
            await session.execute(delete(SiteEvent).where(SiteEvent.site_id == site_id))
        for start in range(0, len(device_ids), 1000):
            batch = device_ids[start : start + 1000]
            await session.execute(
                delete(DeviceSite).where(DeviceSite.device_id.in_(batch))
            )
            await session.execute(delete(Device).where(Device.id.in_(batch)))
        for site_id in site_ids:
            await session.execute(
                delete(SiteMessageTemplate).where(
                    SiteMessageTemplate.site_id == site_id
                )
            )
            await session.execute(
                delete(SiteEngineState).where(SiteEngineState.site_id == site_id)
            )
            await session.execute(delete(Site).where(Site.id == site_id))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()


async def test_bt08_two_sites_same_tick_one_push(
    fs_pg_engine, fixed_clock, fake_fcm, monkeypatch
):
    """Review R2 repro: both claims read the history before either commits
    (forced with a barrier) -> two pushes to one phone. With the device lock
    the second claim waits, sees the first PENDING row, records COOLDOWN."""
    install_engine_recorder(monkeypatch)
    use_deployment_settings(monkeypatch, cooldown_s=1800, daily_cap=2)
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    slug = unique_slug("m7c")
    async with factory() as session:
        org = Organization(name=f"M7C {slug}", slug=slug, is_active=True)
        session.add(org)
        await session.commit()
        site_a = await make_site(session, org, slug=slug + "a", now=fixed_clock.now())
        site_b = await make_site(session, org, slug=slug + "b", now=fixed_clock.now())
        devices = await make_devices(
            session, [site_a, site_b], 3, now=fixed_clock.now(), prefix=slug
        )
        event_a = await make_advisory_event(session, site_a, now=fixed_clock.now())
        event_b = await make_advisory_event(session, site_b, now=fixed_clock.now())

    real = fanout_module.evaluate_device_checks
    arrived = 0
    both_in = asyncio.Event()

    async def barrier(*args, **kwargs):
        nonlocal arrived
        out = await real(*args, **kwargs)
        arrived += 1
        if arrived >= 2:
            both_in.set()
        try:  # without the lock both get here before either commits
            await asyncio.wait_for(both_in.wait(), 1.5)
        except asyncio.TimeoutError:
            pass
        return out

    monkeypatch.setattr(fanout_module, "evaluate_device_checks", barrier)
    try:
        await asyncio.gather(
            run_fanout(factory, event_a.id, clock=fixed_clock, fcm=fake_fcm),
            run_fanout(factory, event_b.id, clock=fixed_clock, fcm=fake_fcm),
        )
        counts = Counter(fake_fcm.sent_tokens)
        assert sorted(counts) == sorted(d.fcm_token for d in devices)
        assert set(counts.values()) == {1}, counts
        async with factory() as session:
            a = (await reload_event(session, event_a.id)).counts
            b = (await reload_event(session, event_b.id)).counts
        assert sorted([a, b], key=lambda c: sorted(c)) == [
            {"COOLDOWN": 3},
            {"SENT": 3},
        ], (a, b)
    finally:
        await _cleanup(factory, org.id, [site_a.id, site_b.id], [d.id for d in devices])


async def test_bt08_concurrent_chunked_fanouts_no_double_send_no_deadlock(
    fs_pg_engine, fixed_clock, fake_fcm, monkeypatch
):
    """Three sites, 900 shared phones, chunks of 100, all fan-outs driven
    concurrently: every phone gets exactly one push; no deadlock."""
    install_engine_recorder(monkeypatch)
    use_deployment_settings(monkeypatch, cooldown_s=1800, daily_cap=2)
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    slug = unique_slug("m7c")
    async with factory() as session:
        org = Organization(name=f"M7C {slug}", slug=slug, is_active=True)
        session.add(org)
        await session.commit()
        sites = [
            await make_site(session, org, slug=f"{slug}{i}", now=fixed_clock.now())
            for i in range(3)
        ]
        devices = await make_devices(
            session, sites, 900, now=fixed_clock.now(), prefix=slug
        )
        events = [
            await make_advisory_event(session, site, now=fixed_clock.now())
            for site in sites
        ]
    try:
        await asyncio.wait_for(
            asyncio.gather(
                *(
                    drive_fanout(factory, e.id, fixed_clock, fake_fcm, chunk_size=100)
                    for e in events
                )
            ),
            timeout=120,
        )
        counts = Counter(fake_fcm.sent_tokens)
        assert len(counts) == 900
        assert set(counts.values()) == {1}
        total: Counter[str] = Counter()
        async with factory() as session:
            for e in events:
                total.update((await reload_event(session, e.id)).counts or {})
        assert total == {
            DeviceOutcome.SENT.value: 900,
            DeviceOutcome.COOLDOWN.value: 1800,
        }
    finally:
        await _cleanup(factory, org.id, [s.id for s in sites], [d.id for d in devices])


async def test_throughput_5000_devices_with_device_lock(
    fs_pg_engine, fixed_clock, fake_fcm, monkeypatch
):
    install_engine_recorder(monkeypatch)
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    slug = unique_slug("m7c")
    async with factory() as session:
        org = Organization(name=f"M7C {slug}", slug=slug, is_active=True)
        session.add(org)
        await session.commit()
        site = await make_site(session, org, slug=slug, now=fixed_clock.now())
        devices = await make_devices(
            session, [site], 5000, now=fixed_clock.now(), prefix=slug
        )
        event = await make_advisory_event(session, site, now=fixed_clock.now())
    try:
        started = time.perf_counter()
        await drive_fanout(factory, event.id, fixed_clock, fake_fcm)
        elapsed = time.perf_counter() - started
        assert len(fake_fcm.sent_tokens) == len(set(fake_fcm.sent_tokens)) == 5000
        assert elapsed < 30, f"fan-out of 5000 on PostgreSQL took {elapsed:.1f}s"
        print(f"5000-device fan-out on PostgreSQL: {elapsed:.2f}s")
    finally:
        await _cleanup(factory, org.id, [site.id], [d.id for d in devices])
