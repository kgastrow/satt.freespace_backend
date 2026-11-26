"""M7 fan-out: BF-52, BF-58 - BF-63, BF-66, BF-67, AT-05, BT-06 - BT-08, BN-3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import uuid

import pytest
from sqlalchemy import select

from src.constants.freespace import (
    FANOUT_STUCK_AFTER_S,
    AdvisoryType,
    DeviceOutcome,
    EventType,
    FanoutStatus,
    FcmErrorReason,
    LimitScope,
    SuppressionReason,
)
from src.models.device import Device, DeviceSite
from src.models.push_send import PushSend
from src.models.site_event import SiteEvent
from src.services.freespace import fanout as fanout_module
from src.services.freespace.clock import ensure_utc
from src.services.freespace.fanout import (
    REDIS_FCM_AUTH_FAILURE_KEY,
    recover_stuck_fanouts,
    register_fcm_auth_failure_hook,
    run_fanout,
    unregister_fcm_auth_failure_hook,
)
from src.services.freespace.fcm import FcmResultKind, FcmSendResult
from tests.freespace.conftest import make_site
from tests.freespace.test_m7_support import (
    drive_fanout,
    install_engine_recorder,
    make_advisory_event,
    make_devices,
    reload_event,
    send_rows,
    session_factory_for,
    use_deployment_settings,
)


pytestmark = pytest.mark.usefixtures("engine_calls")


@pytest.fixture
def engine_calls(monkeypatch):
    """``engine.on_fanout_completed`` (M6) replaced by a recorder."""
    return install_engine_recorder(monkeypatch)


def outcomes_by_device(rows: list[PushSend]) -> dict[uuid.UUID, str]:
    return {row.device_id: row.outcome for row in rows}


async def add_history(
    session,
    site,
    devices,
    *,
    at: datetime,
    advisory_type: AdvisoryType = AdvisoryType.SITE_INITIAL,
    fingerprint: str | None = None,
    cycle_id: uuid.UUID | None = None,
    outcome: DeviceOutcome = DeviceOutcome.SENT,
) -> SiteEvent:
    """A finished advisory of ``site`` that ``devices`` received at ``at``."""
    event = await make_advisory_event(
        session,
        site,
        now=at,
        advisory_type=advisory_type,
        fingerprint=fingerprint,
        cycle_id=cycle_id,
    )
    event.fanout_status = FanoutStatus.COMPLETED.value
    for device in devices:
        session.add(
            PushSend(
                organization_id=site.organization_id,
                event_id=event.id,
                device_id=device.id,
                site_id=site.id,
                advisory_type=advisory_type.value,
                fingerprint=event.fingerprint,
                outcome=outcome.value,
                queued_at=at,
                sent_at=at if outcome == DeviceOutcome.SENT else None,
            )
        )
    await session.commit()
    return event


# ─────────────────────────────────────────────────────────────
# Basic fan-out, payload, bookkeeping (BF-62, BF-65)
# ─────────────────────────────────────────────────────────────


async def test_fanout_sends_once_per_device_and_writes_counts(
    async_session, fs_site, fixed_clock, fake_fcm, engine_calls
):
    devices = await make_devices(async_session, [fs_site], 3, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)

    results = await drive_fanout(factory, event.id, fixed_clock, fake_fcm)

    assert results[-1].status == FanoutStatus.COMPLETED
    assert sorted(fake_fcm.sent_tokens) == sorted(d.fcm_token for d in devices)
    row = await reload_event(async_session, event.id)
    assert row.fanout_status == FanoutStatus.COMPLETED.value
    assert row.counts == {DeviceOutcome.SENT.value: 3}
    assert ensure_utc(row.fanout_started_at) == fixed_clock.now()
    assert ensure_utc(row.fanout_finished_at) == fixed_clock.now()
    assert row.fcm_latency_ms == 0
    # Message content (BF-65) and engine hand-off (BF-54)
    message = fake_fcm.sent[0]
    assert message.payload["data"]["eventId"] == str(event.id)
    assert message.payload["data"]["occupancyPct"] == "90"
    assert message.payload["android"]["ttl"] == "1800s"
    assert "apns" in message.payload
    assert len(engine_calls.calls) == 1
    call = engine_calls.calls[0]
    assert call["sent_count"] == 3
    assert call["top_zones"] == ("b4", "b3")
    assert call["occupancy_exact"] == pytest.approx(90.25)
    assert call["cycle_id"] == event.cycle_id
    # Re-running a finished fan-out is a no-op
    again = await run_fanout(factory, event.id, clock=fixed_clock, fcm=fake_fcm)
    assert again.status == FanoutStatus.COMPLETED and again.reenqueue_in_s is None
    assert len(fake_fcm.sent) == 3


async def test_non_advisory_event_returns_immediately(
    async_session, fs_site, fixed_clock, fake_fcm
):
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    event.type = EventType.CANDIDATE.value
    event.fanout_status = None
    await async_session.commit()
    result = await run_fanout(
        session_factory_for(async_session), event.id, clock=fixed_clock, fcm=fake_fcm
    )
    assert result.reenqueue_in_s is None
    assert fake_fcm.sent == []


async def test_target_set_excludes_invalid_tombstoned_unselected(
    async_session, fs_site, fs_second_site, fixed_clock, fake_fcm
):
    """BF-58 / BF-67: only devices that selected the site, hold a token and
    have no ``tokenInvalidatedAt``; tombstones never (BT-07)."""
    now = fixed_clock.now()
    good, invalid, tombstone, no_token = await make_devices(
        async_session, [fs_site], 4, now=now
    )
    (other,) = await make_devices(
        async_session, [fs_second_site], 1, now=now, prefix="o"
    )
    invalid.token_invalidated_at = now
    no_token.fcm_token = None
    # BT-07: DELETE /v1/devices erases token and selections immediately
    tombstone.fcm_token = None
    tombstone.device_key_hash = None
    tombstone.deleted_time = now
    await async_session.execute(
        DeviceSite.__table__.delete().where(DeviceSite.device_id == tombstone.id)
    )
    await async_session.commit()
    event = await make_advisory_event(async_session, fs_site, now=now)

    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )

    assert fake_fcm.sent_tokens == [good.fcm_token]
    rows = await send_rows(async_session, event.id)
    assert [r.device_id for r in rows] == [good.id]


async def test_unmanaged_site_sends_nothing(
    async_session, test_organization, fixed_clock, fake_fcm, engine_calls
):
    """BF-61: no push for a site with managed = false."""
    site = await make_site(
        async_session, test_organization, slug="shadow-site", managed=False
    )
    await make_devices(async_session, [site], 2, now=fixed_clock.now())
    event = await make_advisory_event(async_session, site, now=fixed_clock.now())

    results = await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )

    assert fake_fcm.sent == []
    assert results[-1].status == FanoutStatus.COMPLETED
    row = await reload_event(async_session, event.id)
    assert row.reason == SuppressionReason.UNMANAGED.value
    assert row.counts == {}
    assert await send_rows(async_session, event.id) == []
    assert engine_calls.calls[0]["sent_count"] == 0


async def test_test_push_bypasses_checks_and_is_not_counted(
    async_session, test_organization, fixed_clock, fake_fcm
):
    """BF-60: TEST bypasses every check (even unmanaged, opted out, outside
    the window) and does not count towards cooldown / cap."""
    site = await make_site(
        async_session, test_organization, slug="pilot", managed=False
    )
    fixed_clock.advance(4 * 3600)  # 11:45 local: outside Mon-Fri 06-10
    (opted_out,) = await make_devices(
        async_session, [site], 1, now=fixed_clock.now(), notifications_enabled=False
    )
    test_event = await make_advisory_event(
        async_session, site, now=fixed_clock.now(), advisory_type=AdvisoryType.TEST
    )
    factory = session_factory_for(async_session)
    await drive_fanout(factory, test_event.id, fixed_clock, fake_fcm)
    assert fake_fcm.sent_tokens == [opted_out.fcm_token]

    # A real advisory right after is not in COOLDOWN because of the TEST.
    site.managed = True
    site.notification_window = []
    opted_out.notifications_enabled = True
    await async_session.commit()
    advisory = await make_advisory_event(async_session, site, now=fixed_clock.now())
    await drive_fanout(factory, advisory.id, fixed_clock, fake_fcm)
    rows = await send_rows(async_session, advisory.id)
    assert [r.outcome for r in rows] == [DeviceOutcome.SENT.value]


# ─────────────────────────────────────────────────────────────
# Per-phone checks (BF-58) and limit scope (BF-63)
# ─────────────────────────────────────────────────────────────


async def test_reasons_and_their_order(async_session, fs_site, fixed_clock, fake_fcm):
    """Each reason, and the first failing check wins."""
    now = fixed_clock.now()
    opted_out, duplicate, cooldown, capped, fresh = await make_devices(
        async_session, [fs_site], 5, now=now
    )
    opted_out.notifications_enabled = False
    await async_session.commit()
    fingerprint = "f" * 64
    state_cycle = (
        await make_advisory_event(async_session, fs_site, now=now - timedelta(hours=5))
    ).cycle_id
    # opted_out ALSO in cooldown -> still OPTED_OUT (check 1 before 4)
    await add_history(
        async_session,
        fs_site,
        [opted_out],
        at=now - timedelta(minutes=5),
        cycle_id=state_cycle,
    )
    # duplicate: same fingerprint 10 min ago (also in cooldown) -> DUPLICATE
    await add_history(
        async_session,
        fs_site,
        [duplicate],
        at=now - timedelta(minutes=10),
        fingerprint=fingerprint,
        cycle_id=state_cycle,
    )
    # cooldown: other advisory 10 min ago, cap not reached
    await add_history(
        async_session,
        fs_site,
        [cooldown],
        at=now - timedelta(minutes=10),
        cycle_id=state_cycle,
    )
    # capped: two advisories earlier today, last one 40 min ago (out of cooldown)
    for minutes in (100, 40):
        await add_history(
            async_session,
            fs_site,
            [capped],
            at=now - timedelta(minutes=minutes),
            cycle_id=state_cycle,
        )
    event = await make_advisory_event(
        async_session, fs_site, now=now, fingerprint=fingerprint, cycle_id=state_cycle
    )

    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )

    outcomes = outcomes_by_device(await send_rows(async_session, event.id))
    assert outcomes == {
        opted_out.id: DeviceOutcome.OPTED_OUT.value,
        duplicate.id: DeviceOutcome.DUPLICATE.value,
        cooldown.id: DeviceOutcome.COOLDOWN.value,
        capped.id: DeviceOutcome.DAILY_CAP.value,
        fresh.id: DeviceOutcome.SENT.value,
    }
    assert fake_fcm.sent_tokens == [fresh.fcm_token]
    row = await reload_event(async_session, event.id)
    assert row.counts == {
        "OPTED_OUT": 1,
        "DUPLICATE": 1,
        "COOLDOWN": 1,
        "DAILY_CAP": 1,
        "SENT": 1,
    }


async def test_duplicate_is_bounded_to_the_cycle(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """The same wording in a NEW cycle (e.g. tomorrow) is not a DUPLICATE."""
    now = fixed_clock.now()
    (device,) = await make_devices(async_session, [fs_site], 1, now=now)
    fingerprint = "a" * 64
    await add_history(
        async_session,
        fs_site,
        [device],
        at=now - timedelta(hours=3),
        fingerprint=fingerprint,
        cycle_id=uuid.uuid4(),
    )
    event = await make_advisory_event(
        async_session, fs_site, now=now, fingerprint=fingerprint, cycle_id=uuid.uuid4()
    )
    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    assert fake_fcm.sent_tokens == [device.fcm_token]


async def test_outside_window_nobody_sent_and_opted_out_first(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """Window in SITE local time: 10:30 SAST on a Tuesday is outside the
    default Mon-Fri 06:00-10:00; opted-out devices still report OPTED_OUT."""
    fixed_clock.set(datetime(2026, 11, 24, 8, 30, tzinfo=timezone.utc))  # 10:30 SAST
    enabled, opted_out = await make_devices(
        async_session, [fs_site], 2, now=fixed_clock.now()
    )
    opted_out.notifications_enabled = False
    await async_session.commit()
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())

    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )

    assert fake_fcm.sent == []
    assert outcomes_by_device(await send_rows(async_session, event.id)) == {
        enabled.id: DeviceOutcome.OUTSIDE_WINDOW.value,
        opted_out.id: DeviceOutcome.OPTED_OUT.value,
    }


async def test_window_edge_is_site_local(
    async_session, test_organization, fixed_clock, fake_fcm
):
    """09:59 local inside, the same UTC instant is 07:59 UTC - a site in UTC
    with a 08:00-10:00 window would be outside."""
    fixed_clock.set(datetime(2026, 11, 24, 7, 59, tzinfo=timezone.utc))
    utc_site = await make_site(
        async_session,
        test_organization,
        slug="utc-site",
        time_zone="UTC",
        notification_window=[{"weekdays": [2], "start": "08:00", "end": "10:00"}],
    )
    sast_site = await make_site(
        async_session,
        test_organization,
        slug="sast-site",
        notification_window=[{"weekdays": [2], "start": "08:00", "end": "10:00"}],
    )
    (a,) = await make_devices(
        async_session, [utc_site], 1, now=fixed_clock.now(), prefix="u"
    )
    (b,) = await make_devices(
        async_session, [sast_site], 1, now=fixed_clock.now(), prefix="s"
    )
    factory = session_factory_for(async_session)
    for site in (utc_site, sast_site):
        event = await make_advisory_event(async_session, site, now=fixed_clock.now())
        await drive_fanout(factory, event.id, fixed_clock, fake_fcm)
    assert fake_fcm.sent_tokens == [b.fcm_token]


async def test_at05_per_phone_part(
    async_session, fs_site, fs_second_site, fixed_clock, fake_fcm
):
    """AT-05: ACTIVE, notified at 90 % at 07:45; 08:20 at 95 % with a new
    recommendation: sent to devices out of cooldown and under the cap; the
    rest COOLDOWN / DAILY_CAP."""
    start = fixed_clock.now()  # 07:45 SAST
    eligible, cooled, capped = await make_devices(
        async_session, [fs_site], 3, now=start
    )
    factory = session_factory_for(async_session)

    initial = await make_advisory_event(async_session, fs_site, now=start)
    await drive_fanout(factory, initial.id, fixed_clock, fake_fcm)
    assert len(fake_fcm.sent) == 3

    # cooled got another site's advisory at 08:05 (DEVICE scope counts it)
    await add_history(
        async_session, fs_second_site, [cooled], at=start + timedelta(minutes=20)
    )
    # capped already had a second advisory at 06:30 today
    await add_history(
        async_session, fs_second_site, [capped], at=start - timedelta(minutes=75)
    )

    fixed_clock.set(start + timedelta(minutes=35))  # 08:20
    fake_fcm.reset()
    change = await make_advisory_event(
        async_session,
        fs_site,
        now=fixed_clock.now(),
        advisory_type=AdvisoryType.SITE_CHANGE,
        recommended_zone_slug="b3",
        occupancy_pct=95,
    )
    await drive_fanout(factory, change.id, fixed_clock, fake_fcm)

    assert fake_fcm.sent_tokens == [eligible.fcm_token]
    assert outcomes_by_device(await send_rows(async_session, change.id)) == {
        eligible.id: DeviceOutcome.SENT.value,
        cooled.id: DeviceOutcome.COOLDOWN.value,
        capped.id: DeviceOutcome.DAILY_CAP.value,
    }
    assert fake_fcm.sent[0].payload["data"]["type"] == "SITE_CHANGE"
    assert fake_fcm.sent[0].payload["data"]["recommendedZoneId"] == "b3"


async def test_bt08_device_scope_two_sites_one_push(
    async_session, fs_site, fs_second_site, fixed_clock, fake_fcm
):
    """BT-08: limitScope DEVICE, a phone follows two sites that both go
    ACTIVE within 30 min: one push, the second is COOLDOWN."""
    (phone,) = await make_devices(
        async_session, [fs_site, fs_second_site], 1, now=fixed_clock.now()
    )
    factory = session_factory_for(async_session)
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, first.id, fixed_clock, fake_fcm)
    fixed_clock.advance(20 * 60)
    second = await make_advisory_event(
        async_session, fs_second_site, now=fixed_clock.now()
    )
    await drive_fanout(factory, second.id, fixed_clock, fake_fcm)

    assert fake_fcm.sent_tokens == [phone.fcm_token]
    rows = await send_rows(async_session, second.id)
    assert [r.outcome for r in rows] == [DeviceOutcome.COOLDOWN.value]


async def test_device_per_site_scope(
    async_session, fs_site, fs_second_site, fixed_clock, fake_fcm, monkeypatch
):
    """BF-63 DEVICE_PER_SITE: counted per (device, site) with the site's own
    cooldown; another site's push does not block."""
    use_deployment_settings(monkeypatch, limit_scope=LimitScope.DEVICE_PER_SITE)
    fs_site.cooldown_s = 600
    await async_session.commit()
    (phone,) = await make_devices(
        async_session, [fs_site, fs_second_site], 1, now=fixed_clock.now()
    )
    factory = session_factory_for(async_session)

    a1 = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, a1.id, fixed_clock, fake_fcm)
    fixed_clock.advance(5 * 60)
    b1 = await make_advisory_event(async_session, fs_second_site, now=fixed_clock.now())
    await drive_fanout(factory, b1.id, fixed_clock, fake_fcm)
    a2 = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, a2.id, fixed_clock, fake_fcm)
    fixed_clock.advance(6 * 60)  # 11 min after a1 > site cooldown 600 s
    a3 = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, a3.id, fixed_clock, fake_fcm)

    assert [r.outcome for r in await send_rows(async_session, b1.id)] == ["SENT"]
    assert [r.outcome for r in await send_rows(async_session, a2.id)] == ["COOLDOWN"]
    # a3: cooldown over, but site cap 2 already used (a1 + nothing else) -> SENT
    assert [r.outcome for r in await send_rows(async_session, a3.id)] == ["SENT"]
    assert len(fake_fcm.sent) == 3


