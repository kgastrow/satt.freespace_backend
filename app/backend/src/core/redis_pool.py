"""
Centralized Redis connection pool manager.

Provides a single shared connection pool for all services that need Redis,
eliminating pool fragmentation that can exhaust connection limits.

Architecture:
- One pool for DB 0 (cache, rate limiting, brute force, job stats)
- One pool for DB 1 / ARQ DB (queue health monitoring)
- One dedicated connection for pub/sub (subscribers hold connections
  open indefinitely and must not compete with request-serving operations)
"""

from typing import Optional

import redis.asyncio as redis

from src.core.config import settings
from src.logger.logger import Logger as logger


class RedisPoolManager:
    """
    Manages shared Redis connection pools for the application.

    Instead of each service creating its own pool (which fragments
    connections and can exhaust Redis limits), all services receive
    their Redis client from this central manager.
    """

    def __init__(self) -> None:
        # DB 0 pool — shared by cache, rate limiter, brute force, job stats
        self._pool_db0: Optional[redis.ConnectionPool] = None
        self._client_db0: Optional[redis.Redis] = None

        # DB 1 pool — shared by queue health (ARQ task queue has its own via arq)
        self._pool_db1: Optional[redis.ConnectionPool] = None
        self._client_db1: Optional[redis.Redis] = None

        # Dedicated pub/sub connection — not pooled, one persistent connection
        self._pubsub_client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Create all pools and verify connectivity."""

        # --- DB 0 pool (general) ---
        try:
            self._pool_db0 = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=settings.REDIS_POOL_SIZE,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._client_db0 = redis.Redis(connection_pool=self._pool_db0)
            await self._client_db0.ping()
            logger.info(
                f"Redis DB 0 pool created "
                f"(max_connections={settings.REDIS_POOL_SIZE})"
            )
        except redis.ConnectionError as e:
            logger.warning(f"Redis DB 0 connection failed: {e}")
            self._client_db0 = None

        # --- DB 1 pool (ARQ monitoring) ---
        try:
            self._pool_db1 = redis.ConnectionPool.from_url(
                settings.ARQ_REDIS_URL,
                decode_responses=True,
                max_connections=5,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._client_db1 = redis.Redis(connection_pool=self._pool_db1)
            await self._client_db1.ping()
            logger.info("Redis DB 1 pool created (max_connections=5)")
        except redis.ConnectionError as e:
            logger.warning(f"Redis DB 1 connection failed: {e}")
            self._client_db1 = None

        # --- Dedicated pub/sub connection ---
        try:
            self._pubsub_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=5,
            )
            await self._pubsub_client.ping()
            logger.info("Redis pub/sub dedicated connection created")
        except redis.ConnectionError as e:
            logger.warning(f"Redis pub/sub connection failed: {e}")
            self._pubsub_client = None

    async def disconnect(self) -> None:
        """Close all pools and connections."""
        if self._pubsub_client:
            await self._pubsub_client.aclose()
            logger.info("Redis pub/sub connection closed")

        if self._pool_db1:
            await self._pool_db1.disconnect()
            logger.info("Redis DB 1 pool closed")

        if self._pool_db0:
            await self._pool_db0.disconnect()
            logger.info("Redis DB 0 pool closed")

    @property
    def client_db0(self) -> Optional[redis.Redis]:
        """Shared Redis client for DB 0 (cache, rate limiting, etc.)."""
        return self._client_db0

    @property
    def client_db1(self) -> Optional[redis.Redis]:
        """Shared Redis client for DB 1 (ARQ queue monitoring)."""
        return self._client_db1

    @property
    def pubsub_client(self) -> Optional[redis.Redis]:
        """Dedicated Redis client for pub/sub (not pooled)."""
        return self._pubsub_client


# Singleton instance
redis_pool_manager = RedisPoolManager()
