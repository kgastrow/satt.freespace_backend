"""
WebSocket Connection Manager for tracking local worker connections.
Manages WebSocket connection lifecycle and message delivery for a single worker process.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from src.logger.logger import Logger


@dataclass
class ConnectionInfo:
    """Information about an active WebSocket connection."""

    websocket: WebSocket
    connection_id: str
    user_id: UUID
    organization_id: UUID
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConnectionManager:
    """
    Manages WebSocket connections for a single worker process.

    Tracks active connections in memory and provides methods for:
    - Connection lifecycle (connect/disconnect)
    - Lookup by user_id or organization_id
    - Message delivery to individual or multiple connections
    """

    def __init__(self) -> None:
        self._connections: dict[str, ConnectionInfo] = {}
        self._user_connections: dict[UUID, set[str]] = {}
        self._org_connections: dict[UUID, set[str]] = {}

    @property
    def connection_count(self) -> int:
        """Return the total number of active connections."""
        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
        connection_id: str,
        user_id: UUID,
        organization_id: UUID,
    ) -> None:
        """
        Register a new WebSocket connection.

        Args:
            websocket: The FastAPI WebSocket instance
            connection_id: Unique identifier for this connection
            user_id: ID of the connected user
            organization_id: ID of the user's organization
        """
        connection_info = ConnectionInfo(
            websocket=websocket,
            connection_id=connection_id,
            user_id=user_id,
            organization_id=organization_id,
        )

        self._connections[connection_id] = connection_info

        if user_id not in self._user_connections:
            self._user_connections[user_id] = set()
        self._user_connections[user_id].add(connection_id)

        if organization_id not in self._org_connections:
            self._org_connections[organization_id] = set()
        self._org_connections[organization_id].add(connection_id)

        Logger.info(
            "WebSocket connected: connection_id=%s user_id=%s org_id=%s",
            connection_id,
            user_id,
            organization_id,
        )

    async def disconnect(self, connection_id: str) -> None:
        """
        Remove a WebSocket connection and clean up references.

        Args:
            connection_id: The connection ID to remove
        """
        connection_info = self._connections.pop(connection_id, None)
        if connection_info is None:
            Logger.warning(
                "Attempted to disconnect unknown connection: %s", connection_id
            )
            return

        user_id = connection_info.user_id
        organization_id = connection_info.organization_id

        if user_id in self._user_connections:
            self._user_connections[user_id].discard(connection_id)
            if not self._user_connections[user_id]:
                del self._user_connections[user_id]

        if organization_id in self._org_connections:
            self._org_connections[organization_id].discard(connection_id)
            if not self._org_connections[organization_id]:
                del self._org_connections[organization_id]

        Logger.info(
            "WebSocket disconnected: connection_id=%s user_id=%s org_id=%s",
            connection_id,
            user_id,
            organization_id,
        )

    def get_connections_for_user(self, user_id: UUID) -> list[WebSocket]:
        """
        Get all WebSocket connections for a specific user.

        Args:
            user_id: The user ID to look up

        Returns:
            List of WebSocket instances for the user
        """
        connection_ids = self._user_connections.get(user_id, set())
        return [
            self._connections[cid].websocket
            for cid in connection_ids
            if cid in self._connections
        ]

    def get_connections_for_org(self, organization_id: UUID) -> list[WebSocket]:
        """
        Get all WebSocket connections for a specific organization.

        Args:
            organization_id: The organization ID to look up

        Returns:
            List of WebSocket instances for the organization
        """
        connection_ids = self._org_connections.get(organization_id, set())
        return [
            self._connections[cid].websocket
            for cid in connection_ids
            if cid in self._connections
        ]

    def get_all_connections(self) -> list[WebSocket]:
        """
        Get all active WebSocket connections.

        Returns:
            List of all active WebSocket instances
        """
        return [info.websocket for info in self._connections.values()]

    def get_connection(self, connection_id: str) -> WebSocket | None:
        """
        Get a specific WebSocket connection by ID.

        Args:
            connection_id: The connection ID to look up

        Returns:
            The WebSocket instance or None if not found
        """
        connection_info = self._connections.get(connection_id)
        return connection_info.websocket if connection_info else None

    async def send_to_connection(
        self, connection_id: str, message: dict[str, Any]
    ) -> bool:
        """
        Send a JSON message to a specific connection.

        Args:
            connection_id: The target connection ID
            message: The message to send (will be JSON serialized)

        Returns:
            True if message was sent, False if connection not found or send failed
        """
        connection_info = self._connections.get(connection_id)
        if connection_info is None:
            Logger.warning("Cannot send to unknown connection: %s", connection_id)
            return False

        try:
            await connection_info.websocket.send_json(message)
            return True
        except Exception as e:
            Logger.error(
                "Failed to send message to connection %s: %s",
                connection_id,
                str(e),
            )
            return False

    async def broadcast_to_connections(
        self, connection_ids: list[str], message: dict[str, Any]
    ) -> int:
        """
        Send a JSON message to multiple connections.

        Args:
            connection_ids: List of target connection IDs
            message: The message to send (will be JSON serialized)

        Returns:
            Number of connections that successfully received the message
        """
        successful = 0
        for connection_id in connection_ids:
            if await self.send_to_connection(connection_id, message):
                successful += 1
        return successful

    async def send_to_user(self, user_id: UUID, message: dict[str, Any]) -> int:
        """
        Send a JSON message to all connections for a specific user.

        Args:
            user_id: The target user ID
            message: The message to send

        Returns:
            Number of connections that successfully received the message
        """
        connection_ids = list(self._user_connections.get(user_id, set()))
        return await self.broadcast_to_connections(connection_ids, message)

    async def send_to_org(self, organization_id: UUID, message: dict[str, Any]) -> int:
        """
        Send a JSON message to all connections for a specific organization.

        Args:
            organization_id: The target organization ID
            message: The message to send

        Returns:
            Number of connections that successfully received the message
        """
        connection_ids = list(self._org_connections.get(organization_id, set()))
        return await self.broadcast_to_connections(connection_ids, message)

    async def send_to_all(self, message: dict[str, Any]) -> int:
        """
        Send a JSON message to all active connections.

        Args:
            message: The message to send

        Returns:
            Number of connections that successfully received the message
        """
        connection_ids = list(self._connections.keys())
        return await self.broadcast_to_connections(connection_ids, message)


# Global singleton instance for the worker process
connection_manager = ConnectionManager()
