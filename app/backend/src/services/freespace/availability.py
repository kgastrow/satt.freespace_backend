"""
Pure availability core (BF-20 - BF-25). OWNER: M4.

No I/O, no clock: every function takes ``now`` explicitly. The SAME
``compute_site_availability`` is used by the app endpoint (M4), the admin
live view (M8) and the rules engine (M6), so they can never disagree (BF-24,
D9). The app endpoint passes the STORED recommendation
(``site_engine_state.current_zone_slug``) as ``current_recommendation`` and
does not persist anything; the engine persists the result.

Implemented here (shared primitives, do not change): ``occupancy_ratio``,
``occupancy_pct_floor``, ``meets_pct``, ``age_seconds``.
M4 (BF-21 - BF-25): staleness, zone status, ranking, stickiness, top-two and
the single entry point ``compute_site_availability``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from fractions import Fraction
import math

from src.constants.freespace import Health, ZoneStatus
from src.services.freespace.types import (
    Figures,
    RankedZone,
    SiteAvailability,
    SiteFigures,
    SiteSettings,
    SnapshotView,
    ZoneAvailability,
    ZoneConfig,
    ZoneFigures,
)


# ─────────────────────────────────────────────────────────────
# Shared primitives (implemented)
# ─────────────────────────────────────────────────────────────


def occupancy_ratio(occupied: int, capacity: int) -> Fraction | None:
    """Exact ``occupied / capacity`` (BF-20); None when capacity is 0."""
    if capacity <= 0:
        return None
    return Fraction(occupied, capacity)


def occupancy_pct_floor(occupied: int, capacity: int) -> int | None:
    """App display value ``floor(ratio * 100)`` (BF-20); None when capacity is 0."""
    ratio = occupancy_ratio(occupied, capacity)
    if ratio is None:
        return None
    return math.floor(ratio * 100)


def meets_pct(occupied: int, capacity: int, pct: float) -> bool:
    """Exact ``occupied / capacity >= pct / 100`` (BF-20: 89.9 % < 90 %).

    ``pct`` may be fractional (e.g. ``last_notified_pct + change_points``);
    it is compared exactly via ``Fraction``. False when capacity is 0.
    """
    if capacity <= 0:
        return False
    threshold = Fraction(pct).limit_denominator(10**6)
    return Fraction(occupied * 100, capacity) >= threshold


def occupancy_exact_pct(occupied: int, capacity: int) -> float | None:
    """``ratio * 100`` as a float, for storing ``last_notified_pct``."""
    ratio = occupancy_ratio(occupied, capacity)
    return None if ratio is None else float(ratio * 100)


def age_seconds(figures: Figures | None, now: datetime) -> int | None:
    """Whole seconds since ``received_at`` (BF-31 ``ageSeconds``), floored at 0."""
    if figures is None:
        return None
    return max(0, int((now - figures.received_at).total_seconds()))


# ─────────────────────────────────────────────────────────────
# M4: staleness, status, ranking, recommendation
# ─────────────────────────────────────────────────────────────


def _exceeds_pct(part: int, whole: int, pct: float) -> bool:
    """Exact ``part / whole > pct / 100`` (strictly greater). ``whole > 0``."""
    threshold = Fraction(pct).limit_denominator(10**6)
    return Fraction(part * 100, whole) > threshold


def _is_too_old(figures: Figures, settings: SiteSettings, now: datetime) -> bool:
    """``now - received_at > stale_limit_s`` (exact; exactly at the limit is
    still fresh). A ``received_at`` in the future is never too old."""
    return (now - figures.received_at) > timedelta(seconds=settings.stale_limit_s)


def _bad_health(settings: SiteSettings, health: Health) -> bool:
    if health == Health.OFFLINE:
        return True
    return health == Health.PARTIAL and settings.partial_is_stale


def is_zone_stale(
    settings: SiteSettings,
    zone: ZoneConfig,
    figures: ZoneFigures | None,
    now: datetime,
) -> bool:
    """BF-21. True when the zone has no figures, or any of:
    ``now - received_at > stale_limit_s``; health OFFLINE; capacity 0;
    ``unknown / capacity > unknown_limit_pct / 100`` (exact); health PARTIAL
    and ``settings.partial_is_stale``."""
    if figures is None:
        return True
    if _is_too_old(figures, settings, now):
        return True
    if _bad_health(settings, figures.health):
        return True
    if figures.capacity <= 0:
        return True
    return _exceeds_pct(figures.unknown, figures.capacity, zone.unknown_limit_pct)


def is_site_stale(
    settings: SiteSettings, figures: SiteFigures | None, now: datetime
) -> bool:
    """BF-22. True when the site has never been reported, or
    ``now - received_at > stale_limit_s``, or health OFFLINE, or (with
    ``partial_is_stale``) PARTIAL, or capacity 0."""
    if figures is None:
        return True
    if _is_too_old(figures, settings, now):
        return True
    if _bad_health(settings, figures.health):
        return True
    return figures.capacity <= 0


def _status_of_fresh(zone: ZoneConfig, figures: ZoneFigures) -> ZoneStatus:
    """BF-23 for a zone already known to be fresh (capacity > 0)."""
    if (
        meets_pct(figures.occupied, figures.capacity, zone.full_pct)
        or figures.free_usable < zone.full_min_free
    ):
        return ZoneStatus.FULL
    if meets_pct(figures.occupied, figures.capacity, zone.limited_pct):
        return ZoneStatus.LIMITED
    return ZoneStatus.AVAILABLE


def zone_status(
    settings: SiteSettings,
    zone: ZoneConfig,
    figures: ZoneFigures | None,
    now: datetime,
) -> ZoneStatus:
    """BF-23: UNKNOWN if stale; FULL if occupancy >= full_pct (exact) or
    free_usable < full_min_free; LIMITED if occupancy >= limited_pct;
    else AVAILABLE."""
    if figures is None or is_zone_stale(settings, zone, figures, now):
        return ZoneStatus.UNKNOWN
    return _status_of_fresh(zone, figures)


def _ranking_key(zone: RankedZone) -> tuple[int, int, str]:
    return (-zone.free_usable, zone.priority, zone.slug)


def rank_candidates(
    zones: Sequence[tuple[ZoneConfig, ZoneFigures, ZoneStatus]],
) -> tuple[RankedZone, ...]:
    """BF-24 steps 1-2. Keep zones that are enabled, recommendable and whose
    status is neither UNKNOWN nor FULL; order by free_usable DESC, priority
    ASC, slug ASC."""
    candidates = [
        RankedZone(
            slug=config.slug,
            name=config.name,
            free_usable=figures.free_usable,
            priority=config.priority,
        )
        for config, figures, status in zones
        if config.enabled
        and config.recommendable
        and status not in (ZoneStatus.UNKNOWN, ZoneStatus.FULL)
    ]
    return tuple(sorted(candidates, key=_ranking_key))


def sticky_recommendation(
    ranked: Sequence[RankedZone],
    current: str | None,
    margin: int,
    *,
    site_stale: bool,
) -> str | None:
    """BF-24 steps 3-4. None if ``site_stale`` or no candidates. Keep
    ``current`` while it is still a candidate unless the top candidate's
    free_usable exceeds current's by MORE than ``margin``; otherwise the top
    candidate. BT-05: 100/104 alternating with margin 10 never flips.

    ``ranked`` must be in BF-24 order (as returned by ``rank_candidates``).
    """
    if site_stale or not ranked:
        return None
    top = ranked[0]
    if current is None or current == top.slug:
        return top.slug
    incumbent = next((zone for zone in ranked if zone.slug == current), None)
    if incumbent is None:  # no longer a candidate
        return top.slug
    if top.free_usable - incumbent.free_usable > margin:
        return top.slug
    return incumbent.slug


def top_two(ranked: Sequence[RankedZone]) -> tuple[str, ...]:
    """BF-25: slugs of the first two ranked candidates (0, 1 or 2 items)."""
    return tuple(zone.slug for zone in ranked[:2])


def _zone_availability(
    settings: SiteSettings,
    zone: ZoneConfig,
    figures: ZoneFigures | None,
    now: datetime,
) -> tuple[ZoneAvailability, ZoneStatus]:
    stale = is_zone_stale(settings, zone, figures, now)
    status = (
        ZoneStatus.UNKNOWN
        if stale or figures is None
        else _status_of_fresh(zone, figures)
    )
    return (
        ZoneAvailability(
            slug=zone.slug,
            name=zone.name,
            display_order=zone.display_order,
            enabled=zone.enabled,
            recommendable=zone.recommendable,
            status=status,
            stale=stale,
            capacity=None if figures is None else figures.capacity,
            occupied=None if figures is None else figures.occupied,
            free=None if figures is None else figures.free_usable,
            occupancy_pct=(
                None
                if figures is None
                else occupancy_pct_floor(figures.occupied, figures.capacity)
            ),
            health=None if figures is None else figures.health,
            as_of=None if figures is None else figures.received_at,
        ),
        status,
    )


def compute_site_availability(
    settings: SiteSettings,
    zones: Sequence[ZoneConfig],
    snapshot: SnapshotView,
    current_recommendation: str | None,
    now: datetime,
) -> SiteAvailability:
    """THE single availability computation (BF-20 - BF-25, BF-31).

    ``zones`` are the site's live zones (any order; all are returned in
    ``SiteAvailability.zones`` sorted by display_order then slug, with
    disabled ones flagged ``enabled=False``). ``current_recommendation`` is
    the stickiness input (the stored ``current_zone_slug``). Never-reported
    site: ``stale=True``, ``as_of=None``, count fields None. Must be
    deterministic and side-effect free.

    ``ranked`` is always the full BF-24 candidate ranking (also while the site
    is stale, for diagnostics); ``recommended_zone_slug`` is None and
    ``top_zones`` is empty while the site is stale (BF-24 step 4).
    """
    ordered = sorted(zones, key=lambda z: (z.display_order, z.slug))
    zone_rows: list[ZoneAvailability] = []
    rankable: list[tuple[ZoneConfig, ZoneFigures, ZoneStatus]] = []
    for zone in ordered:
        figures = snapshot.zones.get(zone.slug)
        row, status = _zone_availability(settings, zone, figures, now)
        zone_rows.append(row)
        if figures is not None:
            rankable.append((zone, figures, status))

    ranked = rank_candidates(rankable)
    site = snapshot.site
    site_stale = is_site_stale(settings, site, now)
    recommended = sticky_recommendation(
        ranked,
        current_recommendation,
        settings.recommendation_margin,
        site_stale=site_stale,
    )
    return SiteAvailability(
        site_slug=settings.slug,
        stale=site_stale,
        as_of=None if site is None else site.received_at,
        age_seconds=age_seconds(site, now),
        capacity=None if site is None else site.capacity,
        occupied=None if site is None else site.occupied,
        free_usable=None if site is None else site.free_usable,
        occupancy_pct=(
            None if site is None else occupancy_pct_floor(site.occupied, site.capacity)
        ),
        health=None if site is None else site.health,
        recommended_zone_slug=recommended,
        top_zones=() if site_stale else top_two(ranked),
        ranked=ranked,
        zones=tuple(zone_rows),
    )
