"""
Frozen value types shared by the pure Freespace core and its callers.

The pure modules (``availability``, ``engine``, ``templates``) take and return
ONLY these types plus builtins: no ORM rows, no sessions, no clocks. Build
them from rows with ``src/services/freespace/loaders.py``.

Conventions
-----------
* Zones are identified by SLUG (the wire ``zoneId``) everywhere in the core.
* Every datetime is timezone-aware UTC.
* "pct" settings are whole percentage points (e.g. ``trigger_pct = 90``).
  Exact occupancy comparisons use ``availability.meets_pct`` (integer
  arithmetic), never floats (BF-20: 89.9 % is below a 90 % trigger).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from types import MappingProxyType
from typing import Any
import uuid

from src.constants.freespace import (
    AdvisoryType,
    ChangeDirection,
    EngineState,
    EventType,
    FanoutStatus,
    Health,
    ZoneStatus,
)


def _empty_mapping() -> Mapping[Any, Any]:
    return MappingProxyType({})


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationWindowRule:
    """One notification window rule in SITE LOCAL time (§10.1).

    ``weekdays`` are ISO numbers (1 = Monday ... 7 = Sunday). ``start < end``;
    no overnight span in this revision. The window is half-open
    ``[start, end)``.
    """

    weekdays: frozenset[int]
    start: time
    end: time

    def contains(self, local_dt: datetime) -> bool:
        """True when ``local_dt`` (already in site local time) is inside."""
        return (
            local_dt.isoweekday() in self.weekdays
            and self.start <= local_dt.time().replace(tzinfo=None) < self.end
        )


def is_within_notification_window(
    rules: tuple[NotificationWindowRule, ...], local_dt: datetime
) -> bool:
    """BF-58 check 2. An empty rule list means "no window": always True."""
    if not rules:
        return True
    return any(rule.contains(local_dt) for rule in rules)


@dataclass(frozen=True)
class SiteSettings:
    """Everything the core needs to know about a site (BF-1, §10.1)."""

    site_id: uuid.UUID  # site row id
    organization_id: uuid.UUID
    slug: str  # wire siteId
    name: str
    time_zone: str
    fcm_topic: str
    managed: bool
    listed: bool
    trigger_pct: int = 90
    reset_pct: int = 80
    change_points: int = 5
    change_direction: ChangeDirection = ChangeDirection.RISING
    stabilisation_s: int = 300
    recommendation_margin: int = 10
    stale_limit_s: int = 120
    partial_is_stale: bool = True
    recovery_push: bool = False
    zone_advisory: bool = False
    zone_reset_gap: int = 10
    notification_window: tuple[NotificationWindowRule, ...] = ()
    cooldown_s: int = 1800
    daily_cap: int = 2
    push_expiry_s: int = 1800


@dataclass(frozen=True)
class ZoneConfig:
    """A zone's configuration (BF-2, §10.2). Live (non-deleted) zones only."""

    zone_id: uuid.UUID  # zone row id
    slug: str  # wire zoneId
    name: str
    display_order: int = 0
    enabled: bool = True
    recommendable: bool = True
    preferred: bool = False
    priority: int = 100
    limited_pct: int = 80
    full_pct: int = 95
    full_min_free: int = 5
    unknown_limit_pct: int = 25
    advisory_pct: int | None = None
    discovered: bool = False


@dataclass(frozen=True)
class MessageTemplate:
    """A site's template for one advisory type (BF-70)."""

    advisory_type: AdvisoryType
    title: str
    body: str
    locale: str = "en"


@dataclass(frozen=True)
class RenderedMessage:
    """Output of ``templates.render``."""

    title: str
    body: str


# ─────────────────────────────────────────────────────────────
# Snapshot figures (BF-3)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Figures:
    """Counts as stored in a snapshot row. ``health`` is the EFFECTIVE health
    (after the BF-12 PARTIAL downgrade); ``received_at`` is the backend clock."""

    capacity: int
    occupied: int
    free_usable: int
    free_reserved: int
    free_disabled: int
    unknown: int
    health: Health
    measured_at: datetime
    received_at: datetime


@dataclass(frozen=True)
class SiteFigures(Figures):
    """Site totals as computed by ParkIT (never summed from zones, §5.2)."""


@dataclass(frozen=True)
class ZoneFigures(Figures):
    """One zone's latest figures."""

    zone_slug: str = ""


@dataclass(frozen=True)
class SnapshotView:
    """The latest snapshot of a site: ``site`` is None when the site has never
    received data; ``zones`` maps zone slug -> figures for zones that have a
    snapshot row (a zone with no row has never been reported)."""

    site: SiteFigures | None
    zones: Mapping[str, ZoneFigures] = field(default_factory=_empty_mapping)


# ─────────────────────────────────────────────────────────────
# Engine state (BF-5)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ZoneAdvisoryState:
    """Per-zone advisory cycle state (BF-56)."""

    above_since: datetime | None = None  # start of continuous fresh run >= advisoryPct
    advised: bool = False  # already advised in this zone cycle