async def test_recovery_counts_towards_limits(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """BF-60 / Q1: RECOVERY counts towards cooldown."""
    (phone,) = await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    await add_history(
        async_session,
        fs_site,
        [phone],
        at=fixed_clock.now() - timedelta(minutes=10),
        advisory_type=AdvisoryType.RECOVERY,
    )
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    assert [r.outcome for r in await send_rows(async_session, event.id)] == ["COOLDOWN"]


@pytest.mark.parametrize(
    ("deployment_tz", "expected"),
    [("Africa/Johannesburg", "SENT"), ("UTC", "DAILY_CAP")],
)
async def test_daily_cap_day_boundary_in_time_zone(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch, deployment_tz, expected
):
    """ "Today" is midnight to midnight in the deployment time zone (DEVICE
    scope). Two pushes on Mon 20:00 and 21:00 SAST; at 23:00 SAST -> cap;
    at Tue 00:05 SAST (= Mon 22:05 UTC) a new SAST day but the same UTC day."""
    use_deployment_settings(monkeypatch, time_zone=deployment_tz)
    fs_site.notification_window = []
    await async_session.commit()
    monday_20 = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)  # 20:00 SAST
    (phone,) = await make_devices(async_session, [fs_site], 1, now=monday_20)
    for hours in (0, 1):
        await add_history(
            async_session, fs_site, [phone], at=monday_20 + timedelta(hours=hours)
        )
    factory = session_factory_for(async_session)

    fixed_clock.set(monday_20 + timedelta(hours=3))  # 23:00 SAST
    late = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, late.id, fixed_clock, fake_fcm)
    assert [r.outcome for r in await send_rows(async_session, late.id)] == ["DAILY_CAP"]

    fixed_clock.set(monday_20 + timedelta(hours=4, minutes=5))  # Tue 00:05 SAST
    after_midnight = await make_advisory_event(
        async_session, fs_site, now=fixed_clock.now()
    )
    await drive_fanout(factory, after_midnight.id, fixed_clock, fake_fcm)
    assert [r.outcome for r in await send_rows(async_session, after_midnight.id)] == [
        expected
    ]


