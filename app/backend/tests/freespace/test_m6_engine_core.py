"""
M6 pure engine core: §8.2 state machine, BF-53 - BF-57, BF-61, in-flight
guard, AT-01 - AT-08 and BT-09, all against ``engine.evaluate`` with a
``FixedClock`` (BF-85). No database.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any
import uuid

import pytest

from src.constants.freespace import (
    AdvisoryType,
    ChangeDirection,
    EngineState,
    EventType,
    FanoutStatus,
    Health,
    StateChangeReason,
    SuppressionReason,
    ZoneStatus,
)
from src.services.freespace import engine
from src.services.freespace import templates as tpl
from src.services.freespace.clock import FixedClock
from src.services.freespace.types import (
    EngineStateData,
    EvaluationResult,
    SiteFigures,
    SiteSettings,
    SnapshotView,
    ZoneConfig,
    ZoneFigures,
    initial_engine_state,
)
from tests.freespace.conftest import FIXED_START


SITE_CAPACITY = 1000
ZONE_CAPACITY = 250


def make_settings(**overrides: Any) -> SiteSettings:
    base: dict[str, Any] = {
        "site_id": uuid.UUID(int=1),
        "organization_id": uuid.UUID(int=2),
        "slug": "absa-alice-lane",
        "name": "Alice Lane",
        "time_zone": "Africa/Johannesburg",
        "fcm_topic": "freespace-alice",
        "managed": True,
        "listed": True,
    }
    base.update(overrides)
    return SiteSettings(**base)


def make_zones(**per_zone: dict[str, Any]) -> tuple[ZoneConfig, ...]:
    return tuple(
        ZoneConfig(
            zone_id=uuid.UUID(int=10 + i),
            slug=f"b{i}",
            name=f"Basement {i}",
            display_order=i,
            **per_zone.get(f"b{i}", {}),
        )
        for i in range(1, 5)
    )


def figures(cls: type, capacity: int, occupied: int, at: datetime, **kw: Any) -> Any:
    health = kw.pop("health", Health.OK)
    return cls(
        capacity=capacity,
        occupied=occupied,
        free_usable=max(0, capacity - occupied),
        free_reserved=0,
        free_disabled=0,
        unknown=0,
        health=health,
        measured_at=at,
        received_at=at,
        **kw,
    )


# Default zone occupancy: b4 freest, then b3 (top two = b4, b3).
DEFAULT_ZONE_OCC = {"b1": 240, "b2": 230, "b3": 200, "b4": 150}


@dataclass
class Sim:
    """Drives the pure engine through time like intake + tick would."""

    settings: SiteSettings = field(default_factory=make_settings)
    zones: tuple[ZoneConfig, ...] = field(default_factory=make_zones)
    clock: FixedClock = field(default_factory=lambda: FixedClock(FIXED_START))
    state: EngineStateData = field(
        default_factory=lambda: initial_engine_state(FIXED_START)
    )
    snapshot: SnapshotView = field(default_factory=lambda: SnapshotView(site=None))
    history: list[EvaluationResult] = field(default_factory=list)

    def post(
        self,
        site_pct: float,
        zone_occ: dict[str, int] | None = None,
        *,
        zone_health: dict[str, Health] | None = None,
        site_health: Health = Health.OK,
    ) -> EvaluationResult:
        """A fresh snapshot arrives now; evaluate."""
        now = self.clock.now()
        occupied = round(SITE_CAPACITY * site_pct / 100)
        occ = dict(DEFAULT_ZONE_OCC if zone_occ is None else zone_occ)
        self.snapshot = SnapshotView(
            site=figures(SiteFigures, SITE_CAPACITY, occupied, now, health=site_health),
            zones={
                slug: figures(
                    ZoneFigures,
                    ZONE_CAPACITY,
                    value,
                    now,
                    health=(zone_health or {}).get(slug, Health.OK),
                    zone_slug=slug,
                )
                for slug, value in occ.items()
            },
        )
        return self.evaluate()

    def evaluate(self) -> EvaluationResult:
        """An evaluation with no new data (the tick)."""
        result = engine.evaluate(
            self.settings, self.zones, self.snapshot, self.state, {}, self.clock.now()
        )
        self.state = result.new_state
        self.history.append(result)
        return result

    def hold(
        self, site_pct: float, seconds: int, step: int = 30, **kw: Any
    ) -> list[EvaluationResult]:
        """Post ``site_pct`` every ``step`` s for ``seconds`` (inclusive end)."""
        results = []
        for _ in range(seconds // step):
            self.clock.advance(step)
            results.append(self.post(site_pct, **kw))
        return results

    def complete(self, result: EvaluationResult, sent: int = 1) -> None:
        """Simulate the M7 fan-out finishing for the advisory in ``result``."""
        (advisory,) = [e for e in result.events if e.type == EventType.ADVISORY]
        details = dict(advisory.details or {})
        self.state = engine.on_fanout_completed(
            self.state,
            event_id=advisory.id,
            cycle_id=advisory.cycle_id,
            advisory_type=AdvisoryType(advisory.advisory_type),
            fingerprint=advisory.fingerprint or "",
            recommended_zone_slug=advisory.recommended_zone_slug,
            top_zones=tuple(details.get("topZones", ())),
            occupancy_exact=details.get("occupancyExact"),
            sent_count=sent,
            now=self.clock.now(),
        )

    def go_active(self, pct: float = 90, **kw: Any) -> EvaluationResult:
        """IDLE -> PENDING -> ACTIVE (S = 300 s); fan-out sent to one device."""
        self.post(pct, **kw)
        result = self.hold(pct, self.settings.stabilisation_s, **kw)[-1]
        assert self.state.state is EngineState.ACTIVE
        self.complete(result)
        return result


def types_of(result: EvaluationResult) -> list[EventType]:
    return [e.type for e in result.events]


def advisories(result: EvaluationResult) -> list[Any]:
    return [e for e in result.events if e.type == EventType.ADVISORY]


def candidate_events(result: EvaluationResult) -> list[Any]:
    return [e for e in result.events if e.type == EventType.CANDIDATE]


def state_changes(result: EvaluationResult) -> list[str | None]:
    return [e.reason for e in result.events if e.type == EventType.STATE_CHANGE]


# ─────────────────────────────────────────────────────────────
# AT-01 - AT-08
# ─────────────────────────────────────────────────────────────


class TestAcceptance:
    def test_at01_75_percent_no_candidate(self):
        sim = Sim()
        result = sim.post(75)
        assert result.availability.occupancy_pct == 75
        assert result.availability.recommended_zone_slug == "b4"
        assert result.candidates == ()
        assert sim.state.state is EngineState.IDLE
        sim.hold(75, 600)
        assert all(r.candidates == () for r in sim.history)

    def test_at02_not_stable(self):
        sim = Sim()
        first = sim.post(90)
        assert sim.state.state is EngineState.PENDING
        assert state_changes(first) == [StateChangeReason.TRIGGER_CROSSED]
        sim.hold(90, 240)
        assert sim.state.state is EngineState.PENDING
        sim.clock.advance(30)
        result = sim.post(88)
        assert sim.state.state is EngineState.IDLE
        assert state_changes(result) == [StateChangeReason.NOT_STABLE]
        assert all(r.candidates == () for r in sim.history)
        assert sim.state.pending_since is None

    def test_at03_stabilised_sends_site_initial(self):
        sim = Sim()
        sim.post(90)
        results = sim.hold(90, 300)
        assert all(r.candidates == () for r in results[:-1])
        last = results[-1]
        assert sim.state.state is EngineState.ACTIVE
        assert state_changes(last) == [StateChangeReason.STABILISED]
        (advisory,) = advisories(last)
        assert advisory.advisory_type == AdvisoryType.SITE_INITIAL
        assert advisory.fanout_status == FanoutStatus.PENDING
        assert advisory.recommended_zone_slug == "b4"
        assert advisory.details["topZones"] == ["b4", "b3"]
        assert "Basement 4 and Basement 3" in (advisory.rendered_body or "")
        assert last.fanout_event_ids == (advisory.id,)
        assert sim.state.cycle_id is not None
        assert advisory.cycle_id == sim.state.cycle_id
        assert sim.state.inflight_event_id == advisory.id

    def test_at03_stabilisation_zero_fires_immediately(self):
        sim = Sim(settings=make_settings(stabilisation_s=0))
        result = sim.post(91)
        assert state_changes(result) == [
            StateChangeReason.TRIGGER_CROSSED,
            StateChangeReason.STABILISED,
        ]
        assert len(advisories(result)) == 1

    def test_at04_small_rise_no_candidate(self):
        sim = Sim()
        sim.go_active(90)
        assert sim.state.last_notified_pct == pytest.approx(90.0)
        sim.clock.advance(30)
        assert sim.post(92).candidates == ()

    def test_at05_rise_same_recommendation_dropped(self):
        sim = Sim()
        sim.go_active(90)
        sim.clock.advance(30)
        result = sim.post(95)
        (candidate,) = result.candidates
        assert candidate.advisory_type == AdvisoryType.SITE_CHANGE
        assert candidate.suppressed == SuppressionReason.NO_MATERIAL_CHANGE
        assert advisories(result) == []
        assert sim.state.last_notified_pct == pytest.approx(90.0)  # BF-54

    def test_at05_rise_with_new_recommendation_sent(self):
        sim = Sim()
        sim.go_active(90)
        sim.clock.advance(30)
        # b4 fills up, b2 empties (more than the margin): new recommendation.
        result = sim.post(95, {"b1": 240, "b2": 100, "b3": 200, "b4": 230})
        (advisory,) = advisories(result)
        assert advisory.advisory_type == AdvisoryType.SITE_CHANGE
        assert advisory.recommended_zone_slug == "b2"
        assert advisory.details["trigger"] == engine.TRIGGER_DELTA_RISE
        sim.complete(result, sent=812)
        assert sim.state.last_notified_pct == pytest.approx(95.0)
        assert sim.state.last_notified_zone_slug == "b2"

    @pytest.mark.parametrize("recovery_push", [False, True])
    def test_at06_reset_and_new_cycle(self, recovery_push):
        sim = Sim(settings=make_settings(recovery_push=recovery_push))
        sim.go_active(90)
        old_cycle = sim.state.cycle_id
        sim.clock.advance(30)
        result = sim.post(79)
        assert sim.state.state is EngineState.IDLE
        assert state_changes(result) == [StateChangeReason.RESET]
        assert sim.state.last_notified_pct is None
        assert sim.state.last_notified_zone_slug is None
        assert sim.state.last_notified_top_zones == ()
        assert sim.state.cycle_id is None
        if recovery_push:
            (advisory,) = advisories(result)
            assert advisory.advisory_type == AdvisoryType.RECOVERY
            assert advisory.cycle_id == old_cycle
        else:
            assert result.candidates == ()
        # A later rise to 90 % starts a new cycle.
        sim.clock.advance(600)
        assert state_changes(sim.post(90)) == [StateChangeReason.TRIGGER_CROSSED]
        last = sim.hold(90, 300)[-1]
        (initial,) = advisories(last)
        assert initial.advisory_type == AdvisoryType.SITE_INITIAL
        assert sim.state.cycle_id not in (None, old_cycle)

    def test_at07_zone_full_site_below_trigger(self):
        zone_occ = {"b1": 245, "b2": 230, "b3": 200, "b4": 112}  # b1 98 %, b4 ~55 %
        # Off by default: no candidate at all.
        sim = Sim()
        sim.post(85, zone_occ)
        sim.hold(85, 600, zone_occ=zone_occ)
        assert sim.history[-1].availability.recommended_zone_slug == "b4"
        assert all(r.candidates == () for r in sim.history)
        # Enabled but b1 not preferred: still nothing.
        sim = Sim(
            settings=make_settings(zone_advisory=True),
            zones=make_zones(b1={"advisory_pct": 95}),
        )
        sim.post(85, zone_occ)
        sim.hold(85, 600, zone_occ=zone_occ)
        assert all(r.candidates == () for r in sim.history)
        # Enabled and preferred: one ZONE_ADVISORY after S, pointing at b4.
        sim = Sim(
            settings=make_settings(zone_advisory=True),
            zones=make_zones(b1={"advisory_pct": 95, "preferred": True}),
        )
        sim.post(85, zone_occ)
        results = sim.hold(85, 600, zone_occ=zone_occ)
        raised = [c for r in sim.history for c in r.candidates]
        assert len(raised) == 1
        (candidate,) = raised
        assert candidate.advisory_type == AdvisoryType.ZONE_ADVISORY
        assert candidate.zone_slug == "b1"
        assert candidate.recommended_zone_slug == "b4"
        assert candidate.suppressed is None
        assert candidate.body == "Basement 1 is full. Basement 4 has available bays."
        assert sim.state.state is EngineState.IDLE
        assert len(advisories(results[9])) == 1  # at t0 + 300 s

    def test_at08_no_ingest_three_minutes(self):
        sim = Sim()
        sim.go_active(90)
        assert sim.state.stale is False
        before = sim.state
        events = []
        for _ in range(6):  # 3 minutes of ticks, no submissions
            sim.clock.advance(30)
            events += sim.evaluate().events
        result = sim.history[-1]
        assert result.availability.stale is True
        assert result.availability.recommended_zone_slug is None
        assert [e.type for e in events].count(EventType.DATA_STALE) == 1
        assert sim.state.state is EngineState.ACTIVE
        assert sim.state.last_notified_pct == before.last_notified_pct
        assert sim.state.cycle_id == before.cycle_id

    def test_at08_stale_candidates_suppressed(self):
        sim = Sim()
        sim.go_active(90)
        sim.clock.advance(30)
        sim.post(96)  # NO_MATERIAL_CHANGE (same recommendation)
        sim.clock.advance(200)
        result = sim.evaluate()  # stale now; Δ still crossed on last figures
        (candidate,) = result.candidates
        assert candidate.suppressed == SuppressionReason.STALE_DATA
        assert candidate.advisory_type == AdvisoryType.SITE_CHANGE
        assert advisories(result) == []
        assert sim.state.state is EngineState.ACTIVE

    def test_at08_stale_site_offline_health(self):
        sim = Sim()
        sim.go_active(90)
        sim.clock.advance(30)
        result = sim.post(97, site_health=Health.OFFLINE)
        assert result.availability.stale is True
        assert all(
            c.suppressed == SuppressionReason.STALE_DATA for c in result.candidates
        )
        assert advisories(result) == []

    def test_at08_offline_zone_never_recommended(self):
        sim = Sim()
        result = sim.post(75, zone_health={"b4": Health.OFFLINE})
        b4 = next(z for z in result.availability.zones if z.slug == "b4")
        assert b4.status == ZoneStatus.UNKNOWN
        assert result.availability.recommended_zone_slug == "b3"
        sim.state = replace(sim.state, current_zone_slug="b4")
        sim.clock.advance(30)
        result = sim.post(75, zone_health={"b4": Health.OFFLINE})
        assert result.availability.recommended_zone_slug == "b3"


# ─────────────────────────────────────────────────────────────
# §8.2 table rows not covered above, BF-53 - BF-55
# ─────────────────────────────────────────────────────────────


class TestStateMachine:
    def test_recommendation_change_must_hold_for_s(self):
        sim = Sim()
        sim.go_active(90)
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}  # b2 now best
        sim.clock.advance(30)
        first = sim.post(91, moved)
        assert first.candidates == ()
        assert sim.state.current_zone_slug == "b2"
        results = sim.hold(91, 300, zone_occ=moved)
        assert all(r.candidates == () for r in results[:-1])
        (advisory,) = advisories(results[-1])
        assert advisory.advisory_type == AdvisoryType.SITE_CHANGE
        assert advisory.recommended_zone_slug == "b2"
        assert advisory.details["trigger"] == engine.TRIGGER_RECOMMENDATION

    def test_recommendation_flapping_does_not_fire(self):
        sim = Sim()
        sim.go_active(90)
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}
        for _ in range(10):
            sim.clock.advance(120)
            sim.post(91, moved)
            sim.clock.advance(120)
            sim.post(91)
        assert all(advisories(r) == [] for r in sim.history[-20:])

    def test_bf53_stale_during_pending_restarts_stabilisation(self):
        sim = Sim()
        sim.post(90)  # t0: PENDING
        sim.hold(90, 120)  # t0 + 120 s
        for _ in range(6):  # stale for 3 minutes (no submissions)
            sim.clock.advance(30)
            sim.evaluate()
        assert sim.state.state is EngineState.PENDING
        assert sim.state.pending_since is None
        # Data back at t0 + 300 + ... : not stable yet although 5 min passed.
        sim.clock.advance(30)
        back = sim.post(90)
        assert back.candidates == ()
        assert sim.state.state is EngineState.PENDING
        assert sim.state.pending_since == sim.clock.now()
        restarted_at = sim.clock.now()
        results = sim.hold(90, 300)
        assert all(r.candidates == () for r in results[:-1])
        assert sim.state.state is EngineState.ACTIVE
        assert sim.clock.now() - restarted_at == timedelta(seconds=300)

    def test_stale_pending_below_trigger_on_return_is_not_stable(self):
        sim = Sim()
        sim.post(90)
        sim.clock.advance(200)
        sim.evaluate()  # stale
        sim.clock.advance(30)
        result = sim.post(85)
        assert state_changes(result) == [StateChangeReason.NOT_STABLE]
        assert EventType.DATA_RECOVERED in types_of(result)

    def test_stale_transitions_logged_once(self):
        sim = Sim()
        first = sim.post(50)
        assert EventType.DATA_RECOVERED in types_of(first)  # initial state is stale
        sim.clock.advance(30)
        assert sim.post(50).events == ()
        sim.clock.advance(200)
        assert types_of(sim.evaluate()) == [EventType.DATA_STALE]
        sim.clock.advance(30)
        assert sim.evaluate().events == ()
        sim.clock.advance(30)
        assert types_of(sim.post(50)) == [EventType.DATA_RECOVERED]

    def test_bf55_rising_ignores_falls(self):
        sim = Sim()
        sim.go_active(95)
        sim.clock.advance(30)
        assert sim.post(89).candidates == ()

    def test_bf55_both_counts_falls_above_reset(self):
        sim = Sim(settings=make_settings(change_direction=ChangeDirection.BOTH))
        sim.go_active(95)
        sim.clock.advance(30)
        result = sim.post(90, {"b1": 240, "b2": 100, "b3": 200, "b4": 230})
        (advisory,) = advisories(result)
        assert advisory.advisory_type == AdvisoryType.SITE_CHANGE
        assert advisory.details["trigger"] == engine.TRIGGER_DELTA_FALL
        sim.clock.advance(30)
        sim.post(92)  # small move: nothing (in flight anyway)
        assert sim.history[-1].candidates == ()

    def test_bf55_both_fall_below_reset_is_reset_not_change(self):
        sim = Sim(settings=make_settings(change_direction=ChangeDirection.BOTH))
        sim.go_active(95)
        sim.clock.advance(30)
        result = sim.post(70)
        assert state_changes(result) == [StateChangeReason.RESET]
        assert result.candidates == ()

    def test_exact_ratio_below_trigger(self):
        sim = Sim()
        sim.post(89.9)
        assert sim.state.state is EngineState.IDLE

    def test_settings_change_next_evaluation(self):
        sim = Sim()
        sim.post(86)
        assert sim.state.state is EngineState.IDLE
        sim.settings = make_settings(trigger_pct=85, reset_pct=75)
        sim.clock.advance(30)
        sim.post(86)
        assert sim.state.state is EngineState.PENDING


# ─────────────────────────────────────────────────────────────
# BF-54, BF-56, BF-57, in-flight guard, BT-09
# ─────────────────────────────────────────────────────────────


class TestLastNotified:
    def test_initial_transition_sets_last_notified(self):
        """§8.2 row 3: PENDING -> ACTIVE sets last-notified level and
        recommendation at the transition, before any fan-out."""
        sim = Sim()
        sim.post(90)
        sim.hold(90, 300)
        assert sim.state.last_notified_pct == pytest.approx(90.0)
        assert sim.state.last_notified_zone_slug == "b4"
        assert sim.state.last_notified_top_zones == ("b4", "b3")
        assert sim.state.last_sent_fingerprint is None

    def test_zero_sent_keeps_transition_values(self):
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        sim.complete(result, sent=0)
        assert sim.state.last_notified_pct == pytest.approx(90.0)
        assert sim.state.last_sent_fingerprint is None
        assert sim.state.inflight_event_id is None

    def test_initial_reaching_nobody_is_not_resent_as_change(self):
        """Review R2: a SITE_INITIAL suppressed for every phone (window,
        cooldown, cap, no devices, auth failure) must not come back as a
        SITE_CHANGE with the same recommendation at the next evaluation."""
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        (initial,) = advisories(result)
        assert initial.advisory_type == AdvisoryType.SITE_INITIAL
        sim.complete(result, sent=0)
        for later in sim.hold(90, 600):
            assert advisories(later) == []
            assert later.candidates == ()
        # BF-57: Δ crossed with the same recommendation -> nothing material
        sim.clock.advance(30)
        (candidate,) = sim.post(95).candidates
        assert candidate.advisory_type == AdvisoryType.SITE_CHANGE
        assert candidate.suppressed == SuppressionReason.NO_MATERIAL_CHANGE

    def test_initial_reaching_nobody_delta_still_works(self):
        """Δ is measured from the transition level for the rest of the cycle:
        a rise of Δ with a new recommendation is a SITE_CHANGE."""
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        sim.complete(result, sent=0)
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}
        sim.clock.advance(30)
        (advisory,) = advisories(sim.post(95, moved))
        assert advisory.advisory_type == AdvisoryType.SITE_CHANGE
        assert advisory.details["trigger"] == engine.TRIGGER_DELTA_RISE
        assert advisory.recommended_zone_slug == "b2"

    def test_sent_advances_everything(self):
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        (advisory,) = advisories(result)
        sim.complete(result, sent=1)
        assert sim.state.last_notified_pct == pytest.approx(90.0)
        assert sim.state.last_notified_zone_slug == "b4"
        assert sim.state.last_notified_top_zones == ("b4", "b3")
        assert sim.state.last_sent_fingerprint == advisory.fingerprint
        assert sim.state.last_sent_at == sim.clock.now()
        assert sim.state.inflight_event_id is None
        assert sim.state.inflight_fingerprint is None

    def test_cycle_change_ignores_late_completion(self):
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        sim.clock.advance(30)
        sim.post(70)  # RESET before the fan-out finished
        sim.complete(result, sent=5)
        assert sim.state.last_notified_pct is None
        assert sim.state.last_sent_fingerprint is None
        assert sim.state.inflight_event_id is None

    def test_suppressed_candidate_does_not_advance(self):
        sim = Sim()
        sim.go_active(90)
        sim.clock.advance(30)
        sim.post(96)  # NO_MATERIAL_CHANGE
        assert sim.state.last_notified_pct == pytest.approx(90.0)

    def test_completion_of_other_event_keeps_inflight(self):
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        inflight = sim.state.inflight_event_id
        sim.state = engine.on_fanout_completed(
            sim.state,
            event_id=uuid.uuid4(),
            cycle_id=None,
            advisory_type=AdvisoryType.ZONE_ADVISORY,
            fingerprint="x",
            recommended_zone_slug="b4",
            top_zones=(),
            occupancy_exact=None,
            sent_count=0,
            now=sim.clock.now(),
        )
        assert sim.state.inflight_event_id == inflight == advisories(result)[0].id


class TestZoneAdvisory:
    def _sim(self, **settings: Any) -> Sim:
        return Sim(
            settings=make_settings(zone_advisory=True, **settings),
            zones=make_zones(b1={"advisory_pct": 90, "preferred": True}),
        )

    @staticmethod
    def occ(b1: int) -> dict[str, int]:
        return {"b1": b1, "b2": 200, "b3": 200, "b4": 150}

    def zone_candidates(self, sim: Sim) -> list[Any]:
        return [
            c
            for r in sim.history
            for c in r.candidates
            if c.advisory_type == AdvisoryType.ZONE_ADVISORY
        ]

    def test_once_per_cycle_and_reset_gap(self):
        sim = self._sim()
        sim.post(70, self.occ(230))  # b1 92 %
        sim.hold(70, 900, zone_occ=self.occ(230))
        assert len(self.zone_candidates(sim)) == 1
        assert sim.state.zone_advisory["b1"].advised is True
        # Dips to 84 % (above 90 - 10 = 80): cycle not reset.
        sim.hold(70, 60, zone_occ=self.occ(210))
        sim.hold(70, 600, zone_occ=self.occ(230))
        assert len(self.zone_candidates(sim)) == 1
        # Falls to 76 % (< 80): cycle resets; holds again for S: advises again.
        sim.hold(70, 60, zone_occ=self.occ(190))
        assert sim.state.zone_advisory["b1"].advised is False
        sim.hold(70, 330, zone_occ=self.occ(230))  # run starts at the first post
        assert len(self.zone_candidates(sim)) == 2

    def test_requires_hold_for_s(self):
        sim = self._sim()
        sim.post(70, self.occ(230))
        sim.hold(70, 270, zone_occ=self.occ(230))
        assert self.zone_candidates(sim) == []
        sim.hold(70, 30, zone_occ=self.occ(230))
        assert len(self.zone_candidates(sim)) == 1

    def test_not_while_site_active(self):
        sim = self._sim()
        sim.post(90, self.occ(230))
        sim.hold(90, 900, zone_occ=self.occ(230))
        assert sim.state.state is EngineState.ACTIVE
        assert self.zone_candidates(sim) == []

    def test_pending_site_still_advises(self):
        sim = self._sim(stabilisation_s=300)
        sim.post(70, self.occ(230))
        sim.hold(70, 240, zone_occ=self.occ(230))
        sim.hold(90, 60, zone_occ=self.occ(230))  # site PENDING at t0 + 300
        assert sim.state.state is EngineState.PENDING
        assert len(self.zone_candidates(sim)) == 1

    def test_full_by_free_bays_counts(self):
        sim = Sim(
            settings=make_settings(zone_advisory=True),
            zones=make_zones(b1={"advisory_pct": 99, "preferred": True}),
        )
        sim.post(70, self.occ(247))  # 98.8 % < 99 but free 3 < 5: FULL
        sim.hold(70, 300, zone_occ=self.occ(247))
        assert len(self.zone_candidates(sim)) == 1

    def test_stale_zone_restarts_timer(self):
        sim = self._sim()
        sim.post(70, self.occ(230))
        sim.hold(70, 240, zone_occ=self.occ(230))
        sim.clock.advance(30)
        sim.post(70, self.occ(230), zone_health={"b1": Health.OFFLINE})
        assert sim.state.zone_advisory["b1"].above_since is None
        # The new run starts with the next fresh snapshot (30 s later).
        sim.hold(70, 300, zone_occ=self.occ(230))
        assert self.zone_candidates(sim) == []
        sim.hold(70, 30, zone_occ=self.occ(230))
        assert len(self.zone_candidates(sim)) == 1

    def test_recommendation_is_not_the_advising_zone(self):
        sim = Sim(
            settings=make_settings(zone_advisory=True),
            zones=make_zones(b4={"advisory_pct": 50, "preferred": True}),
        )
        occ = {"b1": 240, "b2": 230, "b3": 200, "b4": 150}  # b4 60 %, best zone
        sim.post(70, occ)
        sim.hold(70, 300, zone_occ=occ)
        (candidate,) = self.zone_candidates(sim)
        assert candidate.zone_slug == "b4"
        assert candidate.recommended_zone_slug == "b3"


class TestUsefulness:
    def test_no_recommendation(self):
        sim = Sim()
        full = {"b1": 248, "b2": 248, "b3": 248, "b4": 248}
        sim.post(99, full)
        result = sim.hold(99, 300, zone_occ=full)[-1]
        (candidate,) = result.candidates
        assert candidate.advisory_type == AdvisoryType.SITE_INITIAL
        assert candidate.suppressed == SuppressionReason.NO_RECOMMENDATION
        assert advisories(result) == []
        assert sim.state.state is EngineState.ACTIVE
        assert sim.state.inflight_event_id is None

    def test_site_change_unchanged_recommendation_and_top_two(self):
        sim = Sim()
        sim.go_active(90)
        sim.clock.advance(30)
        (candidate,) = sim.post(95).candidates
        assert candidate.suppressed == SuppressionReason.NO_MATERIAL_CHANGE

    def test_fingerprint_equal_to_last_sent(self):
        sim = Sim()
        sim.go_active(90)
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}  # rec b2, top b2,b3
        sim.clock.advance(30)
        sim.complete(sim.post(95, moved))  # SITE_CHANGE -> b2 sent
        # Δ again, same recommendation b2 but different second zone: the
        # top-two set changed, so only the fingerprint (type + zone + body)
        # catches it.
        sim.clock.advance(30)
        result = sim.post(100.0, {"b1": 200, "b2": 100, "b3": 240, "b4": 230})
        (candidate,) = result.candidates
        assert candidate.recommended_zone_slug == "b2"
        assert candidate.top_zones == ("b2", "b1")
        assert candidate.fingerprint == sim.state.last_sent_fingerprint
        assert candidate.suppressed == SuppressionReason.NO_MATERIAL_CHANGE

    def test_fingerprint_matches_template_fingerprint(self):
        sim = Sim()
        sim.post(90)
        (candidate,) = sim.hold(90, 300)[-1].candidates
        assert candidate.fingerprint == tpl.fingerprint(
            AdvisoryType.SITE_INITIAL, "b4", ("b3", "b4"), candidate.body or ""
        )


class TestInFlightGuard:
    def test_site_change_while_initial_in_flight(self):
        sim = Sim()
        sim.post(90)
        sim.hold(90, 300)  # SITE_INITIAL in flight
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}
        sim.clock.advance(30)
        result = sim.post(95, moved)  # Δ rise + new recommendation
        (candidate,) = result.candidates
        assert candidate.advisory_type == AdvisoryType.SITE_CHANGE
        assert candidate.suppressed == SuppressionReason.IN_FLIGHT
        assert advisories(result) == []

    def test_identical_to_inflight_fingerprint(self):
        sim = Sim()
        sim.go_active(90)
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}
        sim.clock.advance(30)
        first = sim.post(95, moved)
        (advisory,) = advisories(first)
        assert sim.state.inflight_fingerprint == advisory.fingerprint
        sim.clock.advance(30)
        (candidate,) = sim.post(95, moved).candidates
        assert candidate.suppressed == SuppressionReason.NO_MATERIAL_CHANGE

    def test_zero_sent_identical_candidate_not_reraised(self):
        sim = Sim()
        sim.go_active(90)
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}
        sim.clock.advance(30)
        first = sim.post(95, moved)
        sim.complete(first, sent=0)  # every phone suppressed (window, cooldown)
        for _ in range(5):
            sim.clock.advance(30)
            result = sim.post(95, moved)
            assert advisories(result) == []
            assert (
                result.candidates[0].suppressed == SuppressionReason.NO_MATERIAL_CHANGE
            )
        assert sim.state.last_notified_zone_slug == "b4"  # BF-54


class TestShadowMode:
    def test_bt09_unmanaged_logged_nothing_sent(self):
        sim = Sim(settings=make_settings(managed=False))
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        (candidate,) = result.candidates
        assert candidate.suppressed == SuppressionReason.UNMANAGED
        assert advisories(result) == []
        assert result.fanout_event_ids == ()
        (event,) = candidate_events(result)
        assert event.reason == SuppressionReason.UNMANAGED
        assert event.advisory_type == AdvisoryType.SITE_INITIAL
        # Plan Q5b: last-notified advanced as if sent.
        assert sim.state.last_notified_pct == pytest.approx(90.0)
        assert sim.state.last_notified_zone_slug == "b4"
        assert sim.state.inflight_event_id is None

    def test_shadow_mirrors_live_behaviour(self):
        live, shadow = Sim(), Sim(settings=make_settings(managed=False))
        moved = {"b1": 240, "b2": 100, "b3": 200, "b4": 230}
        script = [(90, None)] * 11 + [(92, None), (95, None), (95, moved), (79, None)]
        live_reasons, shadow_reasons = [], []
        for pct, occ in script:
            for sim, out in ((live, live_reasons), (shadow, shadow_reasons)):
                result = sim.post(pct, occ)
                if advisories(result):
                    sim.complete(result)
                out.append(
                    [
                        (c.advisory_type, c.suppressed or "SENT")
                        for c in result.candidates
                    ]
                )
                sim.clock.advance(30)
        assert [
            [(t, "UNMANAGED" if r == "SENT" else r) for t, r in step]
            for step in live_reasons
        ] == shadow_reasons
        assert any(step for step in shadow_reasons)


class TestEventFigures:
    def test_shape_and_every_decision_has_figures(self):
        sim = Sim()
        sim.post(90)
        result = sim.hold(90, 300)[-1]
        fig = engine.event_figures(result.availability)
        assert fig["site"] == {
            "capacity": 1000,
            "occupied": 900,
            "freeUsable": 100,
            "occupancyPct": 90,
            "health": "OK",
            "stale": False,
        }
        assert fig["zones"]["b4"] == {
            "capacity": 250,
            "free": 100,
            "occupancyPct": 60,
            "status": "AVAILABLE",
            "health": "OK",
        }
        for event in result.events:
            assert event.figures == fig
            assert event.recommended_zone_slug == "b4"

    def test_never_reported_site(self):
        sim = Sim()
        result = sim.evaluate()
        assert result.events == ()
        assert engine.event_figures(result.availability)["site"]["capacity"] is None
