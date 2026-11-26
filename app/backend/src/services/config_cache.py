"""
Config caching service for dynamic configuration.
Caches SystemConfig values in Redis with short TTL for performance.
"""

from dataclasses import dataclass
import json
from typing import Optional

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.cache import cache_service


# Cache key and TTL constants
REQUEST_LOGGING_CONFIG_KEY = "config:request_logging"
CONFIG_CACHE_TTL = 60  # 60 seconds


@dataclass
class RequestLoggingConfig:
    """Request logging configuration."""

    enabled: bool
    db_enabled: bool
    max_body_size: int
    retention_days: int

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "db_enabled": self.db_enabled,
            "max_body_size": self.max_body_size,
            "retention_days": self.retention_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RequestLoggingConfig":
        return cls(
            enabled=data.get("enabled", False),
            db_enabled=data.get("db_enabled", False),
            max_body_size=data.get("max_body_size", 10240),
            retention_days=data.get("retention_days", 30),
        )

    @classmethod
    def from_settings(cls) -> "RequestLoggingConfig":
        """Create config from static settings (fallback)."""
        return cls(
            enabled=settings.REQUEST_LOGGING_ENABLED,
            db_enabled=settings.REQUEST_LOGGING_DB_ENABLED,
            max_body_size=settings.REQUEST_LOGGING_MAX_BODY_SIZE,
            retention_days=30,  # Default retention
        )


async def get_request_logging_config() -> RequestLoggingConfig:
    """
    Get request logging configuration.
    Tries Redis cache first, then database, falls back to static settings.
    """
    # Try Redis cache first.
    #
    # The guard is cache_service._is_available(), not cache_service._enabled.
    # _enabled is the configuration switch and says nothing about whether the
    # backend is reachable; _is_available() also honours the post-error
    # cooldown and re-probes once it expires. Getting this wrong is expensive
    # here: this function runs on the request-logging path for every request,
    # so a cache that never came back would mean a database round trip per
    # request, forever.
    try:
        if await cache_service._is_available() and cache_service._redis:
            cached = await cache_service._redis.get(REQUEST_LOGGING_CONFIG_KEY)
            if cached:
                data = json.loads(cached)
                return RequestLoggingConfig.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to get config from cache: {e}")

    # Try to load from database and cache it
    config = await _load_config_from_db()
    if config:
        await _cache_config(config)
        return config

    # Fallback to static settings
    return RequestLoggingConfig.from_settings()


async def _load_config_from_db() -> Optional[RequestLoggingConfig]:
    """Load request logging config from SystemConfig database."""
    try:
        from src.crud.system_config import get_system_config_by_key
        from src.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            # Load each config key
            enabled_config = await get_system_config_by_key(
                session, "request_logging.enabled"
            )
            db_enabled_config = await get_system_config_by_key(
                session, "request_logging.db_enabled"
            )
            max_body_size_config = await get_system_config_by_key(
                session, "request_logging.max_body_size"
            )
            retention_days_config = await get_system_config_by_key(
                session, "request_logs.retention_days"
            )

            # Parse values with defaults
            enabled = (
                bool(enabled_config.value)
                if enabled_config and enabled_config.value is not None
                else settings.REQUEST_LOGGING_ENABLED
            )
            db_enabled = (
                bool(db_enabled_config.value)
                if db_enabled_config and db_enabled_config.value is not None
                else settings.REQUEST_LOGGING_DB_ENABLED
            )
            max_body_size = (
                int(max_body_size_config.value)
                if max_body_size_config and max_body_size_config.value is not None
                else settings.REQUEST_LOGGING_MAX_BODY_SIZE
            )
            retention_days = (
                int(retention_days_config.value)
                if retention_days_config and retention_days_config.value is not None
                else 30
            )

            return RequestLoggingConfig(
                enabled=enabled,
                db_enabled=db_enabled,
                max_body_size=max_body_size,
                retention_days=retention_days,
            )

    except Exception as e:
        logger.warning(f"Failed to load config from database: {e}")
        return None

    return None


async def _cache_config(config: RequestLoggingConfig) -> None:
    """Cache configuration in Redis."""
    try:
        if await cache_service._is_available() and cache_service._redis:
            await cache_service._redis.setex(
                REQUEST_LOGGING_CONFIG_KEY,
                CONFIG_CACHE_TTL,
                json.dumps(config.to_dict()),
            )
    except Exception as e:
        logger.warning(f"Failed to cache config: {e}")


async def invalidate_request_logging_config() -> None:
    """Invalidate cached request logging config (call after updates)."""
    try:
        if await cache_service._is_available() and cache_service._redis:
            await cache_service._redis.delete(REQUEST_LOGGING_CONFIG_KEY)
            logger.debug("Request logging config cache invalidated")
    except Exception as e:
        logger.warning(f"Failed to invalidate config cache: {e}")


async def update_request_logging_config(
    enabled: bool,
    db_enabled: bool,
    max_body_size: int,
    retention_days: int,
    user_id: str,
) -> RequestLoggingConfig:
    """
    Update request logging configuration in database and invalidate cache.
    """
    from src.crud.system_config import update_system_config
    from src.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        # Update each config key (update_system_config commits internally)
        await update_system_config(
            session=session,
            key="request_logging.enabled",
            value=enabled,
            description="Enable request/response logging",
            updated_by_user_id=user_id,
        )
        await update_system_config(
            session=session,
            key="request_logging.db_enabled",
            value=db_enabled,
            description="Store request logs in database",
            updated_by_user_id=user_id,
        )
        await update_system_config(
            session=session,
            key="request_logging.max_body_size",
            value=max_body_size,
            description="Maximum request/response body size to capture (bytes)",
            updated_by_user_id=user_id,
        )
        await update_system_config(
            session=session,
            key="request_logs.retention_days",
            value=retention_days,
            description="Number of days to retain request logs",
            updated_by_user_id=user_id,
        )

        # Invalidate cache so next request gets fresh config
        await invalidate_request_logging_config()

        return RequestLoggingConfig(
            enabled=enabled,
            db_enabled=db_enabled,
            max_body_size=max_body_size,
            retention_days=retention_days,
        )
