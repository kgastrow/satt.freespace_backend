"""
Pure validation of site settings (BF-71, §10.1) and zone settings (§10.2).

An invalid value or combination is REFUSED, never clamped. No I/O: the admin
API (M1) calls these on the merged "current + requested" values; the engine
loader may reuse them.

Errors carry the response ``detail_code`` the API must answer with (422).
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Final
from zoneinfo import ZoneInfo

from src.constants.freespace import (
    FCM_TOPIC_PATTERN,
    SITE_SETTING_BOUNDS,
    ChangeDirection,
)


# BF-71: staleLimitS >= 2 x ParkIT's post interval (60 s) = 120 s.
STALE_LIMIT_MIN_S: Final = SITE_SETTING_BOUNDS["stale_limit_s"][0]
MAX_NOTIFICATION_RULES: Final = 20

_TIME_RE: Final = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_TOPIC_RE: Final = re.compile(FCM_TOPIC_PATTERN)

SITE_CONFIG_FIELDS: Final[tuple[str, ...]] = (
    "managed",
    "listed",
    "time_zone",
    "trigger_pct",
    "reset_pct",
    "change_points",
    "change_direction",
    "stabilisation_s",
    "recommendation_margin",
    "stale_limit_s",
    "partial_is_stale",
    "recovery_push",
    "zone_advisory",
    "zone_reset_gap",
    "notification_window",
    "cooldown_s",
    "daily_cap",
    "push_expiry_s",
)

ZONE_SETTING_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "display_order",
    "enabled",
    "recommendable",
    "preferred",
    "priority",
    "limited_pct",
    "full_pct",
    "full_min_free",
    "unknown_limit_pct",
    "advisory_pct",
    "note",
)


class SiteConfigError(ValueError):
    """Invalid site setting. ``detail_code`` is the response code (422)."""

    def __init__(self, message: str, detail_code: str = "site.invalid_settings"):
        super().__init__(message)
        self.detail_code = detail_code


class ZoneSettingsError(ValueError):
    """Invalid zone setting (422 ``zone.invalid_settings``)."""

    def __init__(self, message: str, detail_code: str = "zone.invalid_settings"):
        super().__init__(message)
        self.detail_code = detail_code


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int_in_range(
    values: Mapping[str, Any],
    name: str,
    low: int | None,
    high: int | None,
    error: type[ValueError],
) -> int:
    value = values.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise error(f"{name} must be an integer")
    if low is not None and value < low:
        raise error(f"{name} must be at least {low}")
    if high is not None and value > high:
        raise error(f"{name} must be at most {high}")
    return int(value)


def _bounded(values: Mapping[str, Any], name: str, error: type[ValueError]) -> int:
    """``_int_in_range`` with the bounds from ``SITE_SETTING_BOUNDS``."""
    low, high = SITE_SETTING_BOUNDS[name]
    return _int_in_range(values, name, low, high, error)


def validate_time_zone(name: Any) -> str:
    """A valid IANA time zone name, else ``site.invalid_time_zone``."""
    if not isinstance(name, str) or not name or len(name) > 64:
        raise SiteConfigError(
            "time_zone must be an IANA name", "site.invalid_time_zone"
        )
    try:
        ZoneInfo(name)
    except Exception as exc:  # ZoneInfoNotFoundError, ValueError, OSError
        raise SiteConfigError(
            f"Unknown time zone: {name}", "site.invalid_time_zone"
        ) from exc
    return name


def validate_fcm_topic(topic: Any) -> str:
    if not isinstance(topic, str) or not _TOPIC_RE.match(topic):
        raise SiteConfigError(
            "fcm_topic must match [a-zA-Z0-9-_.~%]+", "site.invalid_topic"
        )
    return topic


def normalise_notification_window(value: Any) -> list[dict[str, Any]]:
    """Validate and normalise a notification window (BF-71).

    A list of ``{weekdays, start, end}`` in site local time; weekdays ISO 1-7,
    ``start < end`` (no overnight span). An empty list means "any time".
    """
    code = "site.invalid_notification_window"
    if not isinstance(value, list):
        raise SiteConfigError("notification_window must be a list", code)
    if len(value) > MAX_NOTIFICATION_RULES:
        raise SiteConfigError(
            f"notification_window has at most {MAX_NOTIFICATION_RULES} rules", code
        )
    rules: list[dict[str, Any]] = []
    for index, rule in enumerate(value):
        if not isinstance(rule, Mapping):
            raise SiteConfigError(f"rule {index} must be an object", code)
        weekdays = rule.get("weekdays")
        if (
            not isinstance(weekdays, list)
            or not weekdays
            or not all(_is_int(day) and 1 <= day <= 7 for day in weekdays)
        ):
            raise SiteConfigError(
                f"rule {index}: weekdays must be a non-empty list of 1-7", code
            )
        start, end = rule.get("start"), rule.get("end")
        if (
            not isinstance(start, str)
            or not isinstance(end, str)
            or not _TIME_RE.match(start)
            or not _TIME_RE.match(end)
        ):
            raise SiteConfigError(f"rule {index}: start/end must be HH:MM", code)
        if start >= end:
            raise SiteConfigError(
                f"rule {index}: start must be before end (no overnight span)", code
            )
        rules.append({"weekdays": sorted(set(weekdays)), "start": start, "end": end})
    return rules


def validate_site_config(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete merged site settings; return the normalised dict
    (``SITE_CONFIG_FIELDS`` keys). Raises ``SiteConfigError``. Never clamps."""
    err = SiteConfigError
    out: dict[str, Any] = {}
    for name in (
        "managed",
        "listed",
        "partial_is_stale",
        "recovery_push",
        "zone_advisory",
    ):
        if not isinstance(values.get(name), bool):
            raise err(f"{name} must be a boolean")
        out[name] = values[name]

    out["time_zone"] = validate_time_zone(values.get("time_zone"))

    out["trigger_pct"] = _bounded(values, "trigger_pct", err)
    out["reset_pct"] = _int_in_range(values, "reset_pct", 0, None, err)
    if out["reset_pct"] >= out["trigger_pct"]:
        raise err("reset_pct must be below trigger_pct")
    out["change_points"] = _bounded(values, "change_points", err)

    direction = values.get("change_direction")
    if direction not in {d.value for d in ChangeDirection}:
        raise err("change_direction must be RISING or BOTH")
    out["change_direction"] = str(direction)

    out["stabilisation_s"] = _bounded(values, "stabilisation_s", err)
    out["recommendation_margin"] = _bounded(values, "recommendation_margin", err)
    out["stale_limit_s"] = _bounded(values, "stale_limit_s", err)
    out["zone_reset_gap"] = _bounded(values, "zone_reset_gap", err)
    out["cooldown_s"] = _bounded(values, "cooldown_s", err)
    out["daily_cap"] = _bounded(values, "daily_cap", err)
    out["push_expiry_s"] = _bounded(values, "push_expiry_s", err)
    out["notification_window"] = normalise_notification_window(
        values.get("notification_window")
    )
    return out