@dataclass(frozen=True)
class EngineStateData:
    """Pure mirror of a ``site_engine_state`` row. See the model for meanings."""

    state: EngineState
    state_entered_at: datetime
    pending_since: datetime | None = None
    cycle_id: uuid.UUID | None = None
    last_notified_pct: float | None = None
    last_notified_zone_slug: str | None = None
    last_notified_top_zones: tuple[str, ...] = ()
    last_sent_fingerprint: str | None = None
    last_sent_at: datetime | None = None
    current_zone_slug: str | None = None
    current_zone_since: datetime | None = None
    zone_advisory: Mapping[str, ZoneAdvisoryState] = field(
        default_factory=_empty_mapping
    )
    stale: bool = True
    stale_since: datetime | None = None
    inflight_event_id: uuid.UUID | None = None
    inflight_fingerprint: str | None = None
    last_evaluated_at: datetime | None = None


def initial_engine_state(now: datetime) -> EngineStateData:
    """State of a brand-new site, or after a fresh-cycle reset (BF-72)."""
    return EngineStateData(state=EngineState.IDLE, state_entered_at=now, stale=True)


# ─────────────────────────────────────────────────────────────
# Availability results (BF-20 - BF-25, BF-31)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RankedZone:
    """A recommendation candidate in BF-24 ranking order."""

    slug: str
    name: str
    free_usable: int
    priority: int


@dataclass(frozen=True)
class ZoneAvailability:
    """One zone as the app sees it (BF-23, BF-31), plus admin extras.

    Count fields are None when the zone has never been reported.
    ``occupancy_pct`` is ``floor(ratio * 100)`` (BF-20), None when capacity is
    0 or unknown.
    """

    slug: str
    name: str
    display_order: int
    enabled: bool
    recommendable: bool
    status: ZoneStatus
    stale: bool
    capacity: int | None
    occupied: int | None
    free: int | None  # freeUsable
    occupancy_pct: int | None
    health: Health | None
    as_of: datetime | None  # receivedAt


@dataclass(frozen=True)
class SiteAvailability:
    """Result of ``availability.compute_site_availability``.

    ``zones`` contains EVERY zone passed in, in display order (then slug);
    the app endpoint filters ``enabled``. ``ranked`` is the full BF-24 ranking
    of candidates; ``top_zones`` the first two slugs (BF-25);
    ``recommended_zone_slug`` the sticky recommendation, None when there are
    no candidates or the site is stale.
    """

    site_slug: str
    stale: bool
    as_of: datetime | None  # site receivedAt
    age_seconds: int | None
    capacity: int | None
    occupied: int | None
    free_usable: int | None
    occupancy_pct: int | None  # floor, for display
    health: Health | None
    recommended_zone_slug: str | None
    top_zones: tuple[str, ...]
    ranked: tuple[RankedZone, ...]
    zones: tuple[ZoneAvailability, ...]


# ─────────────────────────────────────────────────────────────
# Engine outputs (BF-52 - BF-62)
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Candidate:
    """An advisory candidate raised by the engine (BF-52, BF-56).

    ``suppressed`` is the SuppressionReason value when the candidate was
    dropped before fan-out (BF-57, BF-61, stale), else None (it fans out).
    ``zone_slug`` is the full zone of a ZONE_ADVISORY, else None.
    """

    advisory_type: AdvisoryType
    recommended_zone_slug: str | None
    top_zones: tuple[str, ...]
    occupancy_pct: int | None  # floor, as rendered
    occupancy_exact: float | None  # exact ratio x 100, for last_notified_pct
    title: str | None
    body: str | None
    fingerprint: str | None
    suppressed: str | None = None
    zone_slug: str | None = None


@dataclass(frozen=True)
class EventDraft:
    """An event to persist via ``events.write_event``. Mirrors ``site_event``.

    ``id`` is generated up-front so the engine can reference it (e.g. as
    ``EngineStateData.inflight_event_id``) before the row exists.
    ``fanout_status = PENDING`` marks an advisory the shell must enqueue.
    """

    type: EventType
    occurred_at: datetime
    reason: str | None = None
    advisory_type: AdvisoryType | None = None
    zone_slug: str | None = None
    cycle_id: uuid.UUID | None = None
    figures: Mapping[str, Any] | None = None
    recommended_zone_slug: str | None = None
    rendered_title: str | None = None
    rendered_body: str | None = None
    fingerprint: str | None = None
    counts: Mapping[str, int] | None = None
    fanout_status: FanoutStatus | None = None
    details: Mapping[str, Any] | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass(frozen=True)
class EvaluationResult:
    """Output of ``engine.evaluate``.

    ``new_state`` replaces the stored state; ``events`` are written in order;
    ``candidates`` lists every candidate raised (sent or suppressed) for
    tests and diagnostics; ``availability`` is the computation the decision
    used (the same one the app sees, BF-24).
    """

    new_state: EngineStateData
    events: tuple[EventDraft, ...]
    candidates: tuple[Candidate, ...]
    availability: SiteAvailability

    @property
    def fanout_event_ids(self) -> tuple[uuid.UUID, ...]:
        """Ids of advisory events that need a fan-out job."""
        return tuple(
            e.id for e in self.events if e.fanout_status == FanoutStatus.PENDING
        )