# ─────────────────────────────────────────────────────────────
# FCM errors (BF-66, BF-67, BT-06)
# ─────────────────────────────────────────────────────────────


async def test_bt06_unregistered_token_invalidated_and_skipped_next_time(
    async_session, fs_site, fixed_clock, fake_fcm
):
    dead, alive1, alive2 = await make_devices(
        async_session, [fs_site], 3, now=fixed_clock.now()
    )
    fake_fcm.results_by_token[dead.fcm_token] = FcmSendResult(
        kind=FcmResultKind.TOKEN_INVALID, error_code="UNREGISTERED", http_status=404
    )
    factory = session_factory_for(async_session)
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, first.id, fixed_clock, fake_fcm)

    rows = {r.device_id: r for r in await send_rows(async_session, first.id)}
    assert rows[dead.id].outcome == DeviceOutcome.TOKEN_INVALID.value
    assert rows[dead.id].error_code == "UNREGISTERED"
    assert rows[alive1.id].outcome == rows[alive2.id].outcome == "SENT"
    await async_session.refresh(dead)
    assert ensure_utc(dead.token_invalidated_at) == fixed_clock.now()

    fake_fcm.reset()
    fixed_clock.advance(3600)
    second = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, second.id, fixed_clock, fake_fcm)
    assert sorted(fake_fcm.sent_tokens) == sorted([alive1.fcm_token, alive2.fcm_token])
    assert dead.id not in {
        r.device_id for r in await send_rows(async_session, second.id)
    }


