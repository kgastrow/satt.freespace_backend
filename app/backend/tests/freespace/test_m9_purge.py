"""M9: daily purge (BF-73, D12, D14)."""

from __future__ import annotations

from datetime import timedelta
import uuid

import pytest
from sqlalchemy import func, select

from src.models.device import Device, DeviceSite
from src.models.occupancy_history import OccupancyHistory
from src.models.push_send import PushSend
from src.models.request_log import RequestLog
from src.models.site_event import SiteEvent
from src.models.system_config import SystemConfig
from src.services.cron.freespace_purge import (
    cleanup_old_request_logs_configured_handler,
    freespace_daily_purge_handler,
)
from src.services.freespace.deployment_settings import (
    DeploymentSettings,
    invalidate_deployment_settings_cache,
)
from src.services.freespace.purge import run_purge


EPS = timedelta(seconds=1)


async def count(session, model) -> int:
    session.expire_all()
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def make_device(
    session, now, *, age_days: float, suffix: str = "ABC123"
) -> Device:
    seen = now - timedelta(days=age_days)
    device = Device(
        device_key_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        id_suffix=suffix,
        fcm_token="tok-" + uuid.uuid4().hex,
        platform="ANDROID",
        notifications_enabled=True,
        first_seen=seen,
        last_seen=seen,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device


async def make_event(session, site, when, *, last_seen=None) -> SiteEvent:
    event = SiteEvent(
        organization_id=site.organization_id,
        site_id=site.id,
        occurred_at=when,
        last_seen_at=last_seen or when,
        repeat_count=1,
        type="CANDIDATE",
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@pytest.mark.asyncio
async def test_devices_retention_cutoff_and_erasure(
    async_session, fs_site, fixed_clock
):
    now = fixed_clock.now()
    old = await make_device(async_session, now, age_days=90, suffix="OLD000")
    old.last_seen = now - timedelta(days=90) - EPS
    keep = await make_device(async_session, now, age_days=90, suffix="KEEP00")
    keep.last_seen = now - timedelta(days=90) + EPS
    async_session.add_all(
        [
            DeviceSite(device_id=old.id, site_id=fs_site.id),
            DeviceSite(device_id=keep.id, site_id=fs_site.id),
        ]
    )
    await async_session.commit()
    old_id, keep_id = old.id, keep.id

    result = await run_purge(async_session, fixed_clock)

    assert result.devices_erased == 1
    async_session.expire_all()
    erased = await async_session.get(Device, old_id)
    assert erased.fcm_token is None
    assert erased.device_key_hash is None
    assert erased.id_suffix is None
    assert erased.deleted_time is not None
    kept = await async_session.get(Device, keep_id)
    assert kept.fcm_token is not None and kept.deleted_time is None
    links = (await async_session.execute(select(DeviceSite.device_id))).scalars().all()
    assert links == [keep_id]


@pytest.mark.asyncio
async def test_purge_is_idempotent_and_skips_tombstones(
    async_session, fs_site, fixed_clock
):
    now = fixed_clock.now()
    await make_device(async_session, now, age_days=200)
    first = await run_purge(async_session, fixed_clock)
    second = await run_purge(async_session, fixed_clock)
    assert first.devices_erased == 1
    assert second.to_dict() == {
        "devices_erased": 0,
        "send_history_deleted": 0,
        "events_deleted": 0,
        "occupancy_history_deleted": 0,
        "request_logs_deleted": 0,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_send_history_cutoff(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    event = await make_event(async_session, fs_site, now)
    for queued in (now - timedelta(days=35) - EPS, now - timedelta(days=35) + EPS):
        device = await make_device(async_session, now, age_days=1)
        async_session.add(
            PushSend(
                organization_id=fs_site.organization_id,
                event_id=event.id,
                device_id=device.id,
                site_id=fs_site.id,
                advisory_type="SITE_CHANGE",
                fingerprint="f" * 64,
                outcome="SENT",
                queued_at=queued,
            )
        )
    await async_session.commit()

    result = await run_purge(async_session, fixed_clock)

    assert result.send_history_deleted == 1
    assert await count(async_session, PushSend) == 1
    remaining = (await async_session.execute(select(PushSend.queued_at))).scalar_one()
    assert remaining.replace(tzinfo=None) == (now - timedelta(days=35) + EPS).replace(
        tzinfo=None
    )


@pytest.mark.asyncio
async def test_event_log_cutoff_uses_last_activity(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    cutoff = now - timedelta(days=365)
    await make_event(async_session, fs_site, cutoff - EPS)  # expired
    await make_event(async_session, fs_site, cutoff + EPS)  # just inside
    # old first occurrence but refreshed recently by collapse: stays
    await make_event(async_session, fs_site, cutoff - timedelta(days=30), last_seen=now)

    result = await run_purge(async_session, fixed_clock)

    assert result.events_deleted == 1
    assert await count(async_session, SiteEvent) == 2


@pytest.mark.asyncio
async def test_expired_event_takes_its_send_rows(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    event = await make_event(async_session, fs_site, now - timedelta(days=400))
    device = await make_device(async_session, now, age_days=1)
    async_session.add(
        PushSend(
            organization_id=fs_site.organization_id,
            event_id=event.id,
            device_id=device.id,
            site_id=fs_site.id,
            advisory_type="SITE_CHANGE",
            fingerprint="f" * 64,
            outcome="SENT",
            queued_at=now - timedelta(days=1),  # within send-history retention
        )
    )
    await async_session.commit()

    await run_purge(async_session, fixed_clock)

    assert await count(async_session, SiteEvent) == 0
    assert await count(async_session, PushSend) == 0


@pytest.mark.asyncio
async def test_occupancy_history_cutoff(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    cutoff = now - timedelta(days=180)
    for bucket in (cutoff - EPS, cutoff + EPS):
        async_session.add(
            OccupancyHistory(
                organization_id=fs_site.organization_id,
                site_id=fs_site.id,
                zone_id=None,
                bucket_minute=bucket,
                occupied=1,
                capacity=10,
                free_usable=9,
                health="OK",
            )
        )
    await async_session.commit()

    result = await run_purge(async_session, fixed_clock)

    assert result.occupancy_history_deleted == 1
    assert await count(async_session, OccupancyHistory) == 1


@pytest.mark.asyncio
async def test_batches_commit_and_cover_all_rows(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    for i in range(7):
        async_session.add(
            OccupancyHistory(
                organization_id=fs_site.organization_id,
                site_id=fs_site.id,
                zone_id=None,
                bucket_minute=now - timedelta(days=200, minutes=i),
                occupied=1,
                capacity=10,
                free_usable=9,
                health="OK",
            )
        )
    await async_session.commit()

    result = await run_purge(async_session, fixed_clock, batch_size=3)

    assert result.occupancy_history_deleted == 7
    assert await count(async_session, OccupancyHistory) == 0


@pytest.mark.asyncio
async def test_retention_comes_from_settings(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    await make_device(async_session, now, age_days=10)
    await make_event(async_session, fs_site, now - timedelta(days=10))

    default = await run_purge(async_session, fixed_clock)
    assert (default.devices_erased, default.events_deleted) == (0, 0)

    short = DeploymentSettings(retention_devices_days=5, retention_events_days=5)
    result = await run_purge(async_session, fixed_clock, settings=short)
    assert (result.devices_erased, result.events_deleted) == (1, 1)


@pytest.mark.asyncio
async def test_retention_read_from_system_config(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    async_session.add(SystemConfig(key="freespace.retention.devices_days", value=7))
    await async_session.commit()
    await invalidate_deployment_settings_cache()
    await make_device(async_session, now, age_days=10)

    result = await run_purge(async_session, fixed_clock)

    assert result.devices_erased == 1


async def _add_log(session, created):
    session.add(
        RequestLog(
            method="GET",
            path="/v1/sites/{slug}",
            status_code=200,
            duration_ms=5,
            created_time=created,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_request_log_retention_honours_system_config(async_session, fixed_clock):
    now = fixed_clock.now()
    await _add_log(async_session, now - timedelta(days=10))
    await _add_log(async_session, now - timedelta(days=2))

    # default 30 days: nothing to delete
    assert (await run_purge(async_session, fixed_clock)).request_logs_deleted == 0

    async_session.add(SystemConfig(key="request_logs.retention_days", value=7))
    await async_session.commit()
    await invalidate_deployment_settings_cache()

    out = await cleanup_old_request_logs_configured_handler(async_session, {})
    assert out == {"status": "completed", "deleted_count": 1}
    assert await count(async_session, RequestLog) == 1


@pytest.mark.asyncio
async def test_cron_handler_reports_counts(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    await make_device(async_session, now, age_days=100)
    out = await freespace_daily_purge_handler(async_session, {"batch_size": 10})
    assert out["status"] == "completed"
    assert out["devices_erased"] == 1
    assert out["errors"] == []


@pytest.mark.asyncio
async def test_one_failing_class_does_not_stop_others(
    async_session, fs_site, fixed_clock, monkeypatch
):
    from src.services.freespace import purge

    async def boom(*args, **kwargs):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(purge, "purge_send_history", boom)
    now = fixed_clock.now()
    await make_device(async_session, now, age_days=100)
    result = await run_purge(async_session, fixed_clock)
    assert result.errors == ["send_history"]
    assert result.devices_erased == 1


@pytest.mark.asyncio
async def test_purge_is_tenant_agnostic_across_sites(
    async_session, fs_site, fs_second_site, fixed_clock
):
    """Retention applies to every tenant's data; none is skipped or spared."""
    now = fixed_clock.now()
    old = now - timedelta(days=400)
    await make_event(async_session, fs_site, old)
    await make_event(async_session, fs_second_site, old)
    result = await run_purge(async_session, fixed_clock)
    assert result.events_deleted == 2
