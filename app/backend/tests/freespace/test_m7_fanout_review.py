"""M7 review fixes (SQLite): Retry-After honoured when a chunk is full
(BF-66), rows left PENDING by a crash finish as UNKNOWN_AFTER_CRASH and still
count for the limits (BF-52, BF-62), TTL from the decision instant with the
real send time in ``sentAt`` (BF-65)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.constants.freespace import DeviceOutcome, FanoutStatus
from src.crud.freespace_push_send import UNKNOWN_AFTER_CRASH
from src.services.freespace import fanout as fanout_module
from src.services.freespace.fanout import ERROR_EXPIRED, run_fanout
from src.services.freespace.fcm import FcmResultKind, FcmSendResult, iso_z
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


class Crash(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    return install_engine_recorder(monkeypatch)


def _record_send_times(fake_fcm, clock):
    times: list[tuple[str | None, object]] = []
    real = fake_fcm.send

    async def send(message):
        times.append((message.token, clock.now()))
        return await real(message)

    fake_fcm.send = send  # type: ignore[method-assign]
    return times


async def test_full_chunk_retryable_honours_retry_after(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """Review R2: a 429 in a FULL chunk used to be re-claimed by the next
    chunk at once, ignoring Retry-After (BF-66)."""
    devices = sorted(
        await make_devices(async_session, [fs_site], 4, now=fixed_clock.now()),
        key=lambda d: d.id,
    )
    slow = devices[0].fcm_token
    fake_fcm.results_by_token[slow] = [
        FcmSendResult(
            kind=FcmResultKind.RETRYABLE,
            retry_after_s=120,
            http_status=429,
            error_code="QUOTA_EXCEEDED",
        ),
        FcmSendResult(kind=FcmResultKind.ACCEPTED, message_id="m"),
    ]
    times = _record_send_times(fake_fcm, fixed_clock)
    t0 = fixed_clock.now()
    event = await make_advisory_event(async_session, fs_site, now=t0)
    factory = session_factory_for(async_session)

    first = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
    )
    assert first.reenqueue_in_s == 0  # more devices: next chunk now
    second = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
    )
    assert [token for token, _ in times].count(slow) == 1  # not re-sent yet
    assert second.reenqueue_in_s == 0

    # The remaining runs (no new devices) wait for the backoff.
    await drive_fanout(factory, event.id, fixed_clock, fake_fcm, chunk_size=2)
    slow_sends = [at for token, at in times if token == slow]
    assert len(slow_sends) == 2
    assert slow_sends[1] - slow_sends[0] >= timedelta(seconds=120)
    row = await reload_event(async_session, event.id)
    assert row.fanout_status == FanoutStatus.COMPLETED.value
    assert row.counts == {"SENT": 4}


async def test_retry_wake_is_scheduled_by_the_last_chunk(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """The run that ends a chunked fan-out with retry rows waiting (and no
    sends of its own) must defer a wake-up to ``retryAt``, not exit."""
    devices = sorted(
        await make_devices(async_session, [fs_site], 2, now=fixed_clock.now()),
        key=lambda d: d.id,
    )
    fake_fcm.results_by_token[devices[0].fcm_token] = [
        FcmSendResult(kind=FcmResultKind.RETRYABLE, retry_after_s=30, http_status=503),
        FcmSendResult(kind=FcmResultKind.ACCEPTED, message_id="m"),
    ]
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)
    full = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
    )
    assert full.reenqueue_in_s == 0
    last = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
    )
    assert last.reenqueue_in_s is not None and last.reenqueue_in_s >= 30
    # A duplicate job now exits without re-enqueueing (the wake is scheduled).
    duplicate = await run_fanout(
        factory, event.id, clock=fixed_clock, fcm=fake_fcm, chunk_size=2
    )
    assert duplicate.reenqueue_in_s is None
    fixed_clock.advance(last.reenqueue_in_s)
    await drive_fanout(factory, event.id, fixed_clock, fake_fcm, chunk_size=2)
    assert (await reload_event(async_session, event.id)).counts == {"SENT": 2}


async def test_crashed_pending_rows_finish_as_unknown_and_still_count(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    """BF-62: no PENDING bucket in the counts; BF-52: such a row is never
    re-sent and still protects the phone (COOLDOWN for the next advisory)."""
    use_deployment_settings(monkeypatch, cooldown_s=1800, daily_cap=5)
    (device,) = await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    factory = session_factory_for(async_session)
    real_send = fanout_module._send_claimed

    async def die(*args, **kwargs):
        raise Crash("killed after the claim commit")

    monkeypatch.setattr(fanout_module, "_send_claimed", die)
    with pytest.raises(Crash):
        await run_fanout(factory, first.id, clock=fixed_clock, fcm=fake_fcm)
    monkeypatch.setattr(fanout_module, "_send_claimed", real_send)
    await drive_fanout(factory, first.id, fixed_clock, fake_fcm)

    row = await reload_event(async_session, first.id)
    assert row.counts == {DeviceOutcome.SEND_FAILED.value: 1}
    (send,) = await send_rows(async_session, first.id)
    assert send.outcome == DeviceOutcome.SEND_FAILED.value
    assert send.error_code == UNKNOWN_AFTER_CRASH
    assert fake_fcm.sent == []

    fixed_clock.advance(60)
    second = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, second.id, fixed_clock, fake_fcm)
    assert (await reload_event(async_session, second.id)).counts == {
        DeviceOutcome.COOLDOWN.value: 1
    }
    assert fake_fcm.sent == []
    assert device.id == send.device_id


async def test_ttl_from_decision_and_sent_at_is_send_time(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    """BF-65: TTL / apns-expiration measured from the decision instant;
    ``sentAt`` is the actual send time (after the claim)."""
    await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    decided = fixed_clock.now()
    event = await make_advisory_event(async_session, fs_site, now=decided)
    fixed_clock.advance(600)
    real_checks = fanout_module.evaluate_device_checks

    async def slow_claim(*args, **kwargs):
        out = await real_checks(*args, **kwargs)
        fixed_clock.advance(5)  # the claim took 5 s
        return out

    monkeypatch.setattr(fanout_module, "evaluate_device_checks", slow_claim)
    await run_fanout(
        session_factory_for(async_session), event.id, clock=fixed_clock, fcm=fake_fcm
    )
    (message,) = fake_fcm.sent
    expiry = decided + timedelta(seconds=fs_site.push_expiry_s)
    assert message.payload["data"]["sentAt"] == iso_z(decided + timedelta(seconds=605))
    assert message.payload["android"]["ttl"] == f"{fs_site.push_expiry_s - 605}s"
    assert message.payload["apns"]["headers"]["apns-expiration"] == str(
        int(expiry.timestamp())
    )


async def test_expired_between_claim_and_send_is_not_sent(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    """Never a send with TTL <= 0: expired at send time -> SEND_FAILED /
    EXPIRED without calling FCM."""
    await make_devices(async_session, [fs_site], 2, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    fixed_clock.advance(fs_site.push_expiry_s - 3)  # not expired at the claim
    real_checks = fanout_module.evaluate_device_checks

    async def slow_claim(*args, **kwargs):
        out = await real_checks(*args, **kwargs)
        fixed_clock.advance(3)
        return out

    monkeypatch.setattr(fanout_module, "evaluate_device_checks", slow_claim)
    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    assert fake_fcm.sent == []
    rows = await send_rows(async_session, event.id)
    assert {(r.outcome, r.error_code) for r in rows} == {
        (DeviceOutcome.SEND_FAILED.value, ERROR_EXPIRED)
    }


async def test_fcm_concurrency_is_bounded_to_max_in_flight(
    async_session, fs_site, fixed_clock, fake_fcm
):
    """BF-64: sends run concurrently, but never more than FCM_MAX_IN_FLIGHT
    (default 20) at once."""
    import asyncio

    from src.constants.freespace import FCM_MAX_IN_FLIGHT

    await make_devices(async_session, [fs_site], 60, now=fixed_clock.now())
    in_flight = 0
    peak = 0
    real = fake_fcm.send

    async def slow_send(message):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return await real(message)

    fake_fcm.send = slow_send  # type: ignore[method-assign]
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, fake_fcm
    )
    assert FCM_MAX_IN_FLIGHT == 20
    assert peak == FCM_MAX_IN_FLIGHT
    assert len(fake_fcm.sent) == 60
