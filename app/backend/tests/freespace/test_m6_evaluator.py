"""
M6 DB shell: ``evaluate_site`` persistence, restart safety (BN-4), settings
change without restart (BF-72), event collapse (D11), ``run_engine_tick``
(BF-50, failure isolation, recovery, Redis tick key) and the end-to-end
evaluate_site -> run_fanout -> on_fanout_completed path for AT-03 / AT-05.
"""

from __future__ import annotations

from typing import Any
import uuid

import pytest
from sqlalchemy import select

from src.constants.freespace import (
    REDIS_ENGINE_TICK_KEY,
    AdvisoryType,
    DeviceOutcome,
    EngineState,
    EventType,
    FanoutStatus,
    StateChangeReason,
    SuppressionReason,
)
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.services.freespace import engine as engine_module
from src.services.freespace import evaluator
from src.services.freespace.evaluator import evaluate_site, run_engine_tick
from tests.freespace.conftest import make_site, make_zone
from tests.freespace.test_m7_support import (
    drive_fanout,
    make_devices,
    reload_event,
    session_factory_for,
)


DEFAULT_OCC = {"b1": 240, "b2": 230, "b3": 200, "b4": 150}  # rec b4, top b4,b3
MOVED_OCC = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}  # rec b2


@pytest.fixture
def post(async_session, fs_snapshot, fixed_clock):
    """Write a snapshot at the current clock and evaluate like intake does."""

    async def _post(site, pct: float, occ: dict[str, int] | None = None):
        zones = {
            slug: {"capacity": 250, "occupied": value}
            for slug, value in (occ or DEFAULT_OCC).items()
        }
        await fs_snapshot(site, capacity=1000, occupied=round(10 * pct), zones=zones)
        view = await evaluate_site(async_session, site.id, fixed_clock)
        await async_session.commit()
        return view

    return _post


