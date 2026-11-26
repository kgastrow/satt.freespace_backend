"""Foundation: models, loaders (rows -> core types), site bootstrap, BF-72 reset."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.constants.freespace import (
    TEMPLATED_ADVISORY_TYPES,
    AdvisoryType,
    ChangeDirection,
    EngineState,
    Health,
)
from src.models.device import Device
from src.models.occupancy_history import OccupancyHistory
from src.models.site import Site
from src.models.site_message_template import SiteMessageTemplate
from src.models.zone import Zone
from src.services.freespace.loaders import (
    apply_engine_state,
    engine_state_from_row,
    load_engine_state_row,
    load_site_context,
    load_site_row_by_slug,
    load_snapshot,
    notification_window_to_json,
    parse_notification_window,
)
from src.services.freespace.site_bootstrap import reset_engine_cycle
from src.services.freespace.templates import DEFAULT_TEMPLATES
from src.services.freespace.types import (
    NotificationWindowRule,
    ZoneAdvisoryState,
    is_within_notification_window,
)
from tests.freespace.conftest import make_site, make_zone


SAST = timezone(timedelta(hours=2))


class TestNotificationWindow:
    def test_default_window_on_new_site(self, fs_site):
        rules = parse_notification_window(fs_site.notification_window)
        assert rules == (
            NotificationWindowRule(frozenset({1, 2, 3, 4, 5}), time(6, 0), time(10, 0)),
        )

    def test_contains_is_half_open_and_weekday_aware(self):
        rules = parse_notification_window(
            [{"weekdays": [1, 2, 3, 4, 5], "start": "06:00", "end": "10:00"}]
        )
        tuesday = datetime(2026, 11, 24, tzinfo=SAST)
        assert is_within_notification_window(rules, tuesday.replace(hour=6))
        assert is_within_notification_window(rules, tuesday.replace(hour=9, minute=59))
        assert not is_within_notification_window(rules, tuesday.replace(hour=10))
        assert not is_within_notification_window(
            rules, tuesday.replace(hour=5, minute=59)
        )
        saturday = datetime(2026, 11, 28, 8, tzinfo=SAST)
        assert not is_within_notification_window(rules, saturday)

    def test_empty_means_any_time(self):
        assert is_within_notification_window((), datetime(2026, 11, 28, 3, tzinfo=SAST))

    def test_roundtrip_and_validation(self):
        raw = [{"weekdays": [6, 7], "start": "07:30", "end": "09:00"}]
        assert notification_window_to_json(parse_notification_window(raw)) == raw
        with pytest.raises(ValueError):
            parse_notification_window(
                [{"weekdays": [1], "start": "10:00", "end": "06:00"}]
            )
        with pytest.raises(ValueError):
            parse_notification_window(
                [{"weekdays": [0], "start": "06:00", "end": "07:00"}]
            )


class TestSiteBootstrap:
    async def test_engine_state_and_templates_created(
        self, async_session, fs_site, fixed_clock
    ):
        state_row = await load_engine_state_row(async_session, fs_site.id)
        assert state_row is not None
        assert state_row.state == "IDLE"
        assert state_row.organization_id == fs_site.organization_id
        data = engine_state_from_row(state_row)
        assert data.state is EngineState.IDLE
        assert data.state_entered_at == fixed_clock.now()
        assert data.stale is True

        rows = (
            (
                await async_session.execute(
                    select(SiteMessageTemplate).where(
                        SiteMessageTemplate.site_id == fs_site.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {r.advisory_type for r in rows} == {
            t.value for t in TEMPLATED_ADVISORY_TYPES
        }
        assert all(r.locale == "en" for r in rows)
        by_type = {r.advisory_type: (r.title, r.body) for r in rows}
        assert by_type["SITE_INITIAL"] == DEFAULT_TEMPLATES[AdvisoryType.SITE_INITIAL]

    async def test_site_defaults(self, fs_site):
        assert fs_site.trigger_pct == 90 and fs_site.reset_pct == 80
        assert fs_site.change_points == 5 and fs_site.change_direction == "RISING"
        assert fs_site.stabilisation_s == 300 and fs_site.recommendation_margin == 10
        assert fs_site.stale_limit_s == 120 and fs_site.partial_is_stale is True
        assert fs_site.recovery_push is False and fs_site.zone_advisory is False
        assert fs_site.zone_reset_gap == 10 and fs_site.push_expiry_s == 1800
        assert fs_site.cooldown_s == 1800 and fs_site.daily_cap == 2
        assert fs_site.time_zone == "Africa/Johannesburg"

    async def test_reset_engine_cycle(self, async_session, fs_site, fixed_clock):
        row = await load_engine_state_row(async_session, fs_site.id)
        active = replace(
            engine_state_from_row(row),
            state=EngineState.ACTIVE,
            cycle_id=uuid.uuid4(),
            last_notified_pct=91.5,
            last_notified_zone_slug="b4",
            last_notified_top_zones=("b3", "b4"),
            last_sent_fingerprint="f" * 64,
            current_zone_slug="b4",
            current_zone_since=fixed_clock.now(),
            stale=False,
            zone_advisory={"b1": ZoneAdvisoryState(advised=True)},
        )
        apply_engine_state(row, active)
        await async_session.commit()

        fixed_clock.advance(60)
        fresh = await reset_engine_cycle(async_session, fs_site.id, fixed_clock.now())
        await async_session.commit()
        assert fresh.state is EngineState.IDLE
        assert fresh.state_entered_at == fixed_clock.now()
        assert fresh.cycle_id is None and fresh.last_notified_pct is None
        assert fresh.last_sent_fingerprint is None and dict(fresh.zone_advisory) == {}
        assert fresh.current_zone_slug == "b4" and fresh.stale is False
        stored = engine_state_from_row(
            await load_engine_state_row(async_session, fs_site.id)
        )
        assert stored == fresh

    async def test_reset_without_row_raises(self, async_session):
        with pytest.raises(LookupError):
            await reset_engine_cycle(
                async_session, uuid.uuid4(), datetime.now(timezone.utc)
            )


class TestEngineStateRoundtrip:
    async def test_all_fields_survive(self, async_session, fs_site, fixed_clock):
        row = await load_engine_state_row(async_session, fs_site.id)
        data = replace(
            engine_state_from_row(row),
            state=EngineState.PENDING,
            pending_since=fixed_clock.now(),
            cycle_id=uuid.uuid4(),
            last_notified_pct=90.25,
            last_notified_zone_slug="b2",
            last_notified_top_zones=("b2", "b3"),
            last_sent_fingerprint="a" * 64,
            last_sent_at=fixed_clock.now(),
            current_zone_slug="b2",
            current_zone_since=fixed_clock.now(),
            zone_advisory={
                "b1": ZoneAdvisoryState(above_since=fixed_clock.now(), advised=False)
            },
            stale=False,
            stale_since=None,
            inflight_event_id=uuid.uuid4(),
            inflight_fingerprint="b" * 64,
            last_evaluated_at=fixed_clock.now(),
        )
        site_id = fs_site.id
        apply_engine_state(row, data)
        await async_session.commit()
        async_session.expire_all()
        reloaded = engine_state_from_row(
            await load_engine_state_row(async_session, site_id)
        )
        assert reloaded == data


class TestSiteContext:
    async def test_loads_everything(
        self, async_session, fs_site, fs_zones, fs_snapshot
    ):
        await make_zone(
            async_session, fs_site, "gone", deleted_time=datetime.now(timezone.utc)
        )
        await fs_snapshot(
            fs_site,
            capacity=1200,
            occupied=1081,
            free_reserved=6,
            free_disabled=4,
            unknown=8,
            zones={"b1": {"capacity": 450, "occupied": 432, "free_disabled": 2}},
        )
        ctx = await load_site_context(async_session, fs_site.id)
        assert ctx is not None
        assert ctx.settings.slug == "absa-alice-lane"
        assert ctx.settings.change_direction is ChangeDirection.RISING
        assert [z.slug for z in ctx.zones] == ["b1", "b2", "b3", "b4"]
        assert ctx.snapshot.site is not None
        assert ctx.snapshot.site.free_usable == 1200 - 1081 - 6 - 4 - 8
        assert ctx.snapshot.site.health is Health.OK
        assert ctx.snapshot.site.received_at.tzinfo is not None
        assert set(ctx.snapshot.zones) == {"b1"}
        assert ctx.snapshot.zones["b1"].free_usable == 16
        assert set(ctx.templates) == set(TEMPLATED_ADVISORY_TYPES)

    async def test_never_reported_site(self, async_session, fs_site):
        view = await load_snapshot(async_session, fs_site.id)
        assert view.site is None and dict(view.zones) == {}

    async def test_missing_site(self, async_session):
        assert await load_site_context(async_session, uuid.uuid4()) is None

    async def test_lookup_by_slug_ignores_deleted(
        self, async_session, fs_site, fixed_clock
    ):
        assert (
            await load_site_row_by_slug(async_session, fs_site.slug)
        ).id == fs_site.id
        fs_site.deleted_time = fixed_clock.now()
        await async_session.commit()
        assert await load_site_row_by_slug(async_session, fs_site.slug) is None


class TestSchemaConstraints:
    async def test_site_slug_unique_among_live_rows(
        self, async_session, test_organization, second_organization, fixed_clock
    ):
        site = await make_site(async_session, test_organization, slug="dup")
        with pytest.raises(IntegrityError):
            await make_site(async_session, second_organization, slug="dup")
        await async_session.rollback()
        await async_session.refresh(site)
        await async_session.refresh(second_organization)
        site.deleted_time = fixed_clock.now()
        await async_session.commit()
        again = await make_site(async_session, second_organization, slug="dup")
        assert again.id != site.id

    async def test_zone_slug_unique_per_site(
        self, async_session, fs_site, fs_second_site
    ):
        await make_zone(async_session, fs_site, "b1")
        await make_zone(async_session, fs_second_site, "b1")  # other site: fine
        with pytest.raises(IntegrityError):
            await make_zone(async_session, fs_site, "b1")

    async def test_occupancy_history_one_point_per_minute(
        self, async_session, fs_site, fs_zones, fixed_clock
    ):
        minute = fixed_clock.now().replace(second=0, microsecond=0)
        site_id, org_id = fs_site.id, fs_site.organization_id
        b1, b2 = fs_zones["b1"].id, fs_zones["b2"].id

        def point(zone_id):
            return OccupancyHistory(
                organization_id=org_id,
                site_id=site_id,
                zone_id=zone_id,
                bucket_minute=minute,
                occupied=1,
                capacity=2,
                free_usable=1,
                health="OK",
            )

        async_session.add_all([point(None), point(b1), point(b2)])
        await async_session.commit()
        async_session.add(point(None))
        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()
        async_session.add(point(b1))
        with pytest.raises(IntegrityError):
            await async_session.commit()

    async def test_device_tombstones_may_share_null_hash(
        self, async_session, fixed_clock
    ):
        for _ in range(2):
            async_session.add(
                Device(
                    platform="ANDROID",
                    first_seen=fixed_clock.now(),
                    last_seen=fixed_clock.now(),
                    device_key_hash=None,
                    fcm_token=None,
                )
            )
        await async_session.commit()
        count = (
            await async_session.execute(select(func.count()).select_from(Device))
        ).scalar_one()
        assert count == 2

    async def test_site_and_zone_columns_default(
        self, async_session, test_organization
    ):
        site = Site(
            organization_id=test_organization.id, slug="x", name="X", fcm_topic="x"
        )
        async_session.add(site)
        await async_session.flush()
        zone = Zone(
            organization_id=site.organization_id, site_id=site.id, slug="z", name="Z"
        )
        async_session.add(zone)
        await async_session.commit()
        assert site.managed is False and site.listed is False
        assert site.notification_window == [
            {"weekdays": [1, 2, 3, 4, 5], "start": "06:00", "end": "10:00"}
        ]
        assert (
            zone.enabled is False
            and zone.recommendable is True
            and zone.priority == 100
        )
        assert (zone.limited_pct, zone.full_pct, zone.full_min_free) == (80, 95, 5)
        assert (
            zone.unknown_limit_pct == 25
            and zone.advisory_pct is None
            and zone.note == ""
        )
