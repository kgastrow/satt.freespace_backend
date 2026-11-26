"""M9 purge (BF-73, D12, D14) on real PostgreSQL: ``FOR UPDATE SKIP LOCKED``
device erasure does not wait for and does not touch a device another
transaction holds, batched hard deletes commit per batch and stop at the
cut-off, and events take their send rows with them (foreign key).

Skips unless ``TEST_DATABASE_URL_DIRECT`` points at a migrated database
(``fs_pg_engine``). The database may be shared with real data, so every row
this test creates is dated in 2001 and the purge is run with a ``now`` in
2001: the cut-offs then lie before any real row. A pre-check skips the test
if anything else in the database is that old. Everything created is deleted
in the finally block.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.device import Device, DeviceSite
from src.models.occupancy_history import OccupancyHistory
from src.models.organization import Organization
from src.models.push_send import PushSend
from src.models.request_log import RequestLog
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.models.site_message_template import SiteMessageTemplate
from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot
from src.services.freespace import purge
from tests.freespace.conftest import make_site, unique_slug


pytestmark = pytest.mark.postgres

NOW = datetime(2001, 6, 1, 12, 0, tzinfo=UTC)
DAYS = 30
CUTOFF = NOW - timedelta(days=DAYS)
OLD = CUTOFF - timedelta(days=1)
FRESH = CUTOFF + timedelta(days=1)


async def _foreign_rows_before_cutoff(session: AsyncSession, mine: dict) -> int:
    checks = [
        (Device, Device.last_seen, Device.id, mine["devices"]),
        (RequestLog, RequestLog.created_time, RequestLog.id, mine["logs"]),
        (PushSend, PushSend.queued_at, PushSend.id, []),
        (SiteEvent, SiteEvent.last_seen_at, SiteEvent.id, []),
        (OccupancyHistory, OccupancyHistory.bucket_minute, OccupancyHistory.id, []),
    ]
    total = 0
    for model, column, id_col, ids in checks:
        query = select(func.count()).select_from(model).where(column < CUTOFF)
        if ids:
            query = query.where(id_col.not_in(ids))
        if model is not Device and "site_id" in model.__table__.c and mine["site"]:
            query = query.where(model.__table__.c.site_id != mine["site"])
        if model is Device:
            query = query.where(Device.deleted_time.is_(None))
        total += int((await session.execute(query)).scalar_one())
    return total


def _device(suffix: str, seen: datetime) -> Device:
    return Device(
        device_key_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        id_suffix=suffix,
        fcm_token="pgtok-" + uuid.uuid4().hex,
        platform="ANDROID",
        notifications_enabled=True,
        first_seen=seen,
        last_seen=seen,
    )


async def test_purge_skip_locked_and_batched_deletes_on_postgres(fs_pg_engine):
    factory = async_sessionmaker(
        bind=fs_pg_engine, class_=AsyncSession, expire_on_commit=False
    )
    slug = unique_slug("m9")
    mine: dict = {"devices": [], "logs": [], "site": None, "org": None}
    try:
        async with factory() as session:
            org = Organization(name=f"M9 {slug}", slug=slug, is_active=True)
            session.add(org)
            await session.commit()
            mine["org"] = org.id
            site = await make_site(session, org, slug=slug, now=OLD)
            mine["site"] = site.id

            old_devices = [_device(f"OLD{i:03d}", OLD) for i in range(5)]
            fresh_device = _device("FRESH0", FRESH)
            session.add_all([*old_devices, fresh_device])
            await session.flush()
            mine["devices"] = [d.id for d in (*old_devices, fresh_device)]
            session.add_all(
                DeviceSite(device_id=d.id, site_id=site.id) for d in old_devices
            )
            logs = [
                RequestLog(
                    method="GET",
                    path=f"/pg-purge/{slug}/{i}",
                    status_code=200,
                    duration_ms=1,
                    created_time=OLD if i < 7 else FRESH,
                )
                for i in range(9)
            ]
            session.add_all(logs)
            old_event = SiteEvent(
                organization_id=org.id,
                site_id=site.id,
                occurred_at=OLD,
                last_seen_at=OLD,
                repeat_count=1,
                type="CANDIDATE",
            )
            fresh_event = SiteEvent(
                organization_id=org.id,
                site_id=site.id,
                occurred_at=FRESH,
                last_seen_at=FRESH,
                repeat_count=1,
                type="CANDIDATE",
            )
            session.add_all([old_event, fresh_event])
            await session.flush()
            mine["logs"] = [log.id for log in logs]
            # Send row of the OLD event, itself recent: goes with its event.
            session.add(
                PushSend(
                    organization_id=org.id,
                    event_id=old_event.id,
                    device_id=fresh_device.id,
                    site_id=site.id,
                    advisory_type="SITE_CHANGE",
                    fingerprint="f" * 64,
                    outcome="SENT",
                    queued_at=FRESH,
                )
            )
            session.add_all(
                OccupancyHistory(
                    organization_id=org.id,
                    site_id=site.id,
                    bucket_minute=OLD - timedelta(minutes=i) if i < 4 else FRESH,
                    occupied=1,
                    capacity=10,
                    free_usable=9,
                    health="OK",
                )
                for i in range(5)
            )
            await session.commit()
            fresh_event_id = fresh_event.id

            if await _foreign_rows_before_cutoff(session, mine):
                pytest.skip("database holds real rows dated before 2001-05-02")

        locked_id = old_devices[0].id
        # Another transaction (e.g. a PUT /v1/devices) holds one old device.
        async with fs_pg_engine.connect() as holder:
            tx = await holder.begin()
            await holder.execute(
                select(Device.id).where(Device.id == locked_id).with_for_update()
            )
            async with factory() as session:
                erased = await asyncio.wait_for(
                    purge.purge_inactive_devices(session, NOW, DAYS, batch_size=2),
                    timeout=10,
                )
            assert erased == 4  # skipped the locked one, did not wait for it
            await tx.rollback()

        async with factory() as session:
            rows = {
                d.id: d
                for d in (
                    await session.execute(
                        select(Device).where(Device.id.in_(mine["devices"]))
                    )
                )
                .scalars()
                .all()
            }
            assert rows[locked_id].fcm_token is not None
            assert rows[locked_id].deleted_time is None
            for device in old_devices[1:]:
                assert rows[device.id].fcm_token is None
                assert rows[device.id].device_key_hash is None
                assert rows[device.id].deleted_time is not None
            assert rows[fresh_device.id].deleted_time is None
            links = (
                (
                    await session.execute(
                        select(DeviceSite.device_id).where(
                            DeviceSite.site_id == site.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert links == [locked_id]

            # Lock released: the next run erases it; a re-run then finds nothing.
            assert await purge.purge_inactive_devices(session, NOW, DAYS, 2) == 1
            assert await purge.purge_inactive_devices(session, NOW, DAYS, 2) == 0

            # Batched hard deletes, committing per batch of 3.
            assert await purge.purge_request_logs(session, NOW, DAYS, 3) == 7
            assert await purge.purge_occupancy_history(session, NOW, DAYS, 3) == 4
            assert await purge.purge_events(session, NOW, DAYS, 1) == 1
            assert await purge.purge_request_logs(session, NOW, DAYS, 3) == 0

        async with factory() as session:  # fresh connection: really committed
            left_logs = (
                await session.execute(
                    select(func.count())
                    .select_from(RequestLog)
                    .where(RequestLog.id.in_(mine["logs"]))
                )
            ).scalar_one()
            assert left_logs == 2
            left_history = (
                await session.execute(
                    select(func.count())
                    .select_from(OccupancyHistory)
                    .where(OccupancyHistory.site_id == site.id)
                )
            ).scalar_one()
            assert left_history == 1
            events = (
                (
                    await session.execute(
                        select(SiteEvent.id).where(SiteEvent.site_id == site.id)
                    )
                )
                .scalars()
                .all()
            )
            assert events == [fresh_event_id]
            sends = (
                await session.execute(
                    select(func.count())
                    .select_from(PushSend)
                    .where(PushSend.site_id == site.id)
                )
            ).scalar_one()
            assert sends == 0
    finally:
        async with factory() as session:
            site_id, org_id = mine["site"], mine["org"]
            if site_id is not None:
                for model in (
                    PushSend,
                    OccupancyHistory,
                    ZoneSnapshot,
                    SiteSnapshot,
                    SiteEvent,
                    SiteMessageTemplate,
                    SiteEngineState,
                ):
                    await session.execute(delete(model).where(model.site_id == site_id))
                await session.execute(
                    delete(DeviceSite).where(DeviceSite.site_id == site_id)
                )
            if mine["devices"]:
                await session.execute(
                    delete(PushSend).where(PushSend.device_id.in_(mine["devices"]))
                )
                await session.execute(
                    delete(DeviceSite).where(DeviceSite.device_id.in_(mine["devices"]))
                )
                await session.execute(
                    delete(Device).where(Device.id.in_(mine["devices"]))
                )
            if mine["logs"]:
                await session.execute(
                    delete(RequestLog).where(RequestLog.id.in_(mine["logs"]))
                )
            if site_id is not None:
                from src.models.zone import Zone

                await session.execute(delete(Zone).where(Zone.site_id == site_id))
                await session.execute(delete(Site).where(Site.id == site_id))
            if org_id is not None:
                await session.execute(
                    delete(Organization).where(Organization.id == org_id)
                )
            await session.commit()