async def hold(post, clock, site, pct, seconds, occ=None):
    view = None
    for _ in range(seconds // 30):
        clock.advance(30)
        view = await post(site, pct, occ)
    return view


async def events_of(session, site_id, event_type: EventType | None = None):
    query = select(SiteEvent).where(SiteEvent.site_id == site_id)
    if event_type is not None:
        query = query.where(SiteEvent.type == event_type.value)
    query = query.order_by(SiteEvent.occurred_at).execution_options(
        populate_existing=True
    )
    return list((await session.execute(query)).scalars().all())


async def state_row(session, site_id) -> SiteEngineState:
    return (
        (
            await session.execute(
                select(SiteEngineState)
                .where(SiteEngineState.site_id == site_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .one()
    )


class TestEvaluateSite:
    async def test_unknown_site(self, async_session, fixed_clock):
        with pytest.raises(LookupError):
            await evaluate_site(async_session, uuid.uuid4(), fixed_clock)

    async def test_never_reported_site(self, async_session, fs_site, fixed_clock):
        view = await evaluate_site(async_session, fs_site.id, fixed_clock)
        assert view == evaluator.EvaluatedSiteView(
            state=EngineState.IDLE, recommended_zone_slug=None, stale=True
        )

    async def test_persists_state_and_events(
        self, async_session, fs_site, fs_zones, fixed_clock, post
    ):
        view = await post(fs_site, 90)
        assert view.state is EngineState.PENDING
        assert view.recommended_zone_slug == "b4"
        assert view.stale is False
        row = await state_row(async_session, fs_site.id)
        assert row.state == EngineState.PENDING
        assert row.current_zone_slug == "b4"
        reasons = [e.reason for e in await events_of(async_session, fs_site.id)]
        assert StateChangeReason.TRIGGER_CROSSED in reasons

        view = await hold(post, fixed_clock, fs_site, 90, 300)
        assert view.state is EngineState.ACTIVE
        (advisory,) = await events_of(async_session, fs_site.id, EventType.ADVISORY)
        assert view.fanout_event_ids == (advisory.id,)
        assert advisory.fanout_status == FanoutStatus.PENDING
        assert advisory.advisory_type == AdvisoryType.SITE_INITIAL
        assert advisory.details["topZones"] == ["b4", "b3"]
        assert advisory.details["occupancyExact"] == pytest.approx(90.0)
        assert advisory.details["occupancyPct"] == 90
        assert advisory.figures["site"]["occupancyPct"] == 90
        assert advisory.rendered_title and advisory.rendered_body
        assert len(advisory.fingerprint) == 64
        row = await state_row(async_session, fs_site.id)
        assert row.inflight_event_id == advisory.id
        assert row.cycle_id == advisory.cycle_id is not None

    async def test_restart_safety(
        self, async_session, fs_site, fs_zones, fixed_clock, post
    ):
        """BN-4: state lives in the DB; a fresh session continues the cycle and
        never re-sends."""
        await post(fs_site, 90)
        await hold(post, fixed_clock, fs_site, 90, 270)
        async_session.expunge_all()  # "restart": nothing cached in memory
        fixed_clock.advance(30)
        view = await post(fs_site, 90)
        assert view.state is EngineState.ACTIVE
        assert len(view.fanout_event_ids) == 1
        async_session.expunge_all()
        for _ in range(4):
            fixed_clock.advance(30)
            view = await post(fs_site, 90)
            assert view.fanout_event_ids == ()
        advisories = await events_of(async_session, fs_site.id, EventType.ADVISORY)
        assert len(advisories) == 1

    async def test_repeated_suppression_collapses(
        self, async_session, fs_site, fs_zones, fixed_clock, post
    ):
        await post(fs_site, 90)
        await hold(post, fixed_clock, fs_site, 90, 300)
        # Δ crossed, same recommendation and top zones (BF-57) x5
        await hold(post, fixed_clock, fs_site, 95, 150)
        (candidate,) = await events_of(async_session, fs_site.id, EventType.CANDIDATE)
        assert candidate.reason == SuppressionReason.NO_MATERIAL_CHANGE
        assert candidate.repeat_count == 5

    async def test_settings_change_without_restart(
        self, async_session, fs_site, fs_zones, fixed_clock, post
    ):
        assert (await post(fs_site, 86)).state is EngineState.IDLE
        fs_site.trigger_pct = 85
        fs_site.reset_pct = 75
        await async_session.commit()
        fixed_clock.advance(30)
        assert (await post(fs_site, 86)).state is EngineState.PENDING

    async def test_unmanaged_shadow_mode(
        self, async_session, test_organization, fixed_clock, post
    ):
        site = await make_site(
            async_session, test_organization, slug="shadow-site", managed=False
        )
        for i in range(1, 5):
            await make_zone(async_session, site, f"b{i}", display_order=i)
        await post(site, 90)
        view = await hold(post, fixed_clock, site, 90, 300)
        assert view.state is EngineState.ACTIVE
        assert view.fanout_event_ids == ()
        assert await events_of(async_session, site.id, EventType.ADVISORY) == []
        (candidate,) = await events_of(async_session, site.id, EventType.CANDIDATE)
        assert candidate.reason == SuppressionReason.UNMANAGED
        row = await state_row(async_session, site.id)
        assert row.last_notified_pct == pytest.approx(90.0)


class TestTick:
    async def test_tick_evaluates_all_isolates_failures_and_records(
        self,
        async_session,
        fs_site,
        fs_zones,
        test_organization,
        fixed_clock,
        fs_redis,
        post,
        monkeypatch,
    ):
        shadow = await make_site(
            async_session, test_organization, slug="shadow-site", managed=False
        )
        for i in range(1, 5):
            await make_zone(async_session, shadow, f"b{i}", display_order=i)
        await post(fs_site, 90)
        await post(shadow, 90)

        real_evaluate = engine_module.evaluate

        def flaky(settings, *args, **kwargs):
            if settings.site_id == fs_site.id:
                raise RuntimeError("boom")
            return real_evaluate(settings, *args, **kwargs)

        monkeypatch.setattr(engine_module, "evaluate", flaky)
        stuck_id = uuid.uuid4()

        async def fake_recover(session, now):
            return [stuck_id]

        from src.services.freespace import fanout

        monkeypatch.setattr(fanout, "recover_stuck_fanouts", fake_recover)
        enqueued: list[Any] = []

        async def fake_enqueue(name, *args, **kwargs):
            enqueued.append((name, args))
            return "job"

        from src.services.tasks import task_queue

        monkeypatch.setattr(task_queue, "enqueue_job", fake_enqueue)

        # Shadow-mode timers expire through the tick alone (fresh data kept).
        for _ in range(10):
            fixed_clock.advance(30)
            await _refresh_snapshot(async_session, shadow, fixed_clock)
            result = await run_engine_tick(
                session_factory_for(async_session), fixed_clock
            )
            assert result.sites_evaluated == 1
            assert result.sites_failed == 1
            assert result.fanouts_recovered == 1
            assert any("boom" in e for e in result.errors)

        row = await state_row(async_session, shadow.id)
        assert row.state == EngineState.ACTIVE
        assert ("fanout_advisory_task", (str(stuck_id),)) in enqueued
        stamp = await fs_redis.get(REDIS_ENGINE_TICK_KEY)
        stamp = stamp.decode() if isinstance(stamp, bytes) else stamp
        assert stamp == fixed_clock.now().isoformat()
        assert REDIS_ENGINE_TICK_KEY == "freespace:engine_tick:last"

    async def test_tick_enqueues_new_advisories_after_commit(
        self, async_session, fs_site, fs_zones, fixed_clock, post, monkeypatch
    ):
        await post(fs_site, 90)
        await hold(post, fixed_clock, fs_site, 90, 270)
        fixed_clock.advance(30)
        await _refresh_snapshot(async_session, fs_site, fixed_clock)
        seen: list[Any] = []

        async def fake_enqueue(name, event_id, **kwargs):
            # The event must already be committed (BF-52).
            factory = session_factory_for(async_session)
            async with factory() as other:
                row = await other.get(SiteEvent, uuid.UUID(event_id))
                seen.append(row is not None and row.fanout_status == "PENDING")
            return "job"

        from src.services.tasks import task_queue

        monkeypatch.setattr(task_queue, "enqueue_job", fake_enqueue)
        result = await run_engine_tick(session_factory_for(async_session), fixed_clock)
        assert result.fanouts_enqueued == 1
        assert seen == [True]


async def _refresh_snapshot(session, site, clock) -> None:
    """Re-stamp the site's and zones' latest snapshot as just received."""
    from src.models.site_snapshot import SiteSnapshot, ZoneSnapshot

    for model in (SiteSnapshot, ZoneSnapshot):
        rows = (
            await session.execute(select(model).where(model.site_id == site.id))
        ).scalars()
        for row in rows:
            row.received_at = clock.now()
            row.measured_at = clock.now()
    await session.commit()


class TestEndToEndWithFanout:
    async def test_at03_and_at05_through_fanout(
        self, async_session, fs_site, fs_zones, fixed_clock, fake_fcm, post
    ):
        factory = session_factory_for(async_session)
        await make_devices(
            async_session, [fs_site], 3, now=fixed_clock.now(), prefix="old"
        )

        # AT-03: 90 % held 5 min -> SITE_INITIAL sent to eligible devices.
        await post(fs_site, 90)
        view = await hold(post, fixed_clock, fs_site, 90, 300)
        (initial_id,) = view.fanout_event_ids
        await drive_fanout(factory, initial_id, fixed_clock, fake_fcm)
        initial = await reload_event(async_session, initial_id)
        assert initial.fanout_status == FanoutStatus.COMPLETED
        assert initial.counts.get(DeviceOutcome.SENT) == 3
        row = await state_row(async_session, fs_site.id)
        assert row.state == EngineState.ACTIVE
        assert row.last_notified_pct == pytest.approx(90.0)
        assert row.last_notified_zone_slug == "b4"
        assert row.last_sent_fingerprint == initial.fingerprint
        assert row.inflight_event_id is None

        # AT-04: 92 % -> nothing.
        fixed_clock.advance(30)
        assert (await post(fs_site, 92)).fanout_event_ids == ()

        # AT-05a: 95 %, same recommendation and top-two -> NO_MATERIAL_CHANGE.
        fixed_clock.advance(30)
        assert (await post(fs_site, 95)).fanout_event_ids == ()
        (dropped,) = await events_of(async_session, fs_site.id, EventType.CANDIDATE)
        assert dropped.reason == SuppressionReason.NO_MATERIAL_CHANGE

        # AT-05b: new recommendation -> sent to devices out of cooldown; the
        # three that just got SITE_INITIAL are in cooldown.
        await make_devices(
            async_session, [fs_site], 2, now=fixed_clock.now(), prefix="new"
        )
        fixed_clock.advance(30)
        view = await post(fs_site, 95, MOVED_OCC)
        (change_id,) = view.fanout_event_ids
        await drive_fanout(factory, change_id, fixed_clock, fake_fcm)
        change = await reload_event(async_session, change_id)
        assert change.advisory_type == AdvisoryType.SITE_CHANGE
        assert change.recommended_zone_slug == "b2"
        assert change.counts.get(DeviceOutcome.SENT) == 2
        assert change.counts.get(DeviceOutcome.COOLDOWN) == 3
        row = await state_row(async_session, fs_site.id)
        assert row.last_notified_pct == pytest.approx(95.0)
        assert row.last_notified_zone_slug == "b2"
        assert row.last_sent_fingerprint == change.fingerprint

        # Same situation again: dropped, never re-sent.
        fixed_clock.advance(30)
        assert (await post(fs_site, 95, MOVED_OCC)).fanout_event_ids == ()
