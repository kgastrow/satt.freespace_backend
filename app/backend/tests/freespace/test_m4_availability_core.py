"""M4: pure availability core (BF-20 - BF-25, AT-01, AT-07, AT-08, BT-05)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any
import uuid

import pytest

from src.constants.freespace import Health, ZoneStatus
from src.services.freespace.availability import (
    compute_site_availability,
    is_site_stale,
    is_zone_stale,
    meets_pct,
    occupancy_pct_floor,
    rank_candidates,
    sticky_recommendation,
    top_two,
    zone_status,
)
from src.services.freespace.types import (
    RankedZone,
    SiteFigures,
    SiteSettings,
    SnapshotView,
    ZoneConfig,
    ZoneFigures,
)


NOW = datetime(2026, 11, 24, 5, 45, 0, tzinfo=timezone.utc)
SETTINGS = SiteSettings(
    site_id=uuid.uuid4(),
    organization_id=uuid.uuid4(),
    slug="absa-alice-lane",
    name="Alice Lane",
    time_zone="Africa/Johannesburg",
    fcm_topic="freespace-absa-alice-lane",
    managed=True,
    listed=True,
)


def zc(slug: str, **kw: Any) -> ZoneConfig:
    kw.setdefault("name", slug.upper())
    return ZoneConfig(zone_id=uuid.uuid4(), slug=slug, **kw)


def zf(
    capacity: int = 100,
    occupied: int = 50,
    *,
    free_usable: int | None = None,
    unknown: int = 0,
    health: Health = Health.OK,
    age_s: float = 0,
    slug: str = "z",
) -> ZoneFigures:
    if free_usable is None:
        free_usable = max(0, capacity - occupied - unknown)
    received = NOW - timedelta(seconds=age_s)
    return ZoneFigures(
        capacity=capacity,
        occupied=occupied,
        free_usable=free_usable,
        free_reserved=0,
        free_disabled=0,
        unknown=unknown,
        health=health,
        measured_at=received,
        received_at=received,
        zone_slug=slug,
    )


def sf(
    capacity: int = 1200,
    occupied: int = 900,
    *,
    health: Health = Health.OK,
    age_s: float = 0,
) -> SiteFigures:
    received = NOW - timedelta(seconds=age_s)
    return SiteFigures(
        capacity=capacity,
        occupied=occupied,
        free_usable=capacity - occupied,
        free_reserved=0,
        free_disabled=0,
        unknown=0,
        health=health,
        measured_at=received,
        received_at=received,
    )


def snap(site: SiteFigures | None, **zones: ZoneFigures) -> SnapshotView:
    return SnapshotView(
        site=site,
        zones=MappingProxyType(
            {slug: replace(f, zone_slug=slug) for slug, f in zones.items()}
        ),
    )


def rz(slug: str, free: int, priority: int = 100) -> RankedZone:
    return RankedZone(slug=slug, name=slug.upper(), free_usable=free, priority=priority)


# ─────────────────────────────────────────────────────────────
# BF-20: exact ratio, floor for display
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("occupied", "capacity", "floor_pct", "meets_90"),
    [
        (899, 1000, 89, False),  # 89.9 % shows 89 and is below 90
        (900, 1000, 90, True),
        (8999, 10000, 89, False),
        (9, 10, 90, True),  # 0.9 has no exact float but compares exactly
        (1081, 1200, 90, True),  # 90.083 %
        (1079, 1200, 89, False),  # 89.916 %
        (0, 10, 0, False),
        (10, 10, 100, True),
        (0, 0, None, False),  # capacity 0: undefined
    ],
)
def test_floor_and_exact_threshold(occupied, capacity, floor_pct, meets_90):
    assert occupancy_pct_floor(occupied, capacity) == floor_pct
    assert meets_pct(occupied, capacity, 90) is meets_90


def test_floor_never_shows_90_before_rule_fires():
    for capacity in range(1, 400):
        for occupied in range(capacity + 1):
            shown = occupancy_pct_floor(occupied, capacity)
            assert (shown is not None and shown >= 90) == meets_pct(
                occupied, capacity, 90
            )


# ─────────────────────────────────────────────────────────────
# BF-21: zone staleness, all five conditions
# ─────────────────────────────────────────────────────────────

ZONE = zc("b1")


@pytest.mark.parametrize(
    ("settings", "figures", "expected"),
    [
        (SETTINGS, None, True),  # never reported
        (SETTINGS, zf(age_s=0), False),
        (SETTINGS, zf(age_s=120), False),  # exactly at the limit: fresh
        (SETTINGS, zf(age_s=120.001), True),  # just over
        (SETTINGS, zf(age_s=180), True),  # AT-08: 3 min without ingest
        (SETTINGS, zf(age_s=-30), False),  # receivedAt ahead of now
        (replace(SETTINGS, stale_limit_s=30), zf(age_s=31), True),
        (SETTINGS, zf(health=Health.OFFLINE), True),
        (SETTINGS, zf(health=Health.PARTIAL), True),  # partialIsStale default
        (replace(SETTINGS, partial_is_stale=False), zf(health=Health.PARTIAL), False),
        (
            replace(SETTINGS, partial_is_stale=False),
            zf(health=Health.OFFLINE),
            True,
        ),
        (SETTINGS, zf(capacity=0, occupied=0, free_usable=0), True),
        (SETTINGS, zf(capacity=100, occupied=10, unknown=25), False),  # == 25 %
        (SETTINGS, zf(capacity=100, occupied=10, unknown=26), True),  # > 25 %
        (SETTINGS, zf(capacity=1000, occupied=10, unknown=251), True),  # 25.1 %
        (SETTINGS, zf(capacity=1000, occupied=10, unknown=250), False),
        (SETTINGS, zf(capacity=3, occupied=0, unknown=1), True),  # 33.3 %
    ],
)
def test_is_zone_stale(settings, figures, expected):
    assert is_zone_stale(settings, ZONE, figures, NOW) is expected


def test_zone_unknown_limit_is_per_zone():
    figures = zf(capacity=100, occupied=10, unknown=30)
    assert is_zone_stale(SETTINGS, zc("b1", unknown_limit_pct=25), figures, NOW)
    assert not is_zone_stale(SETTINGS, zc("b1", unknown_limit_pct=30), figures, NOW)
    assert is_zone_stale(SETTINGS, zc("b1", unknown_limit_pct=0), zf(unknown=1), NOW)


# ─────────────────────────────────────────────────────────────
# BF-22: site staleness
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("settings", "figures", "expected"),
    [
        (SETTINGS, None, True),
        (SETTINGS, sf(), False),
        (SETTINGS, sf(age_s=120), False),
        (SETTINGS, sf(age_s=121), True),
        (SETTINGS, sf(age_s=180), True),
        (SETTINGS, sf(health=Health.OFFLINE), True),
        (SETTINGS, sf(health=Health.PARTIAL), True),
        (replace(SETTINGS, partial_is_stale=False), sf(health=Health.PARTIAL), False),
        (SETTINGS, sf(capacity=0, occupied=0), True),
    ],
)
def test_is_site_stale(settings, figures, expected):
    assert is_site_stale(settings, figures, NOW) is expected


# ─────────────────────────────────────────────────────────────
# BF-23: zone status
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("zone", "figures", "expected"),
    [
        (ZONE, None, ZoneStatus.UNKNOWN),
        (ZONE, zf(age_s=500), ZoneStatus.UNKNOWN),
        (ZONE, zf(health=Health.OFFLINE), ZoneStatus.UNKNOWN),
        (ZONE, zf(capacity=0, occupied=0, free_usable=0), ZoneStatus.UNKNOWN),
        (ZONE, zf(100, 0), ZoneStatus.AVAILABLE),
        (ZONE, zf(1000, 799), ZoneStatus.AVAILABLE),  # 79.9 %
        (ZONE, zf(1000, 800), ZoneStatus.LIMITED),  # exactly 80 %
        (ZONE, zf(1000, 949), ZoneStatus.LIMITED),  # 94.9 %
        (ZONE, zf(1000, 950), ZoneStatus.FULL),  # exactly 95 %
        (ZONE, zf(100, 100), ZoneStatus.FULL),
        # fullMinFree: 4 usable free < 5 at only 50 % occupancy
        (ZONE, zf(100, 50, free_usable=4), ZoneStatus.FULL),
        (ZONE, zf(100, 50, free_usable=5), ZoneStatus.AVAILABLE),  # not < 5
        (zc("b1", full_min_free=0), zf(100, 94, free_usable=0), ZoneStatus.LIMITED),
        (zc("b1", full_min_free=10), zf(20, 5, free_usable=9), ZoneStatus.FULL),
        (zc("b1", limited_pct=50, full_pct=60), zf(100, 55), ZoneStatus.LIMITED),
        (zc("b1", limited_pct=50, full_pct=60), zf(100, 60), ZoneStatus.FULL),
        (zc("b1", limited_pct=50, full_pct=60), zf(100, 49), ZoneStatus.AVAILABLE),
        # tiny zone: 3 bays, 2 occupied, 1 free -> FULL by fullMinFree
        (ZONE, zf(3, 2), ZoneStatus.FULL),
    ],
)
def test_zone_status(zone, figures, expected):
    assert zone_status(SETTINGS, zone, figures, NOW) == expected


# ─────────────────────────────────────────────────────────────
# BF-24 steps 1-2: candidates and ranking
# ─────────────────────────────────────────────────────────────


def test_rank_filters_non_candidates():
    rows = [
        (zc("a"), zf(free_usable=50), ZoneStatus.AVAILABLE),
        (zc("b"), zf(free_usable=60), ZoneStatus.LIMITED),
        (zc("c"), zf(free_usable=70), ZoneStatus.FULL),
        (zc("d"), zf(free_usable=80), ZoneStatus.UNKNOWN),
        (zc("e", enabled=False), zf(free_usable=90), ZoneStatus.AVAILABLE),
        (zc("f", recommendable=False), zf(free_usable=99), ZoneStatus.AVAILABLE),
    ]
    assert [r.slug for r in rank_candidates(rows)] == ["b", "a"]


def test_rank_order_free_desc_priority_asc_slug_asc():
    rows = [
        (zc("b3", priority=100), zf(free_usable=40), ZoneStatus.AVAILABLE),
        (zc("b2", priority=100), zf(free_usable=40), ZoneStatus.AVAILABLE),
        (zc("b1", priority=200), zf(free_usable=40), ZoneStatus.AVAILABLE),
        (zc("b4", priority=50), zf(free_usable=40), ZoneStatus.AVAILABLE),
        (zc("b5", priority=999), zf(free_usable=41), ZoneStatus.LIMITED),
        (zc("b0", priority=1), zf(free_usable=10), ZoneStatus.AVAILABLE),
    ]
    ranked = rank_candidates(rows)
    assert [r.slug for r in ranked] == ["b5", "b4", "b2", "b3", "b1", "b0"]
    assert ranked[0] == RankedZone(slug="b5", name="B5", free_usable=41, priority=999)


def test_rank_is_order_independent():
    rows = [
        (zc(s, priority=p), zf(free_usable=f), ZoneStatus.AVAILABLE)
        for s, p, f in [("a", 1, 5), ("b", 1, 5), ("c", 0, 5), ("d", 9, 6)]
    ]
    assert rank_candidates(rows) == rank_candidates(list(reversed(rows)))


def test_rank_empty():
    assert rank_candidates([]) == ()


# ─────────────────────────────────────────────────────────────
# BF-24 steps 3-4: stickiness
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ranked", "current", "margin", "stale", "expected"),
    [
        ([], None, 10, False, None),  # no candidates
        ([], "b1", 10, False, None),
        ([rz("b1", 100)], "b1", 10, True, None),  # site stale
        ([rz("b1", 100)], None, 10, False, "b1"),  # no current: top
        ([rz("b2", 110), rz("b1", 100)], "b1", 10, False, "b1"),  # exactly margin
        ([rz("b2", 111), rz("b1", 100)], "b1", 10, False, "b2"),  # margin + 1
        ([rz("b2", 104), rz("b1", 100)], "b1", 10, False, "b1"),  # BT-05
        ([rz("b2", 200), rz("b1", 100)], "b1", 0, False, "b2"),  # margin 0
        ([rz("b2", 100), rz("b1", 100)], "b1", 0, False, "b1"),  # tie, margin 0
        ([rz("b2", 100)], "b1", 10, False, "b2"),  # current not a candidate
        ([rz("b2", 100)], "gone", 10, False, "b2"),  # current deleted
        # current is third; top beats it by more than margin even if #2 doesn't
        ([rz("a", 130), rz("b", 115), rz("c", 110)], "c", 10, False, "a"),
        ([rz("a", 120), rz("b", 115), rz("c", 110)], "c", 10, False, "c"),
    ],
)
def test_sticky_recommendation(ranked, current, margin, stale, expected):
    assert sticky_recommendation(ranked, current, margin, site_stale=stale) == expected


@pytest.mark.parametrize(
    ("ranked", "expected"),
    [
        ([], ()),
        ([rz("a", 1)], ("a",)),
        ([rz("a", 3), rz("b", 2)], ("a", "b")),
        ([rz("a", 3), rz("b", 2), rz("c", 1)], ("a", "b")),
    ],
)
def test_top_two(ranked, expected):
    assert top_two(ranked) == expected


# ─────────────────────────────────────────────────────────────
# compute_site_availability
# ─────────────────────────────────────────────────────────────

FOUR_ZONES = [zc(f"b{i}", name=f"Basement {i}", display_order=i) for i in (1, 2, 3, 4)]


def test_compute_basic_shape_and_order():
    zones = list(reversed(FOUR_ZONES)) + [zc("b0", display_order=1)]
    view = snap(
        sf(1200, 1081, age_s=14),
        b1=zf(450, 432, free_usable=16),
        b2=zf(400, 300),
        b3=zf(300, 120),
        b0=zf(50, 10),
    )
    result = compute_site_availability(SETTINGS, zones, view, None, NOW)
    assert result.site_slug == "absa-alice-lane"
    assert result.stale is False
    assert result.age_seconds == 14
    assert result.as_of == NOW - timedelta(seconds=14)
    assert (result.capacity, result.occupied, result.free_usable) == (1200, 1081, 119)
    assert result.occupancy_pct == 90
    assert [z.slug for z in result.zones] == ["b0", "b1", "b2", "b3", "b4"]
    statuses = {z.slug: z.status for z in result.zones}
    assert statuses == {
        "b0": ZoneStatus.AVAILABLE,
        "b1": ZoneStatus.FULL,
        "b2": ZoneStatus.AVAILABLE,
        "b3": ZoneStatus.AVAILABLE,
        "b4": ZoneStatus.UNKNOWN,  # never reported
    }
    b4 = result.zones[-1]
    assert (b4.capacity, b4.free, b4.occupancy_pct, b4.as_of, b4.stale) == (
        None,
        None,
        None,
        None,
        True,
    )
    assert [r.slug for r in result.ranked] == ["b3", "b2", "b0"]
    assert result.recommended_zone_slug == "b3"
    assert result.top_zones == ("b3", "b2")


def test_compute_never_reported_site():
    result = compute_site_availability(SETTINGS, FOUR_ZONES, snap(None), "b1", NOW)
    assert result.stale is True
    assert result.as_of is None and result.age_seconds is None
    assert result.capacity is None and result.occupancy_pct is None
    assert result.health is None
    assert result.recommended_zone_slug is None
    assert result.top_zones == () and result.ranked == ()
    assert all(z.status == ZoneStatus.UNKNOWN for z in result.zones)


def test_compute_site_stale_nulls_recommendation_but_keeps_zone_rows():
    view = snap(sf(age_s=200), b1=zf(100, 10), b2=zf(100, 20))
    result = compute_site_availability(SETTINGS, FOUR_ZONES[:2], view, "b1", NOW)
    assert result.stale is True
    assert result.recommended_zone_slug is None
    assert result.top_zones == ()
    assert [r.slug for r in result.ranked] == ["b1", "b2"]  # diagnostic


def test_compute_site_offline_is_stale_even_with_fresh_zones():
    view = snap(sf(health=Health.OFFLINE), b1=zf(100, 10))
    result = compute_site_availability(SETTINGS, FOUR_ZONES[:1], view, None, NOW)
    assert result.stale is True
    assert result.recommended_zone_slug is None


def test_compute_capacity_zero_site_and_zone():
    view = snap(
        sf(capacity=0, occupied=0), b1=zf(capacity=0, occupied=0, free_usable=0)
    )
    result = compute_site_availability(SETTINGS, FOUR_ZONES[:1], view, None, NOW)
    assert result.stale is True
    assert result.occupancy_pct is None
    assert result.zones[0].status == ZoneStatus.UNKNOWN
    assert result.zones[0].occupancy_pct is None
    assert result.zones[0].capacity == 0


def test_compute_disabled_zone_listed_but_never_recommended():
    zones = [zc("b1", enabled=False, display_order=1), zc("b2", display_order=2)]
    view = snap(sf(), b1=zf(500, 0), b2=zf(100, 50))
    result = compute_site_availability(SETTINGS, zones, view, "b1", NOW)
    assert [(z.slug, z.enabled) for z in result.zones] == [
        ("b1", False),
        ("b2", True),
    ]
    assert result.recommended_zone_slug == "b2"


def test_compute_uses_site_margin():
    zones = FOUR_ZONES[:2]
    view = snap(sf(), b1=zf(200, 100), b2=zf(200, 80))  # free 100 vs 120
    assert (
        compute_site_availability(
            SETTINGS, zones, view, "b1", NOW
        ).recommended_zone_slug
        == "b2"
    )
    wide = replace(SETTINGS, recommendation_margin=20)
    assert (
        compute_site_availability(wide, zones, view, "b1", NOW).recommended_zone_slug
        == "b1"
    )


def test_compute_is_deterministic():
    view = snap(sf(), b1=zf(100, 10), b2=zf(100, 10), b3=zf(100, 10))
    first = compute_site_availability(SETTINGS, FOUR_ZONES, view, None, NOW)
    for _ in range(5):
        again = compute_site_availability(
            SETTINGS, list(reversed(FOUR_ZONES)), view, None, NOW
        )
        assert again == first
    assert first.recommended_zone_slug == "b1"  # tie broken by zoneId


# ─────────────────────────────────────────────────────────────
# Acceptance
# ─────────────────────────────────────────────────────────────


def test_at01_site_at_75_percent_served():
    view = snap(sf(1200, 900), b1=zf(450, 340), b4=zf(400, 300))
    zones = [FOUR_ZONES[0], FOUR_ZONES[3]]
    result = compute_site_availability(SETTINGS, zones, view, None, NOW)
    assert result.stale is False
    assert result.occupancy_pct == 75
    assert not meets_pct(
        result.occupied or 0, result.capacity or 0, SETTINGS.trigger_pct
    )
    assert result.recommended_zone_slug == "b1"  # 110 free vs 100


def test_at07_recommends_b4_when_b1_full():
    view = snap(sf(1000, 850), b1=zf(500, 490), b4=zf(400, 220))  # 98 %, 55 %
    zones = [FOUR_ZONES[0], FOUR_ZONES[3]]
    result = compute_site_availability(SETTINGS, zones, view, "b1", NOW)
    assert result.occupancy_pct == 85
    assert {z.slug: z.status for z in result.zones} == {
        "b1": ZoneStatus.FULL,
        "b4": ZoneStatus.AVAILABLE,
    }
    assert result.zones[0].occupancy_pct == 98
    assert result.zones[1].occupancy_pct == 55
    assert result.recommended_zone_slug == "b4"
    assert result.top_zones == ("b4",)


def test_at08_no_ingest_for_three_minutes():
    view = snap(sf(age_s=180), b1=zf(100, 10, age_s=180), b2=zf(100, 20, age_s=180))
    result = compute_site_availability(SETTINGS, FOUR_ZONES[:2], view, "b1", NOW)
    assert result.stale is True
    assert all(z.status == ZoneStatus.UNKNOWN for z in result.zones)
    assert result.recommended_zone_slug is None
    assert result.age_seconds == 180


@pytest.mark.parametrize("bad", [Health.OFFLINE, Health.PARTIAL])
def test_at08_zone_offline_never_recommended(bad):
    # b1 has by far the most free bays but is OFFLINE; current points at it.
    view = snap(sf(), b1=zf(500, 0, health=bad), b2=zf(100, 50), b3=zf(100, 60))
    result = compute_site_availability(SETTINGS, FOUR_ZONES[:3], view, "b1", NOW)
    assert result.stale is False
    assert result.zones[0].status == ZoneStatus.UNKNOWN
    assert result.recommended_zone_slug == "b2"
    assert "b1" not in result.top_zones
    assert "b1" not in [r.slug for r in result.ranked]


def test_at08_recommendation_never_unknown_exhaustive():
    """Property: across many combinations the recommendation is a fresh,
    enabled, recommendable, non-FULL zone, or None."""
    healths = [Health.OK, Health.PARTIAL, Health.OFFLINE]
    ages = [0, 120, 121]
    combos = 0
    for h1 in healths:
        for a1 in ages:
            for h2 in healths:
                for occ2 in (10, 96):
                    for current in (None, "b1", "b2"):
                        view = snap(
                            sf(),
                            b1=zf(100, 5, health=h1, age_s=a1),
                            b2=zf(100, occ2, health=h2),
                        )
                        result = compute_site_availability(
                            SETTINGS, FOUR_ZONES[:2], view, current, NOW
                        )
                        statuses = {z.slug: z.status for z in result.zones}
                        rec = result.recommended_zone_slug
                        if rec is not None:
                            assert statuses[rec] not in (
                                ZoneStatus.UNKNOWN,
                                ZoneStatus.FULL,
                            )
                        for slug in result.top_zones:
                            assert statuses[slug] != ZoneStatus.UNKNOWN
                        combos += 1
    assert combos == 3 * 3 * 3 * 2 * 3


def test_bt05_alternating_100_104_never_flips():
    zones = FOUR_ZONES[:2]
    current: str | None = None
    seen: list[str | None] = []
    for i in range(20):
        free_b1, free_b2 = (100, 104) if i % 2 == 0 else (104, 100)
        view = snap(
            sf(),
            b1=zf(300, 300 - free_b1),
            b2=zf(300, 300 - free_b2),
        )
        result = compute_site_availability(SETTINGS, zones, view, current, NOW)
        current = result.recommended_zone_slug
        seen.append(current)
    assert seen[0] == "b2"  # first pick: most free
    assert set(seen) == {"b2"}


def test_bt05_large_swing_does_flip():
    zones = FOUR_ZONES[:2]
    view = snap(sf(), b1=zf(300, 200), b2=zf(300, 189))  # 100 vs 111
    assert (
        compute_site_availability(
            SETTINGS, zones, view, "b1", NOW
        ).recommended_zone_slug
        == "b2"
    )
