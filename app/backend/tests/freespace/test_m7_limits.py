"""M7 per-phone check primitives (BF-58, BF-63), pure."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import uuid

import pytest

from src.constants.freespace import DEVICE_CHECK_ORDER, DeviceOutcome, LimitScope
from src.services.freespace.deployment_settings import DeploymentSettings
from src.services.freespace.limits import (
    LimitPolicy,
    first_failed_check,
    inside_window,
    local_day_start,
    resolve_limit_policy,
)
from src.services.freespace.types import NotificationWindowRule, SiteSettings


NOW = datetime(2026, 11, 24, 5, 45, tzinfo=timezone.utc)  # Tue 07:45 SAST
POLICY = LimitPolicy(LimitScope.DEVICE, 1800, 2, "Africa/Johannesburg")


def _check(**overrides):
    values = dict(
        notifications_enabled=True,
        in_window=True,
        last_fingerprint=None,
        fingerprint="f",
        last_at=None,
        today_count=0,
        policy=POLICY,
        now=NOW,
    )
    values.update(overrides)
    return first_failed_check(**values)


def test_passes_when_nothing_fails():
    assert _check() is None


def test_first_failure_wins_in_spec_order():
    failing = dict(
        notifications_enabled=False,
        in_window=False,
        last_fingerprint="f",
        last_at=NOW - timedelta(minutes=1),
        today_count=5,
    )
    keys = [
        "notifications_enabled",
        "in_window",
        "last_fingerprint",
        "last_at",
        "today_count",
    ]
    passing = dict(
        notifications_enabled=True,
        in_window=True,
        last_fingerprint=None,
        last_at=None,
        today_count=0,
    )
    for index, expected in enumerate(DEVICE_CHECK_ORDER):
        values = {
            k: (passing[k] if i < index else failing[k]) for i, k in enumerate(keys)
        }
        assert _check(**values) == expected


def test_cooldown_boundary():
    assert _check(last_at=NOW - timedelta(seconds=1799)) == DeviceOutcome.COOLDOWN
    assert _check(last_at=NOW - timedelta(seconds=1800)) is None


def test_daily_cap_boundary():
    assert _check(today_count=1) is None
    assert _check(today_count=2) == DeviceOutcome.DAILY_CAP
    zero_cap = LimitPolicy(LimitScope.DEVICE, 0, 0, "UTC")
    assert _check(policy=zero_cap) == DeviceOutcome.DAILY_CAP


def test_local_day_start():
    assert local_day_start(NOW, "Africa/Johannesburg") == datetime(
        2026, 11, 23, 22, 0, tzinfo=timezone.utc
    )
    assert local_day_start(NOW, "UTC") == datetime(
        2026, 11, 24, 0, 0, tzinfo=timezone.utc
    )


def test_window_in_site_local_time():
    rules = (NotificationWindowRule(frozenset({1, 2, 3, 4, 5}), time(6), time(10)),)
    assert inside_window(rules, "Africa/Johannesburg", NOW)  # 07:45 SAST
    assert not inside_window(rules, "UTC", NOW - timedelta(hours=1))  # 04:45 UTC
    assert not inside_window(
        rules, "Africa/Johannesburg", NOW + timedelta(hours=2, minutes=15)
    )
    assert inside_window((), "UTC", NOW)


def _site(**kw):
    return SiteSettings(
        site_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        slug="s",
        name="S",
        time_zone="Europe/London",
        fcm_topic="t",
        managed=True,
        listed=True,
        cooldown_s=600,
        daily_cap=5,
        **kw,
    )


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (
            LimitScope.DEVICE,
            LimitPolicy(LimitScope.DEVICE, 1800, 2, "Africa/Johannesburg"),
        ),
        (
            LimitScope.DEVICE_PER_SITE,
            LimitPolicy(LimitScope.DEVICE_PER_SITE, 600, 5, "Europe/London"),
        ),
    ],
)
def test_resolve_limit_policy(scope, expected):
    assert (
        resolve_limit_policy(DeploymentSettings(limit_scope=scope), _site()) == expected
    )
