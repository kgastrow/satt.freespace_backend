"""M1: BF-71 validation table (pure) and zone settings (§10.2)."""

from __future__ import annotations

import pytest

from src.constants.freespace import (
    SITE_DEFAULTS,
    ZONE_DEFAULTS,
    default_notification_window,
)
from src.services.freespace.site_config import (
    SITE_CONFIG_FIELDS,
    SiteConfigError,
    ZoneSettingsError,
    validate_site_config,
    validate_zone_settings,
)


def base() -> dict:
    values = dict(SITE_DEFAULTS)
    values["time_zone"] = "Africa/Johannesburg"
    values["notification_window"] = default_notification_window()
    return values


def zone_base() -> dict:
    values = dict(ZONE_DEFAULTS)
    values["name"] = "Basement 1"
    return values


def test_defaults_valid_and_complete():
    out = validate_site_config(base())
    assert set(out) == set(SITE_CONFIG_FIELDS)
    assert out["notification_window"] == [
        {"weekdays": [1, 2, 3, 4, 5], "start": "06:00", "end": "10:00"}
    ]


VALID = [
    {"trigger_pct": 1, "reset_pct": 0},
    {"trigger_pct": 100},
    {"reset_pct": 89},
    {"change_points": 1},
    {"change_points": 50},
    {"change_direction": "BOTH"},
    {"stabilisation_s": 0},
    {"stabilisation_s": 3600},
    {"recommendation_margin": 0},
    {"stale_limit_s": 120},
    {"stale_limit_s": 100000},
    {"zone_reset_gap": 1},
    {"zone_reset_gap": 50},
    {"push_expiry_s": 60},
    {"push_expiry_s": 86400},
    {"cooldown_s": 0, "daily_cap": 0},
    {"time_zone": "UTC"},
    {"notification_window": []},
    {"notification_window": [{"weekdays": [7, 6], "start": "00:00", "end": "23:59"}]},
    {
        "notification_window": [
            {"weekdays": [1], "start": "06:00", "end": "10:00"},
            {"weekdays": [1], "start": "16:00", "end": "18:00"},
        ]
    },
    {"managed": True, "listed": True, "recovery_push": True, "zone_advisory": True},
    {"partial_is_stale": False},
]

INVALID = [
    ({"trigger_pct": 0}, "site.invalid_settings"),
    ({"trigger_pct": 101}, "site.invalid_settings"),
    ({"reset_pct": 90}, "site.invalid_settings"),  # == trigger
    ({"reset_pct": 95}, "site.invalid_settings"),  # > trigger
    ({"reset_pct": -1}, "site.invalid_settings"),
    ({"trigger_pct": 70}, "site.invalid_settings"),  # reset 80 now >= trigger
    ({"change_points": 0}, "site.invalid_settings"),
    ({"change_points": 51}, "site.invalid_settings"),
    ({"change_direction": "FALLING"}, "site.invalid_settings"),
    ({"change_direction": "rising"}, "site.invalid_settings"),
    ({"stabilisation_s": -1}, "site.invalid_settings"),
    ({"stabilisation_s": 3601}, "site.invalid_settings"),
    ({"recommendation_margin": -1}, "site.invalid_settings"),
    ({"stale_limit_s": 119}, "site.invalid_settings"),
    ({"stale_limit_s": 0}, "site.invalid_settings"),
    ({"zone_reset_gap": 0}, "site.invalid_settings"),
    ({"zone_reset_gap": 51}, "site.invalid_settings"),
    ({"push_expiry_s": 59}, "site.invalid_settings"),
    ({"push_expiry_s": 86401}, "site.invalid_settings"),
    ({"cooldown_s": -1}, "site.invalid_settings"),
    ({"daily_cap": -1}, "site.invalid_settings"),
    ({"managed": "yes"}, "site.invalid_settings"),
    ({"trigger_pct": True}, "site.invalid_settings"),
    ({"trigger_pct": 90.5}, "site.invalid_settings"),
    ({"time_zone": "Not/AZone"}, "site.invalid_time_zone"),
    ({"time_zone": ""}, "site.invalid_time_zone"),
    ({"time_zone": "../etc/passwd"}, "site.invalid_time_zone"),
    ({"notification_window": "always"}, "site.invalid_notification_window"),
    (
        {"notification_window": [{"weekdays": [1], "start": "10:00", "end": "06:00"}]},
        "site.invalid_notification_window",
    ),  # overnight / start > end
    (
        {"notification_window": [{"weekdays": [1], "start": "22:00", "end": "02:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [1], "start": "06:00", "end": "06:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [], "start": "06:00", "end": "10:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [0], "start": "06:00", "end": "10:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [8], "start": "06:00", "end": "10:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [1], "start": "6:00", "end": "10:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [1], "start": "06:00", "end": "24:00"}]},
        "site.invalid_notification_window",
    ),
    (
        {"notification_window": [{"weekdays": [1], "start": "06:00"}]},
        "site.invalid_notification_window",
    ),
]


@pytest.mark.parametrize("override", VALID)
def test_valid_combinations(override):
    values = base() | override
    if (
        "trigger_pct" in override
        and "reset_pct" not in override
        and override["trigger_pct"] <= 80
    ):
        values["reset_pct"] = 0
    assert validate_site_config(values)


@pytest.mark.parametrize("override,code", INVALID)
def test_invalid_is_refused_never_clamped(override, code):
    with pytest.raises(SiteConfigError) as exc:
        validate_site_config(base() | override)
    assert exc.value.detail_code == code


def test_window_is_normalised():
    out = validate_site_config(
        base()
        | {
            "notification_window": [
                {"weekdays": [3, 1, 3], "start": "06:00", "end": "07:00"}
            ]
        }
    )
    assert out["notification_window"][0]["weekdays"] == [1, 3]


class TestZoneSettings:
    def test_defaults_valid(self):
        out = validate_zone_settings(zone_base())
        assert out["advisory_pct"] is None and out["full_pct"] == 95

    @pytest.mark.parametrize(
        "override",
        [
            {"limited_pct": 95, "full_pct": 95},
            {"advisory_pct": 100},
            {"advisory_pct": 1},
            {"full_min_free": 0},
            {"unknown_limit_pct": 0},
            {"priority": 0},
        ],
    )
    def test_valid(self, override):
        assert validate_zone_settings(zone_base() | override)

    @pytest.mark.parametrize(
        "override",
        [
            {"name": ""},
            {"name": "x" * 256},
            {"limited_pct": 96},
            {"limited_pct": 0},
            {"full_pct": 101},
            {"full_min_free": -1},
            {"unknown_limit_pct": 101},
            {"advisory_pct": 0},
            {"advisory_pct": 101},
            {"priority": -1},
            {"display_order": -1},
            {"enabled": "true"},
            {"note": "n" * 2001},
        ],
    )
    def test_invalid(self, override):
        with pytest.raises(ZoneSettingsError) as exc:
            validate_zone_settings(zone_base() | override)
        assert exc.value.detail_code == "zone.invalid_settings"
