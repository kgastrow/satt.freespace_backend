"""
Per-phone checks (BF-58 - BF-60, BF-63). OWNER: M7.

Checks run in ``DEVICE_CHECK_ORDER``; the first failure is the device's
reason:

1. ``notificationsEnabled``                       -> OPTED_OUT
2. inside the site's notification window (site local time; empty = any
   time)                                          -> OUTSIDE_WINDOW
3. device's last advisory fingerprint (this site, this engine cycle) differs
                                                  -> DUPLICATE
4. at least ``cooldown`` since the last advisory in the limit scope
                                                  -> COOLDOWN
5. fewer than ``dailyCap`` advisories "today" in the limit scope
                                                  -> DAILY_CAP

``TEST`` bypasses every check and is never counted; ``RECOVERY`` is counted
(BF-60). Scope (BF-63): ``DEVICE`` = deployment cooldown / cap, every site,
"today" in the deployment time zone; ``DEVICE_PER_SITE`` = the site's own
cooldown / cap, per (device, site), "today" in the site time zone.

Everything is evaluated per CHUNK with two aggregate queries
(``crud/freespace_push_send.py``), never one query per device.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    DEFAULT_TIME_ZONE,
    AdvisoryType,
    DeviceOutcome,
    LimitScope,
)
from src.crud.freespace_push_send import LimitUsage, last_fingerprints, limit_usage
from src.services.freespace.clock import ensure_utc
from src.services.freespace.deployment_settings import DeploymentSettings
from src.services.freespace.types import (
    NotificationWindowRule,
    SiteSettings,
    is_within_notification_window,
)


@dataclass(frozen=True)
class LimitPolicy:
    """Resolved cooldown / cap and their scope for one site's fan-out."""

    scope: LimitScope
    cooldown_s: int
    daily_cap: int
    time_zone: str  # zone in which "today" is measured


@dataclass(frozen=True)
class DeviceCheckInput:
    device_id: uuid.UUID
    notifications_enabled: bool


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def resolve_limit_policy(
    deployment: DeploymentSettings, site: SiteSettings
) -> LimitPolicy:
    """BF-63: which cooldown / cap / time zone apply."""
    if deployment.limit_scope == LimitScope.DEVICE_PER_SITE:
        return LimitPolicy(
            scope=LimitScope.DEVICE_PER_SITE,
            cooldown_s=site.cooldown_s,
            daily_cap=site.daily_cap,
            time_zone=site.time_zone,
        )
    return LimitPolicy(
        scope=LimitScope.DEVICE,
        cooldown_s=deployment.cooldown_s,
        daily_cap=deployment.daily_cap,
        time_zone=deployment.time_zone,
    )


def local_day_start(now: datetime, time_zone: str) -> datetime:
    """UTC instant of local midnight of ``now``'s day in ``time_zone``."""
    local = ensure_utc(now).astimezone(_zone(time_zone))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def inside_window(
    rules: tuple[NotificationWindowRule, ...], time_zone: str, now: datetime
) -> bool:
    """BF-58 check 2 in SITE local time."""
    return is_within_notification_window(
        rules, ensure_utc(now).astimezone(_zone(time_zone))
    )


def first_failed_check(
    *,
    notifications_enabled: bool,
    in_window: bool,
    last_fingerprint: str | None,
    fingerprint: str,
    last_at: datetime | None,
    today_count: int,
    policy: LimitPolicy,
    now: datetime,
) -> DeviceOutcome | None:
    """Pure BF-58 decision for one device; None = passes every check."""
    if not notifications_enabled:
        return DeviceOutcome.OPTED_OUT
    if not in_window:
        return DeviceOutcome.OUTSIDE_WINDOW
    if last_fingerprint is not None and last_fingerprint == fingerprint:
        return DeviceOutcome.DUPLICATE
    if last_at is not None and (now - last_at).total_seconds() < policy.cooldown_s:
        return DeviceOutcome.COOLDOWN
    if today_count >= policy.daily_cap:
        return DeviceOutcome.DAILY_CAP
    return None


async def evaluate_device_checks(
    session: AsyncSession,
    devices: Sequence[DeviceCheckInput],
    *,
    site: SiteSettings,
    advisory_type: AdvisoryType | str,
    fingerprint: str,
    cycle_id: uuid.UUID | None,
    event_id: uuid.UUID,
    policy: LimitPolicy,
    now: datetime,
) -> dict[uuid.UUID, DeviceOutcome | None]:
    """BF-58 for a whole chunk. ``{device_id: failing reason | None}``."""
    if not devices:
        return {}
    now = ensure_utc(now)
    if AdvisoryType(advisory_type) == AdvisoryType.TEST:
        return {d.device_id: None for d in devices}  # BF-60: bypass everything

    in_window = inside_window(site.notification_window, site.time_zone, now)
    day_start = local_day_start(now, policy.time_zone)
    since = min(day_start, now - timedelta(seconds=max(0, policy.cooldown_s)))
    # Only devices that get past checks 1-2 need the history queries.
    to_query = [d.device_id for d in devices if d.notifications_enabled and in_window]

    usage: Mapping[uuid.UUID, LimitUsage] = {}
    fingerprints: Mapping[uuid.UUID, str] = {}
    if to_query:
        usage = await limit_usage(
            session,
            to_query,
            site_id=(
                site.site_id if policy.scope == LimitScope.DEVICE_PER_SITE else None
            ),
            since=since,
            day_start=day_start,
            exclude_event_id=event_id,
        )
        fingerprints = await last_fingerprints(
            session,
            to_query,
            site_id=site.site_id,
            cycle_id=cycle_id,
            since=day_start,
            exclude_event_id=event_id,
        )

    result: dict[uuid.UUID, DeviceOutcome | None] = {}
    for device in devices:
        device_usage = usage.get(device.device_id)
        result[device.device_id] = first_failed_check(
            notifications_enabled=device.notifications_enabled,
            in_window=in_window,
            last_fingerprint=fingerprints.get(device.device_id),
            fingerprint=fingerprint,
            last_at=device_usage.last_at if device_usage else None,
            today_count=device_usage.today_count if device_usage else 0,
            policy=policy,
            now=now,
        )
    return result
