"""
Pure rules engine (BF-52 - BF-57, BF-61, BF-62). OWNER: M6.

No I/O, no clock, no randomness beyond ``EventDraft.id`` / new cycle ids. The
DB shell (``evaluator.py``) loads inputs with ``loaders.py``, calls
``evaluate`` under the site row lock (D6), persists ``new_state`` and
``events`` and enqueues fan-outs (D7).

One evaluation, in order
------------------------
1. Availability (``availability.compute_site_availability``) with the stored
   ``current_zone_slug`` as stickiness input - the same computation the app
   sees (BF-24).
2. Staleness transition: ``DATA_STALE`` / ``DATA_RECOVERED`` when
   ``state.stale`` flips.
3. **Stale site** (§8.2 last row, BF-53): state and last-notified values are
   left alone; the running timers (``pending_since``, ``current_zone_since``,
   each zone's ``above_since``) are cleared so they restart from the next
   fresh snapshot (timers never advance across stale data). Any candidate
   the stored state would raise on the last figures is logged
   ``CANDIDATE / STALE_DATA``.
4. **Fresh site**: recommendation tracking (``current_zone_since`` = when the
   current recommendation became current), then the §8.2 state machine
   (``STATE_CHANGE`` events), then zone advisories (BF-56, only while the
   site is IDLE or PENDING after step 4's transition).
5. Every candidate goes through ``_decide`` (BF-57 usefulness, D10 in-flight
   guard, BF-61 shadow mode). A passing candidate becomes one ``ADVISORY``
   event with ``fanout_status = PENDING`` and becomes the in-flight advisory;
   a dropped one becomes one ``CANDIDATE`` event with the reason (the event
   writer collapses identical repeats, D11).

Cycle and "last-notified" bookkeeping
-------------------------------------
* A site cycle starts when the site goes ACTIVE (a fresh ``cycle_id``) and
  ends on RESET (``cycle_id = None``). Both boundaries clear
  ``last_sent_fingerprint`` and ``inflight_fingerprint``; RESET clears the
  last-notified values, going ACTIVE sets them (below).
* PENDING -> ACTIVE sets the last-notified level / recommendation / top
  zones to the current values (§8.2 row 3), independent of whether the
  ``SITE_INITIAL`` reaches a device. After that they advance only in
  ``on_fanout_completed`` with at least one device sent (BF-54) - or, for an
  unmanaged site, immediately "as if sent" (plan Q5b) through the same
  ``_advance_as_sent``.
* ``inflight_event_id`` is the advisory currently being fanned out.
  ``inflight_fingerprint`` is the fingerprint of the most recent advisory
  decided in this cycle that has not (yet) reached a device: it stays set
  after a fan-out that reached nobody, so the identical candidate is not
  re-raised every 30 s (BF-59: suppressed advisories are not retried).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Any
import uuid

from src.constants.freespace import (
    AdvisoryType,
    ChangeDirection,
    EngineState,
    EventType,
    FanoutStatus,
    StateChangeReason,
    SuppressionReason,
    ZoneStatus,
)
from src.services.freespace import templates as tpl
from src.services.freespace.availability import (
    compute_site_availability,
    meets_pct,
    occupancy_exact_pct,
)
from src.services.freespace.types import (
    Candidate,
    EngineStateData,
    EvaluationResult,
    EventDraft,
    MessageTemplate,
    SiteAvailability,
    SiteFigures,
    SiteSettings,
    SnapshotView,
    ZoneAdvisoryState,
    ZoneConfig,
)


# ``details["trigger"]`` values: which rule raised a candidate.
TRIGGER_STABILISED = "STABILISED"
TRIGGER_DELTA_RISE = "DELTA_RISE"
TRIGGER_DELTA_FALL = "DELTA_FALL"
TRIGGER_RECOMMENDATION = "RECOMMENDATION_CHANGED"
TRIGGER_RESET = "RESET"
TRIGGER_ZONE = "ZONE_THRESHOLD"

SITE_ADVISORY_TYPES: frozenset[AdvisoryType] = frozenset(
    {AdvisoryType.SITE_INITIAL, AdvisoryType.SITE_CHANGE}
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _held_for(since: datetime | None, now: datetime, seconds: int) -> bool:
    return since is not None and now - since >= timedelta(seconds=seconds)


def _at_or_below_pct(occupied: int, capacity: int, pct: float) -> bool:
    """Exact ``occupied / capacity <= pct / 100``."""
    if capacity <= 0:
        return False
    return Fraction(occupied * 100, capacity) <= Fraction(pct).limit_denominator(10**6)


def _template_for(
    templates: Mapping[AdvisoryType, MessageTemplate], advisory_type: AdvisoryType
) -> MessageTemplate:
    template = templates.get(advisory_type)
    if template is not None:
        return template
    title, body = tpl.DEFAULT_TEMPLATES[advisory_type]
    return MessageTemplate(advisory_type=advisory_type, title=title, body=body)


@dataclass
class _Run:
    """Mutable working set of one ``evaluate`` call."""

    settings: SiteSettings
    zones: Mapping[str, ZoneConfig]
    availability: SiteAvailability
    templates: Mapping[AdvisoryType, MessageTemplate]
    now: datetime
    figures: dict[str, Any]
    state: EngineStateData
    events: list[EventDraft]
    candidates: list[Candidate]

    # ── building blocks ──

    def zone_name(self, slug: str | None) -> str | None:
        if slug is None:
            return None
        zone = self.zones.get(slug)
        return zone.name if zone is not None else slug

    def event(self, event_type: EventType, **kwargs: Any) -> EventDraft:
        kwargs.setdefault("figures", self.figures)
        kwargs.setdefault(
            "recommended_zone_slug", self.availability.recommended_zone_slug
        )
        draft = EventDraft(type=event_type, occurred_at=self.now, **kwargs)
        self.events.append(draft)
        return draft

    def transition(
        self,
        to: EngineState,
        reason: StateChangeReason,
        *,
        event_cycle: uuid.UUID | None,
        **changes: Any,
    ) -> None:
        previous = self.state.state
        self.state = replace(self.state, state=to, state_entered_at=self.now, **changes)
        self.event(
            EventType.STATE_CHANGE,
            reason=reason.value,
            cycle_id=event_cycle,
            details={
                "from": previous.value,
                "to": to.value,
                "occupancyExact": _site_exact(self.availability),
            },
        )

    def candidate(
        self,
        advisory_type: AdvisoryType,
        *,
        recommended: str | None,
        top_zones: tuple[str, ...],
        zone_slug: str | None = None,
    ) -> Candidate:
        context = tpl.build_context(
            site_name=self.settings.name,
            zone_name=self.zone_name(recommended),
            top_zone_names=[self.zone_name(s) or s for s in top_zones],
            occupancy_pct=self.availability.occupancy_pct,
            full_zone_name=self.zone_name(zone_slug),
        )
        rendered = tpl.render(_template_for(self.templates, advisory_type), context)
        return Candidate(
            advisory_type=advisory_type,
            recommended_zone_slug=recommended,
            top_zones=top_zones,
            occupancy_pct=self.availability.occupancy_pct,
            occupancy_exact=_site_exact(self.availability),
            title=rendered.title,
            body=rendered.body,
            fingerprint=tpl.fingerprint(
                advisory_type, recommended, top_zones, rendered.body
            ),
            zone_slug=zone_slug,
        )

    def decide(self, candidate: Candidate) -> str | None:
        """BF-57 usefulness + D10 in-flight guard + BF-61 shadow mode.
        Returns the suppression reason, or None when it should fan out."""
        state = self.state
        if candidate.recommended_zone_slug is None:
            return SuppressionReason.NO_RECOMMENDATION.value
        # A ZONE_ADVISORY is deduplicated by its own per-zone cycle (BF-56
        # ``advised``): after a zone-cycle reset the same text is wanted again.
        if (
            candidate.advisory_type != AdvisoryType.ZONE_ADVISORY
            and candidate.fingerprint is not None
            and candidate.fingerprint
            in (state.last_sent_fingerprint, state.inflight_fingerprint)
        ):
            return SuppressionReason.NO_MATERIAL_CHANGE.value
        if candidate.advisory_type == AdvisoryType.SITE_CHANGE:
            if candidate.recommended_zone_slug == state.last_notified_zone_slug and set(
                candidate.top_zones
            ) == set(state.last_notified_top_zones):
                return SuppressionReason.NO_MATERIAL_CHANGE.value
            if state.inflight_event_id is not None:
                return SuppressionReason.IN_FLIGHT.value
        if not self.settings.managed:
            return SuppressionReason.UNMANAGED.value
        return None

    def emit(
        self,
        candidate: Candidate,
        *,
        cycle_id: uuid.UUID | None,
        trigger: str,
        forced_reason: str | None = None,
    ) -> Candidate:
        """Decide (unless ``forced_reason``) and record one candidate."""
        reason = forced_reason if forced_reason is not None else self.decide(candidate)
        candidate = replace(candidate, suppressed=reason)
        self.candidates.append(candidate)
        details = {
            "trigger": trigger,
            "occupancyPct": candidate.occupancy_pct,
            "occupancyExact": candidate.occupancy_exact,
            "topZones": list(candidate.top_zones),
        }
        common: dict[str, Any] = {
            "advisory_type": candidate.advisory_type,
            "zone_slug": candidate.zone_slug,
            "cycle_id": cycle_id,
            "recommended_zone_slug": candidate.recommended_zone_slug,
            "rendered_title": candidate.title,
            "rendered_body": candidate.body,
            "fingerprint": candidate.fingerprint,
            "details": details,
        }
        if reason is None:
            draft = self.event(
                EventType.ADVISORY, fanout_status=FanoutStatus.PENDING, **common
            )
            self.state = replace(
                self.state,
                inflight_event_id=draft.id,
                inflight_fingerprint=candidate.fingerprint,
            )
            return candidate
        self.event(EventType.CANDIDATE, reason=reason, **common)
        if reason == SuppressionReason.UNMANAGED.value:
            # Plan Q5b: shadow mode advances as if the advisory had been sent.
            self.state = _advance_as_sent(
                self.state,
                cycle_id=cycle_id,
                advisory_type=candidate.advisory_type,
                fingerprint=candidate.fingerprint or "",
                recommended_zone_slug=candidate.recommended_zone_slug,
                top_zones=candidate.top_zones,
                occupancy_exact=candidate.occupancy_exact,
                now=self.now,
            )
        return candidate


def _site_exact(availability: SiteAvailability) -> float | None:
    if availability.occupied is None or availability.capacity is None:
        return None
    return occupancy_exact_pct(availability.occupied, availability.capacity)


def _cycle_cleared(**changes: Any) -> dict[str, Any]:
    """Field values that end/start a cycle (last-notified values cleared)."""
    values: dict[str, Any] = {
        "last_notified_pct": None,
        "last_notified_zone_slug": None,
        "last_notified_top_zones": (),
        "last_sent_fingerprint": None,
        "inflight_fingerprint": None,
        "pending_since": None,
    }
    values.update(changes)
    return values


def _advance_as_sent(
    state: EngineStateData,
    *,
    cycle_id: uuid.UUID | None,
    advisory_type: AdvisoryType,
    fingerprint: str,
    recommended_zone_slug: str | None,
    top_zones: Sequence[str],
    occupancy_exact: float | None,
    now: datetime,
) -> EngineStateData:
    """BF-54: the advisory reached at least one device (or would have, in
    shadow mode). No-op when the cycle it belonged to has ended."""
    if cycle_id != state.cycle_id:
        return state
    changes: dict[str, Any] = {
        "last_sent_fingerprint": fingerprint or None,
        "last_sent_at": now,
    }
    if advisory_type in SITE_ADVISORY_TYPES:
        changes.update(
            last_notified_pct=occupancy_exact,
            last_notified_zone_slug=recommended_zone_slug,
            last_notified_top_zones=tuple(top_zones),
        )
    return replace(state, **changes)


# ─────────────────────────────────────────────────────────────
# Rules
# ─────────────────────────────────────────────────────────────


def _delta_trigger(
    settings: SiteSettings, state: EngineStateData, site: SiteFigures
) -> str | None:
    """BF-55: rise of Δ over the last-notified level (or, with BOTH, a fall
    of Δ; the caller guarantees occupancy is still >= R)."""
    if state.last_notified_pct is None:
        return None
    if meets_pct(
        site.occupied, site.capacity, state.last_notified_pct + settings.change_points
    ):
        return TRIGGER_DELTA_RISE
    if settings.change_direction == ChangeDirection.BOTH and _at_or_below_pct(
        site.occupied, site.capacity, state.last_notified_pct - settings.change_points
    ):
        return TRIGGER_DELTA_FALL
    return None


def _stale_candidates(
    run: _Run, original: EngineStateData, site: SiteFigures | None
) -> None:
    """§8.2 last row: whatever the stored state would raise on the last known
    figures is logged ``STALE_DATA``; no state moves."""
    if site is None or site.capacity <= 0:
        return
    settings = run.settings
    raised: list[tuple[AdvisoryType, str]] = []
    if original.state == EngineState.PENDING:
        if meets_pct(site.occupied, site.capacity, settings.trigger_pct) and _held_for(
            original.pending_since, run.now, settings.stabilisation_s
        ):
            raised.append((AdvisoryType.SITE_INITIAL, TRIGGER_STABILISED))
    elif original.state == EngineState.ACTIVE:
        if not meets_pct(site.occupied, site.capacity, settings.reset_pct):
            if settings.recovery_push:
                raised.append((AdvisoryType.RECOVERY, TRIGGER_RESET))
        else:
            trigger = _delta_trigger(settings, original, site)
            if trigger is not None:
                raised.append((AdvisoryType.SITE_CHANGE, trigger))
    for advisory_type, trigger in raised:
        run.emit(
            run.candidate(advisory_type, recommended=None, top_zones=()),
            cycle_id=original.cycle_id,
            trigger=trigger,
            forced_reason=SuppressionReason.STALE_DATA.value,
        )


def _track_recommendation(run: _Run) -> None:
    recommended = run.availability.recommended_zone_slug
    state = run.state
    if recommended != state.current_zone_slug:
        run.state = replace(
            state,
            current_zone_slug=recommended,
            current_zone_since=run.now if recommended is not None else None,
        )
    elif recommended is not None and state.current_zone_since is None:
        run.state = replace(state, current_zone_since=run.now)


def _site_machine(run: _Run, site: SiteFigures) -> None:
    """§8.2 rows 1-6 on fresh data."""
    settings = run.settings
    availability = run.availability
    at_trigger = meets_pct(site.occupied, site.capacity, settings.trigger_pct)
    entered_active = False

    if run.state.state == EngineState.IDLE and at_trigger:
        run.transition(
            EngineState.PENDING,
            StateChangeReason.TRIGGER_CROSSED,
            event_cycle=run.state.cycle_id,
            pending_since=run.now,
        )

    if run.state.state == EngineState.PENDING:
        if not at_trigger:
            run.transition(
                EngineState.IDLE,
                StateChangeReason.NOT_STABLE,
                event_cycle=run.state.cycle_id,
                pending_since=None,
            )
        else:
            if run.state.pending_since is None:  # restarted after stale data
                run.state = replace(run.state, pending_since=run.now)
            if _held_for(run.state.pending_since, run.now, settings.stabilisation_s):
                cycle_id = uuid.uuid4()
                # §8.2 row 3: the transition itself sets last-notified level
                # and recommendation (and top zones) to the current values,
                # whether or not the SITE_INITIAL reaches anyone. A
                # SITE_INITIAL suppressed for every phone is therefore not
                # re-raised as a same-recommendation SITE_CHANGE, and Δ is
                # measured from this level. BF-54 governs later advances.
                run.transition(
                    EngineState.ACTIVE,
                    StateChangeReason.STABILISED,
                    event_cycle=cycle_id,
                    **_cycle_cleared(
                        cycle_id=cycle_id,
                        last_notified_pct=_site_exact(availability),
                        last_notified_zone_slug=availability.recommended_zone_slug,
                        last_notified_top_zones=tuple(availability.top_zones),
                    ),
                )
                entered_active = True
                run.emit(
                    run.candidate(
                        AdvisoryType.SITE_INITIAL,
                        recommended=availability.recommended_zone_slug,
                        top_zones=availability.top_zones,
                    ),
                    cycle_id=cycle_id,
                    trigger=TRIGGER_STABILISED,
                )

    if run.state.state != EngineState.ACTIVE or entered_active:
        return

    if not meets_pct(site.occupied, site.capacity, settings.reset_pct):
        old_cycle = run.state.cycle_id
        run.transition(
            EngineState.IDLE,
            StateChangeReason.RESET,
            event_cycle=old_cycle,
            **_cycle_cleared(cycle_id=None),
        )
        if settings.recovery_push:
            run.emit(
                run.candidate(
                    AdvisoryType.RECOVERY,
                    recommended=availability.recommended_zone_slug,
                    top_zones=availability.top_zones,
                ),
                cycle_id=old_cycle,
                trigger=TRIGGER_RESET,
            )
        return

    state = run.state
    trigger = _delta_trigger(settings, state, site)
    if trigger is None and (
        availability.recommended_zone_slug != state.last_notified_zone_slug
        and _held_for(state.current_zone_since, run.now, settings.stabilisation_s)
    ):
        trigger = TRIGGER_RECOMMENDATION
    if trigger is not None:
        run.emit(
            run.candidate(
                AdvisoryType.SITE_CHANGE,
                recommended=availability.recommended_zone_slug,
                top_zones=availability.top_zones,
            ),
            cycle_id=state.cycle_id,
            trigger=trigger,
        )


def _zone_advisory_recommendation(run: _Run, full_zone: str) -> str | None:
    """The zone to point at from a ZONE_ADVISORY: the site recommendation,
    unless that is the advising zone itself, then the next ranked zone."""
    recommended = run.availability.recommended_zone_slug
    if recommended is None or recommended != full_zone:
        return recommended
    return next((z.slug for z in run.availability.ranked if z.slug != full_zone), None)


def _zone_advisories(run: _Run, snapshot: SnapshotView, site_stale: bool) -> None:
    """BF-56. Per preferred zone with ``advisory_pct``: track the continuous
    fresh run at/above the level (or FULL), advise once per zone cycle while
    the site is IDLE/PENDING, reset below ``advisory_pct - zone_reset_gap``."""
    settings = run.settings
    availability_by_slug = {z.slug: z for z in run.availability.zones}
    new_map: dict[str, ZoneAdvisoryState] = {}
    for zone in sorted(run.zones.values(), key=lambda z: (z.display_order, z.slug)):
        if not (zone.enabled and zone.preferred and zone.advisory_pct is not None):
            continue
        previous = run.state.zone_advisory.get(zone.slug, ZoneAdvisoryState())
        figures = snapshot.zones.get(zone.slug)
        row = availability_by_slug.get(zone.slug)
        if (
            site_stale
            or not settings.zone_advisory
            or figures is None
            or row is None
            or row.stale
        ):
            # Timers never run across stale data (BF-53 applied to zones).
            new_map[zone.slug] = replace(previous, above_since=None)
            continue
        above = (
            meets_pct(figures.occupied, figures.capacity, zone.advisory_pct)
            or row.status == ZoneStatus.FULL
        )
        if not above:
            reset = not meets_pct(
                figures.occupied,
                figures.capacity,
                zone.advisory_pct - settings.zone_reset_gap,
            )
            new_map[zone.slug] = ZoneAdvisoryState(
                above_since=None, advised=False if reset else previous.advised
            )
            continue
        current = ZoneAdvisoryState(
            above_since=previous.above_since or run.now, advised=previous.advised
        )
        if (
            not current.advised
            and run.state.state in (EngineState.IDLE, EngineState.PENDING)
            and _held_for(current.above_since, run.now, settings.stabilisation_s)
        ):
            decided = run.emit(
                run.candidate(
                    AdvisoryType.ZONE_ADVISORY,
                    recommended=_zone_advisory_recommendation(run, zone.slug),
                    top_zones=run.availability.top_zones,
                    zone_slug=zone.slug,
                ),
                cycle_id=run.state.cycle_id,
                trigger=TRIGGER_ZONE,
            )
            if decided.suppressed in (
                None,
                SuppressionReason.UNMANAGED.value,
                SuppressionReason.NO_MATERIAL_CHANGE.value,
            ):
                current = replace(current, advised=True)
        new_map[zone.slug] = current
    run.state = replace(run.state, zone_advisory=MappingProxyType(new_map))


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────


def evaluate(
    settings: SiteSettings,
    zones: Sequence[ZoneConfig],
    snapshot: SnapshotView,
    state: EngineStateData,
    templates: Mapping[AdvisoryType, MessageTemplate],
    now: datetime,
) -> EvaluationResult:
    """Evaluate one site at ``now`` and return the new state, the events to
    write and the candidates raised. Pure and deterministic given inputs
    (except generated event ids). ``templates`` may lack a type; then the
    module default from ``templates.DEFAULT_TEMPLATES`` is used."""
    availability = compute_site_availability(
        settings, zones, snapshot, state.current_zone_slug, now
    )
    run = _Run(
        settings=settings,
        zones={z.slug: z for z in zones},
        availability=availability,
        templates=templates,
        now=now,
        figures=event_figures(availability),
        state=state,
        events=[],
        candidates=[],
    )

    if availability.stale:
        if not state.stale:
            run.event(EventType.DATA_STALE, cycle_id=state.cycle_id)
            run.state = replace(run.state, stale=True, stale_since=now)
        elif state.stale_since is None:
            run.state = replace(run.state, stale_since=now)
        # BF-53: timers restart from the next fresh snapshot.
        run.state = replace(run.state, pending_since=None, current_zone_since=None)
        _stale_candidates(run, state, snapshot.site)
        _zone_advisories(run, snapshot, site_stale=True)
    else:
        if state.stale:
            run.event(
                EventType.DATA_RECOVERED,
                cycle_id=state.cycle_id,
                details={"staleSince": _iso(state.stale_since)},
            )
            run.state = replace(run.state, stale=False, stale_since=None)
        site = snapshot.site
        assert site is not None  # a fresh site always has figures
        _track_recommendation(run)
        _site_machine(run, site)
        _zone_advisories(run, snapshot, site_stale=False)

    run.state = replace(run.state, last_evaluated_at=now)
    return EvaluationResult(
        new_state=run.state,
        events=tuple(run.events),
        candidates=tuple(run.candidates),
        availability=availability,
    )


def on_fanout_completed(
    state: EngineStateData,
    *,
    event_id: uuid.UUID,
    cycle_id: uuid.UUID | None,
    advisory_type: AdvisoryType,
    fingerprint: str,
    recommended_zone_slug: str | None,
    top_zones: Sequence[str],
    occupancy_exact: float | None,
    sent_count: int,
    now: datetime,
) -> EngineStateData:
    """BF-54 / D10: called by the fan-out (M7) under the site row lock when
    the fan-out of ``event_id`` finishes (also on failure, with the
    ``sent_count`` reached). Clears the in-flight guard if it points at
    ``event_id``. Only when ``cycle_id`` equals ``state.cycle_id`` (a reset
    in between - BF-72 or RESET - makes the outcome irrelevant) and
    ``sent_count >= 1``: for SITE_INITIAL / SITE_CHANGE advance
    last_notified_pct / zone / top zones; for any type set
    last_sent_fingerprint / last_sent_at. RECOVERY keeps the already-cleared
    last-notified values cleared. Returns the new state.

    When the fan-out reached nobody (``sent_count == 0``) in the current
    cycle, ``inflight_fingerprint`` is kept (only ``inflight_event_id`` is
    cleared), so the identical candidate is dropped as NO_MATERIAL_CHANGE
    instead of being re-raised on every evaluation (BF-59)."""
    new = state
    same_cycle = cycle_id == state.cycle_id
    if state.inflight_event_id == event_id:
        keep_fingerprint = same_cycle and sent_count < 1
        new = replace(
            new,
            inflight_event_id=None,
            inflight_fingerprint=(
                state.inflight_fingerprint if keep_fingerprint else None
            ),
        )
    if sent_count >= 1:
        new = _advance_as_sent(
            new,
            cycle_id=cycle_id,
            advisory_type=advisory_type,
            fingerprint=fingerprint,
            recommended_zone_slug=recommended_zone_slug,
            top_zones=top_zones,
            occupancy_exact=occupancy_exact,
            now=now,
        )
    return new


def event_figures(availability: SiteAvailability) -> dict[str, Any]:
    """BF-62 figures snapshot for ``site_event.figures``:
    ``{"site": {capacity, occupied, freeUsable, occupancyPct, health, stale},
    "zones": {slug: {capacity, free, occupancyPct, status, health}}}``.
    JSON-serialisable; no device data."""
    return {
        "site": {
            "capacity": availability.capacity,
            "occupied": availability.occupied,
            "freeUsable": availability.free_usable,
            "occupancyPct": availability.occupancy_pct,
            "health": availability.health.value if availability.health else None,
            "stale": availability.stale,
        },
        "zones": {
            zone.slug: {
                "capacity": zone.capacity,
                "free": zone.free,
                "occupancyPct": zone.occupancy_pct,
                "status": zone.status.value,
                "health": zone.health.value if zone.health else None,
            }
            for zone in availability.zones
        },
    }
