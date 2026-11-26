"""Foundation: typed deployment settings from SystemConfig (D13, BF-63, BF-73)."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.constants.freespace import (
    DEPLOYMENT_DEFAULTS,
    REDIS_DEPLOYMENT_SETTINGS_KEY,
    LimitScope,
)
from src.models.system_config import SystemConfig
from src.services.freespace import redis_client
from src.services.freespace.deployment_settings import (
    SYSTEM_CONFIG_KEYS,
    DeploymentSettings,
    get_deployment_settings,
    invalidate_deployment_settings_cache,
    parse_deployment_settings,
)


SEED = (
    Path(__file__).resolve().parents[2] / "scripts" / "seed_data" / "system_config.yaml"
)


async def _set(session, key: str, value) -> None:
    session.add(SystemConfig(key=key, value=value))
    await session.commit()


def test_defaults_match_constants():
    assert DeploymentSettings().to_dict() == DEPLOYMENT_DEFAULTS
    assert DeploymentSettings().retention_devices_days == 90
    assert DeploymentSettings().retention_send_history_days == 35
    assert DeploymentSettings().retention_events_days == 365
    assert DeploymentSettings().retention_occupancy_history_days == 180
    assert DeploymentSettings().retention_request_logs_days == 30


def test_seed_yaml_has_every_key_with_default_values():
    entries = {e["key"]: e["value"] for e in yaml.safe_load(SEED.read_text())}
    for field_name, key in SYSTEM_CONFIG_KEYS.items():
        assert key in entries, f"{key} missing from system_config.yaml"
    parsed = parse_deployment_settings(
        {name: entries[key] for name, key in SYSTEM_CONFIG_KEYS.items()}
    )
    assert parsed == DeploymentSettings()


class TestParse:
    def test_valid_values(self):
        parsed = parse_deployment_settings(
            {
                "limit_scope": "device_per_site",
                "cooldown_s": "600",
                "daily_cap": 5,
                "time_zone": "Europe/London",
                "device_ceiling": "10",
            }
        )
        assert parsed.limit_scope is LimitScope.DEVICE_PER_SITE
        assert parsed.cooldown_s == 600
        assert parsed.daily_cap == 5
        assert parsed.time_zone == "Europe/London"
        assert parsed.device_ceiling == 10

    def test_invalid_values_fall_back(self):
        parsed = parse_deployment_settings(
            {
                "limit_scope": "EVERYWHERE",
                "cooldown_s": "soon",
                "daily_cap": -1,
                "time_zone": "Mars/Olympus",
                "device_ceiling": 0,
                "retention_events_days": None,
            }
        )
        assert parsed == DeploymentSettings()

    def test_zero_cooldown_and_cap_allowed(self):
        parsed = parse_deployment_settings({"cooldown_s": "0", "daily_cap": "0"})
        assert parsed.cooldown_s == 0 and parsed.daily_cap == 0


class TestGetDeploymentSettings:
    async def test_no_rows_gives_defaults(self, async_session):
        assert await get_deployment_settings(async_session) == DeploymentSettings()

    async def test_reads_system_config(self, async_session):
        await _set(async_session, "freespace.limit_scope", "DEVICE_PER_SITE")
        await _set(async_session, "freespace.daily_cap", "3")
        await _set(async_session, "request_logs.retention_days", "14")
        value = await get_deployment_settings(async_session)
        assert value.limit_scope is LimitScope.DEVICE_PER_SITE
        assert value.daily_cap == 3
        assert value.retention_request_logs_days == 14
        assert value.cooldown_s == 1800

    async def test_cached_for_ttl_then_invalidated(self, async_session, fs_redis):
        await _set(async_session, "freespace.daily_cap", "3")
        assert (await get_deployment_settings(async_session)).daily_cap == 3
        assert 0 < await fs_redis.ttl(REDIS_DEPLOYMENT_SETTINGS_KEY) <= 60

        row = await async_session.get(SystemConfig, (await _row_id(async_session)))
        row.value = "4"
        await async_session.commit()
        assert (await get_deployment_settings(async_session)).daily_cap == 3  # cached

        await invalidate_deployment_settings_cache()
        assert (await get_deployment_settings(async_session)).daily_cap == 4

    async def test_works_without_redis(self, async_session):
        redis_client.set_redis_override(None)
        await _set(async_session, "freespace.device_ceiling", "7")
        assert (await get_deployment_settings(async_session)).device_ceiling == 7

    async def test_db_failure_returns_defaults(self):
        class Broken:
            async def execute(self, *args, **kwargs):
                raise RuntimeError("db down")

        assert await get_deployment_settings(Broken()) == DeploymentSettings()  # type: ignore[arg-type]


async def _row_id(session):
    from sqlalchemy import select

    result = await session.execute(
        select(SystemConfig.id).where(SystemConfig.key == "freespace.daily_cap")
    )
    return result.scalar_one()