async def test_retry_honours_retry_after_then_succeeds(
    async_session, fs_site, fixed_clock, fake_fcm
):
    flaky, ok = await make_devices(async_session, [fs_site], 2, now=fixed_clock.now())
    fake_fcm.results_by_token[flaky.fcm_token] = [
        FcmSendResult(
            kind=FcmResultKind.RETRYABLE,
            retry_after_s=42,
            http_status=429,
            error_code="QUOTA_EXCEEDED",
        ),
        FcmSendResult(kind=FcmResultKind.ACCEPTED, message_id="m", http_status=200),
    ]
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    results = await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    assert results[0].reenqueue_in_s is not None and results[0].reenqueue_in_s >= 42
    assert fake_fcm.sent_tokens.count(flaky.fcm_token) == 2  # FCM refused the first
    assert fake_fcm.sent_tokens.count(ok.fcm_token) == 1
    row = await reload_event(async_session, event.id)
    assert row.counts == {"SENT": 2}


async def test_retry_window_exhausted_then_send_failed(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """BF-66: retried with backoff until 5 minutes have passed, then
    SEND_FAILED; others unaffected."""
    broken, ok = await make_devices(async_session, [fs_site], 2, now=fixed_clock.now())
    fake_fcm.results_by_token[broken.fcm_token] = FcmSendResult(
        kind=FcmResultKind.RETRYABLE, http_status=503, error_code="UNAVAILABLE"
    )
    start = fixed_clock.now()
    event = await make_advisory_event(async_session, fs_site, now=start)
    results = await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )

    attempts = fake_fcm.sent_tokens.count(broken.fcm_token)
    assert attempts >= 3  # exponential backoff 5, 10, 20, 40, 60 ...
    assert fixed_clock.now() - start <= timedelta(seconds=300)
    assert results[-1].status == FanoutStatus.COMPLETED
    rows = {r.device_id: r for r in await send_rows(async_session, event.id)}
    assert rows[broken.id].outcome == DeviceOutcome.SEND_FAILED.value
    assert rows[ok.id].outcome == DeviceOutcome.SENT.value
    assert fake_fcm.sent_tokens.count(ok.fcm_token) == 1


