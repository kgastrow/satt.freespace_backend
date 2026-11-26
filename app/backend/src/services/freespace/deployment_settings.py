"""
Typed deployment-level Freespace settings (BF-37, BF-63, BF-73, D13).

Stored as SystemConfig keys (seeded from ``scripts/seed_data/system_config.yaml``
by the shared seeder) and read through a 60 s Redis cache. Every key has a
safe default: a missing, malformed or out-of-range value falls back to the
default with a warning, never an exception, so a bad admin edit cannot stop
the engine.

Request-log retention reuses the template's existing
``request_logs.retention_days`` key rather than adding a second one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    DEPLOYMENT_DEFAULTS,
    DEPLOYMENT_SETTINGS_CACHE_TTL_S,
    REDIS_DEPLOYMENT_SETTINGS_KEY,
    LimitScope,
)
from src.logger.logger import Logger as logger
from src.models.system_config import SystemConfig
from src.services.freespace.redis_client import get_redis


# Dataclass field -> SystemConfig key
SYSTEM_CONFIG_KEYS: dict[str, str] = {
    "limit_scope": "freespace.limit_scope",
    "cooldown_s": "freespace.cooldown_s",
    "daily_cap": "freespace.daily_cap",
    "time_zone": "freespace.time_zone",
    "device_ceiling": "freespace.device_ceiling",
    "retention_devices_days": "freespace.retention.devices_days",
    "retention_send_history_days": "freespace.retention.send_history_days",
    "retention_events_days": "freespace.retention.events_days",
    "retention_occupancy_history_days": "freespace.retention.occupancy_history_days",
    "retention_request_logs_days": "request_logs.retention_days",
}


@dataclass(frozen=True)
class DeploymentSettings:
    """Deployment-wide Freespace settings. See ``DEPLOYMENT_DEFAULTS``."""

    limit_scope: LimitScope = LimitScope.DEVICE
    cooldown_s: int = 1800  # DEVICE scope cooldown (BF-63)
    daily_cap: int = 2  # DEVICE scope daily cap (BF-63)
    time_zone: str = "Africa/Johannesburg"  # "today" for DEVICE scope
    device_ceiling: int = 50000  # BF-37
    retention_devices_days: int = 90  # BF-73
    retention_send_history_days: int = 35
    retention_events_days: int = 365
    retention_occupancy_history_days: int = 180
    retention_request_logs_days: int = 30

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["limit_scope"] = self.limit_scope.value
        return data


def _int_value(name: str, raw: Any, *, minimum: int) -> int:
    default = int(DEPLOYMENT_DEFAULTS[name])
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            f"Freespace setting {name}: invalid value {raw!r}, using {default}"
        )
        return default
    if value < minimum:
        logger.warning(
            f"Freespace setting {name}: {value} < {minimum}, using {default}"
        )
        return default
    return value


def parse_deployment_settings(raw: dict[str, Any]) -> DeploymentSettings:
    """Build settings from ``{field name: raw SystemConfig value}``. Missing or
    invalid entries fall back to defaults. Pure; exposed for tests."""
    scope_raw = raw.get("limit_scope")
    try:
        limit_scope = (
            LimitScope(str(scope_raw).strip().upper())
            if scope_raw is not None
            else LimitScope(DEPLOYMENT_DEFAULTS["limit_scope"])
        )
    except ValueError:
        logger.warning(f"Freespace setting limit_scope: invalid value {scope_raw!r}")
        limit_scope = LimitScope(DEPLOYMENT_DEFAULTS["limit_scope"])

    tz_raw = raw.get("time_zone")
    time_zone = str(DEPLOYMENT_DEFAULTS["time_zone"])
    if tz_raw is not None and str(tz_raw).strip():
        try:
            ZoneInfo(str(tz_raw).strip())
            time_zone = str(tz_raw).strip()
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning(f"Freespace setting time_zone: unknown zone {tz_raw!r}")

    return DeploymentSettings(
        limit_scope=limit_scope,
        cooldown_s=_int_value("cooldown_s", raw.get("cooldown_s"), minimum=0),
        daily_cap=_int_value("daily_cap", raw.get("daily_cap"), minimum=0),
        time_zone=time_zone,
        device_ceiling=_int_value(
            "device_ceiling", raw.get("device_ceiling"), minimum=1
        ),
        retention_devices_days=_int_value(
            "retention_devices_days", raw.get("retention_devices_days"), minimum=1
        ),
        retention_send_history_days=_int_value(
            "retention_send_history_days",
            raw.get("retention_send_history_days"),
            minimum=1,
        ),
        retention_events_days=_int_value(
            "retention_events_days", raw.get("retention_events_days"), minimum=1
        ),
        retention_occupancy_history_days=_int_value(
            "retention_occupancy_history_days",
            raw.get("retention_occupancy_history_days"),
            minimum=1,
        ),
        retention_request_logs_days=_int_value(
            "retention_request_logs_days",
            raw.get("retention_request_logs_days"),
            minimum=1,
        ),
    )


async def _read_cache() -> DeploymentSettings | None:
    redis = get_redis()
    if redis is None:
        return None
    try:
        cached = await redis.get(REDIS_DEPLOYMENT_SETTINGS_KEY)
    except Exception as exc:  # cache is optional: fall through to the DB
        logger.warning(f"Freespace deployment settings: cache read failed: {exc}")
        return None
    if not cached:
        return None
    try:
        return parse_deployment_settings(json.loads(cached))
    except (TypeError, ValueError):
        return None


async def _write_cache(value: DeploymentSettings) -> None:
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.setex(
            REDIS_DEPLOYMENT_SETTINGS_KEY,
            DEPLOYMENT_SETTINGS_CACHE_TTL_S,
            json.dumps(value.to_dict()),
        )
    except Exception as exc:  # cache is optional
        logger.warning(f"Freespace deployment settings: cache write failed: {exc}")


async def load_deployment_settings_from_db(session: AsyncSession) -> DeploymentSettings:
    """Read the SystemConfig keys (no cache)."""
    key_to_field = {key: name for name, key in SYSTEM_CONFIG_KEYS.items()}
    result = await session.execute(
        select(SystemConfig.key, SystemConfig.value).where(
            SystemConfig.key.in_(list(key_to_field))
        )
    )
    raw = {key_to_field[key]: value for key, value in result.all()}
    return parse_deployment_settings(raw)


async def get_deployment_settings(
    session: AsyncSession | None = None,
) -> DeploymentSettings:
    """Cached deployment settings (Redis, 60 s). On a miss reads SystemConfig
    with ``session`` (or a fresh ``AsyncSessionLocal`` session when None). A
    database failure without a cached value returns the defaults."""
    cached = await _read_cache()
    if cached is not None:
        return cached
    try:
        if session is not None:
            value = await load_deployment_settings_from_db(session)
        else:
            from src.database import AsyncSessionLocal

            async with AsyncSessionLocal() as own_session:
                value = await load_deployment_settings_from_db(own_session)
    except Exception as exc:  # never stop the engine over settings
        logger.error(
            f"Freespace deployment settings: DB read failed, using defaults: {exc}"
        )
        return DeploymentSettings()
    await _write_cache(value)
    return value


async def invalidate_deployment_settings_cache() -> None:
    """Drop the cached value (call after editing any of the keys)."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.delete(REDIS_DEPLOYMENT_SETTINGS_KEY)
    except Exception as exc:  # cache is optional
        logger.warning(f"Freespace deployment settings: cache delete failed: {exc}")
