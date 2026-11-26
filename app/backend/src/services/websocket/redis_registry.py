"""
Redis-based WebSocket connection registry for cross-worker connection tracking.
Uses Redis hashes to store connection metadata and enable lookups by user/org.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import redis.asyncio as redis

from src.logger.logger import Logger
from src.services.cache import cache_service


class RedisRegistry:
    """
    Redis-based registry for WebSocket connections across workers.

    Uses Redis hashes to track connections with the following structure:
    - ws:conn:{connection_id} -> connection metadata hash
    - ws:user:{user_id} -> set of connection_ids
    - ws:org:{org_id} -> set of connection_ids
    - ws:worker:{worker_id} -> set of connection_ids (for cleanup)
    """

    # Key prefixes
    CONN_PREFIX = "ws:conn:"
    USER_PREFIX = "ws:user:"
    ORG_PREFIX = "ws:org:"
    WORKER_PREFIX = "ws:worker:"

    # Connection TTL (2 hours) - connections should refresh before this
    CONNECTION_TTL = 7200

    def __init__(self) -> None:
        self._redis: Optional[redis.Redis] = None

    def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis client from cache service."""
        if cache_service._redis is not None:
            return cache_service._redis
        return None

    async def _is_available(self) -> bool:
        """Check if Redis is available."""
        redis_client = self._get_redis()
        if redis_client is None:
            return False
        try:
            await redis_client.ping()
            return True
        except redis.ConnectionError:
            return False

    async def register_connection(
        self,
        connection_id: str,
        user_id: UUID,
        organization_id: UUID,
        worker_id: str,
    ) -> bool:
        """
        Register a WebSocket connection in Redis.

        Args:
            connection_id: Unique connection identifier
            user_id: ID of the connected user
            organization_id: ID of the user's organization
            worker_id: ID of the worker process handling this connection

        Returns:
            True if registration succeeded, False otherwise
        """
        if not await self._is_available():
            Logger.warning("Redis unavailable, skipping connection registration")
            return False

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            user_id_str = str(user_id)
            org_id_str = str(organization_id)
            connected_at = datetime.now(timezone.utc).isoformat()

            conn_key = f"{self.CONN_PREFIX}{connection_id}"
            user_key = f"{self.USER_PREFIX}{user_id_str}"
            org_key = f"{self.ORG_PREFIX}{org_id_str}"
            worker_key = f"{self.WORKER_PREFIX}{worker_id}"

            # Store connection metadata as hash
            conn_data = {
                "connection_id": connection_id,
                "user_id": user_id_str,
                "organization_id": org_id_str,
                "worker_id": worker_id,
                "connected_at": connected_at,
            }

            pipe = redis_client.pipeline()
            pipe.hset(conn_key, mapping=conn_data)
            pipe.expire(conn_key, self.CONNECTION_TTL)
            pipe.sadd(user_key, connection_id)
            pipe.expire(user_key, self.CONNECTION_TTL)
            pipe.sadd(org_key, connection_id)
            pipe.expire(org_key, self.CONNECTION_TTL)
            pipe.sadd(worker_key, connection_id)
            pipe.expire(worker_key, self.CONNECTION_TTL)
            await pipe.execute()

            Logger.debug(
                "Registered connection in Redis: connection_id=%s user_id=%s org_id=%s worker_id=%s",
                connection_id,
                user_id_str,
                org_id_str,
                worker_id,
            )
            return True

        except redis.RedisError as e:
            Logger.warning("Failed to register connection in Redis: %s", str(e))
            return False

    async def unregister_connection(self, connection_id: str) -> bool:
        """
        Remove a WebSocket connection from Redis.

        Args:
            connection_id: The connection ID to remove

        Returns:
            True if unregistration succeeded, False otherwise
        """
        if not await self._is_available():
            Logger.warning("Redis unavailable, skipping connection unregistration")
            return False

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            conn_key = f"{self.CONN_PREFIX}{connection_id}"

            # Get connection metadata first
            conn_data = await redis_client.hgetall(conn_key)  # type: ignore[misc]
            if not conn_data:
                Logger.debug("Connection not found in Redis: %s", connection_id)
                return True

            user_id_str = conn_data.get("user_id", "")
            org_id_str = conn_data.get("organization_id", "")
            worker_id = conn_data.get("worker_id", "")

            user_key = f"{self.USER_PREFIX}{user_id_str}"
            org_key = f"{self.ORG_PREFIX}{org_id_str}"
            worker_key = f"{self.WORKER_PREFIX}{worker_id}"

            pipe = redis_client.pipeline()
            pipe.delete(conn_key)
            pipe.srem(user_key, connection_id)
            pipe.srem(org_key, connection_id)
            pipe.srem(worker_key, connection_id)
            await pipe.execute()

            Logger.debug(
                "Unregistered connection from Redis: connection_id=%s",
                connection_id,
            )
            return True

        except redis.RedisError as e:
            Logger.warning("Failed to unregister connection from Redis: %s", str(e))
            return False

    async def get_connection(self, connection_id: str) -> Optional[dict]:
        """
        Get connection metadata by connection ID.

        Args:
            connection_id: The connection ID to look up

        Returns:
            Connection metadata dict or None if not found
        """
        if not await self._is_available():
            return None

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            conn_key = f"{self.CONN_PREFIX}{connection_id}"
            conn_data = await redis_client.hgetall(conn_key)  # type: ignore[misc]
            if not conn_data:
                return None
            return dict(conn_data)
        except redis.RedisError as e:
            Logger.warning("Failed to get connection from Redis: %s", str(e))
            return None

    async def get_user_connections(self, user_id: UUID) -> list[dict]:
        """
        Get all connection metadata for a specific user.

        Args:
            user_id: The user ID to look up

        Returns:
            List of connection metadata dicts
        """
        if not await self._is_available():
            return []

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            user_key = f"{self.USER_PREFIX}{str(user_id)}"
            connection_ids = await redis_client.smembers(user_key)  # type: ignore[misc]

            connections = []
            for conn_id in connection_ids:
                conn_data = await self.get_connection(conn_id)
                if conn_data:
                    connections.append(conn_data)

            return connections

        except redis.RedisError as e:
            Logger.warning("Failed to get user connections from Redis: %s", str(e))
            return []

    async def get_org_connections(self, organization_id: UUID) -> list[dict]:
        """
        Get all connection metadata for a specific organization.

        Args:
            organization_id: The organization ID to look up

        Returns:
            List of connection metadata dicts
        """
        if not await self._is_available():
            return []

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            org_key = f"{self.ORG_PREFIX}{str(organization_id)}"
            connection_ids = await redis_client.smembers(org_key)  # type: ignore[misc]

            connections = []
            for conn_id in connection_ids:
                conn_data = await self.get_connection(conn_id)
                if conn_data:
                    connections.append(conn_data)

            return connections

        except redis.RedisError as e:
            Logger.warning("Failed to get org connections from Redis: %s", str(e))
            return []

    async def get_worker_connections(self, worker_id: str) -> list[str]:
        """
        Get all connection IDs for a specific worker.

        Args:
            worker_id: The worker ID to look up

        Returns:
            List of connection IDs
        """
        if not await self._is_available():
            return []

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            worker_key = f"{self.WORKER_PREFIX}{worker_id}"
            connection_ids = await redis_client.smembers(worker_key)  # type: ignore[misc]
            return list(connection_ids)
        except redis.RedisError as e:
            Logger.warning("Failed to get worker connections from Redis: %s", str(e))
            return []

    async def refresh_connection(self, connection_id: str) -> bool:
        """
        Refresh the TTL for a connection (heartbeat).

        Args:
            connection_id: The connection ID to refresh

        Returns:
            True if refresh succeeded, False otherwise
        """
        if not await self._is_available():
            return False

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            conn_key = f"{self.CONN_PREFIX}{connection_id}"
            conn_data = await redis_client.hgetall(conn_key)  # type: ignore[misc]
            if not conn_data:
                return False

            user_id_str = conn_data.get("user_id", "")
            org_id_str = conn_data.get("organization_id", "")
            worker_id = conn_data.get("worker_id", "")

            user_key = f"{self.USER_PREFIX}{user_id_str}"
            org_key = f"{self.ORG_PREFIX}{org_id_str}"
            worker_key = f"{self.WORKER_PREFIX}{worker_id}"

            pipe = redis_client.pipeline()
            pipe.expire(conn_key, self.CONNECTION_TTL)
            pipe.expire(user_key, self.CONNECTION_TTL)
            pipe.expire(org_key, self.CONNECTION_TTL)
            pipe.expire(worker_key, self.CONNECTION_TTL)
            await pipe.execute()

            return True

        except redis.RedisError as e:
            Logger.warning("Failed to refresh connection in Redis: %s", str(e))
            return False

    async def cleanup_worker_connections(self, worker_id: str) -> int:
        """
        Remove all connections for a worker (on worker shutdown).

        Args:
            worker_id: The worker ID to clean up

        Returns:
            Number of connections removed
        """
        if not await self._is_available():
            return 0

        connection_ids = await self.get_worker_connections(worker_id)
        removed = 0
        for conn_id in connection_ids:
            if await self.unregister_connection(conn_id):
                removed += 1

        return removed


# Singleton instance
redis_registry = RedisRegistry()