async def test_expired_advisory_is_never_sent_late(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """BF-59 / push expiry: a fan-out that only starts after the message
    expired sends nothing."""
    await make_devices(async_session, [fs_site], 2, now=fixed_clock.now())
    event = await make_advisory_event(
        async_session, fs_site, now=fixed_clock.now() - timedelta(seconds=1801)
    )
    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    assert fake_fcm.sent == []
    rows = await send_rows(async_session, event.id)
    assert {(r.outcome, r.error_code) for r in rows} == {("SEND_FAILED", "EXPIRED")}


async def test_late_start_shortens_ttl(async_session, fs_site, fixed_clock, fake_fcm):
    await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    event = await make_advisory_event(
        async_session, fs_site, now=fixed_clock.now() - timedelta(seconds=600)
    )
    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    payload = fake_fcm.sent[0].payload
    assert payload["android"]["ttl"] == "1200s"
    expected = int(
        (ensure_utc(event.occurred_at) + timedelta(seconds=1800)).timestamp()
    )
    assert payload["apns"]["headers"]["apns-expiration"] == str(expected)


async def test_auth_failure_stops_fanout_and_alerts(
    async_session, fs_site, fixed_clock, fake_fcm, fs_redis, engine_calls
):
    devices = await make_devices(async_session, [fs_site], 6, now=fixed_clock.now())
    fake_fcm.default_result = FcmSendResult(
        kind=FcmResultKind.AUTH_FAILURE, http_status=401, error_code="UNAUTHENTICATED"
    )
    seen = []

    async def hook(failure):
        seen.append(failure)

    register_fcm_auth_failure_hook(hook)
    try:
        event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
        results = await drive_fanout(
            session_factory_for(async_session),
            event.id,
            fixed_clock,
            fake_fcm,
            chunk_size=2,
        )
    finally:
        unregister_fcm_auth_failure_hook(hook)

    assert len(results) == 1 and results[0].status == FanoutStatus.FAILED
    assert len(fake_fcm.sent) == 2  # first chunk only; the rest never tried
    row = await reload_event(async_session, event.id)
    assert row.fanout_status == FanoutStatus.FAILED.value
    assert row.counts == {"SEND_FAILED": 2}
    errors = (
        (
            await async_session.execute(
                select(SiteEvent).where(
                    SiteEvent.site_id == fs_site.id,
                    SiteEvent.type == EventType.FCM_ERROR.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(errors) == 1 and errors[0].reason == FcmErrorReason.AUTH_FAILURE.value
    assert errors[0].details["eventId"] == str(event.id)
    assert await fs_redis.get(REDIS_FCM_AUTH_FAILURE_KEY) is not None
    assert len(seen) == 1 and seen[0].event_id == event.id
    assert engine_calls.calls[0]["sent_count"] == 0
    # No device id or token anywhere in the error event (BF-35)
    text = str(errors[0].details)
    assert all(d.fcm_token not in text and str(d.id) not in text for d in devices)


# ─────────────────────────────────────────────────────────────
# At-most-once across crashes (BF-52, BT-02 SQLite variant)
# ─────────────────────────────────────────────────────────────


class Crash(RuntimeError):
    pass


async def test_crash_between_commit_and_send_never_resends(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    devices = await make_devices(async_session, [fs_site], 5, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)

    # Chunk 1 (2 devices) goes through.
    first = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
    )
    assert first.reenqueue_in_s == 0
    # Chunk 2: the worker dies after the rows are committed, before FCM.
    real_send = fanout_module._send_claimed

    async def die(*args, **kwargs):
        raise Crash("killed")

    monkeypatch.setattr(fanout_module, "_send_claimed", die)
    with pytest.raises(Crash):
        await run_fanout(
            factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
        )
    monkeypatch.setattr(fanout_module, "_send_claimed", real_send)

    # Restart: resumes with the devices not yet recorded.
    await drive_fanout(factory, event.id, fixed_clock, fake_fcm, chunk_size=2)

    sent = fake_fcm.sent_tokens
    assert len(sent) == len(set(sent)) == 3  # 2 lost to the crash, none twice
    rows = await send_rows(async_session, event.id)
    assert len(rows) == 5
    row = await reload_event(async_session, event.id)
    assert row.fanout_status == FanoutStatus.COMPLETED.value
    assert row.counts == {"SENT": 3, "SEND_FAILED": 2}  # BF-62: no PENDING bucket
    crashed = [r for r in rows if r.outcome == "SEND_FAILED"]
    assert {r.error_code for r in crashed} == {"UNKNOWN_AFTER_CRASH"}
    assert {d.fcm_token for d in devices} >= set(sent)


async def test_crash_between_send_and_outcome_update_never_resends(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    await make_devices(async_session, [fs_site], 4, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)
    real_record = fanout_module._record_outcomes

    async def die(*args, **kwargs):
        raise Crash("killed after FCM accepted")

    monkeypatch.setattr(fanout_module, "_record_outcomes", die)
    with pytest.raises(Crash):
        await run_fanout(
            factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
        )
    assert len(fake_fcm.sent) == 2
    monkeypatch.setattr(fanout_module, "_record_outcomes", real_record)

    await drive_fanout(factory, event.id, fixed_clock, fake_fcm, chunk_size=2)
    sent = fake_fcm.sent_tokens
    assert len(sent) == len(set(sent)) == 4
    row = await reload_event(async_session, event.id)
    assert row.counts == {"SENT": 2, "SEND_FAILED": 2}


async def test_lease_blocks_a_concurrent_duplicate_job(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    """A duplicate job arriving while a run holds the lease exits at once;
    after the lease lapses (crashed holder) the work resumes."""
    await make_devices(async_session, [fs_site], 3, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)
    real_release = fanout_module._release_lease
    real_send = fanout_module._send_claimed

    async def die(*args, **kwargs):
        raise Crash("hard kill")

    async def no_release(*args, **kwargs):  # SIGKILL: no cleanup either
        return None

    monkeypatch.setattr(fanout_module, "_send_claimed", die)
    monkeypatch.setattr(fanout_module, "_release_lease", no_release)
    with pytest.raises(Crash):
        await run_fanout(
            factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=1
        )
    monkeypatch.setattr(fanout_module, "_send_claimed", real_send)
    monkeypatch.setattr(fanout_module, "_release_lease", real_release)

    duplicate = await run_fanout(factory, event.id, clock=fixed_clock, fcm=fake_fcm)
    assert duplicate.status == FanoutStatus.RUNNING and duplicate.reenqueue_in_s is None
    assert fake_fcm.sent == []
    assert await recover_stuck_fanouts(async_session, fixed_clock.now()) == []

    fixed_clock.advance(max(fanout_module.LEASE_S, FANOUT_STUCK_AFTER_S) + 1)
    assert await recover_stuck_fanouts(async_session, fixed_clock.now()) == [event.id]
    await drive_fanout(factory, event.id, fixed_clock, fake_fcm)
    # The message has 1800 s expiry, so the 2 unclaimed devices still get it.
    assert len(fake_fcm.sent_tokens) == len(set(fake_fcm.sent_tokens)) == 2


async def test_recover_stuck_fanouts_selection(async_session, fs_site, fixed_clock):
    now = fixed_clock.now()
    old_pending = await make_advisory_event(
        async_session, fs_site, now=now - timedelta(seconds=400)
    )
    fresh_pending = await make_advisory_event(
        async_session, fs_site, now=now - timedelta(seconds=30)
    )
    old_running = await make_advisory_event(
        async_session, fs_site, now=now - timedelta(seconds=900)
    )
    old_running.fanout_status = FanoutStatus.RUNNING.value
    old_running.fanout_started_at = now - timedelta(seconds=800)
    done = await make_advisory_event(
        async_session, fs_site, now=now - timedelta(seconds=900)
    )
    done.fanout_status = FanoutStatus.COMPLETED.value
    await async_session.commit()

    stuck = await recover_stuck_fanouts(async_session, now)

    assert set(stuck) == {old_pending.id, old_running.id}
    assert fresh_pending.id not in stuck and done.id not in stuck


# ─────────────────────────────────────────────────────────────
# BN-3: 5 000 devices well within 2 minutes
# ─────────────────────────────────────────────────────────────


async def test_throughput_5000_devices(async_session, fs_site, fixed_clock, fake_fcm):
    await make_devices(async_session, [fs_site], 5000, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)

    started = time.perf_counter()
    results = await drive_fanout(factory, event.id, fixed_clock, fake_fcm)
    elapsed = time.perf_counter() - started

    assert len(fake_fcm.sent_tokens) == len(set(fake_fcm.sent_tokens)) == 5000
    assert len(results) == 11  # 10 full chunks + the closing call
    assert elapsed < 60, f"fan-out of 5000 took {elapsed:.1f}s"
    row = await reload_event(async_session, event.id)
    assert row.counts == {"SENT": 5000}


async def test_devices_without_rows_only_get_one_row_each(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """Unique (event_id, device_id) holds across chunks."""
    await make_devices(async_session, [fs_site], 7, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(
        session_factory_for(async_session),
        event.id,
        fixed_clock,
        fake_fcm,
        chunk_size=3,
    )
    rows = await send_rows(async_session, event.id)
    assert len(rows) == len({r.device_id for r in rows}) == 7
    devices = (await async_session.execute(select(Device))).scalars().all()
    assert len(devices) == 7