def validate_zone_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete merged zone settings (§10.2); return normalised
    values. Raises ``ZoneSettingsError``. Never clamps."""
    err = ZoneSettingsError
    out: dict[str, Any] = {}

    name = values.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        raise err("name must be 1-255 characters")
    out["name"] = name.strip()

    for flag in ("enabled", "recommendable", "preferred"):
        if not isinstance(values.get(flag), bool):
            raise err(f"{flag} must be a boolean")
        out[flag] = values[flag]

    out["display_order"] = _int_in_range(values, "display_order", 0, 100000, err)
    out["priority"] = _int_in_range(values, "priority", 0, 100000, err)
    out["limited_pct"] = _int_in_range(values, "limited_pct", 1, 100, err)
    out["full_pct"] = _int_in_range(values, "full_pct", 1, 100, err)
    if out["limited_pct"] > out["full_pct"]:
        raise err("limited_pct must not exceed full_pct")
    out["full_min_free"] = _int_in_range(values, "full_min_free", 0, None, err)
    out["unknown_limit_pct"] = _int_in_range(values, "unknown_limit_pct", 0, 100, err)

    advisory = values.get("advisory_pct")
    if advisory is not None:
        advisory = _int_in_range(values, "advisory_pct", 1, 100, err)
    out["advisory_pct"] = advisory

    note = values.get("note", "")
    if not isinstance(note, str) or len(note) > 2000:
        raise err("note must be text of at most 2000 characters")
    out["note"] = note
    return out
