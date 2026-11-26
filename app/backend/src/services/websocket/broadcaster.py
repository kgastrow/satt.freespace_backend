"""
Message Broadcaster service for sending WebSocket messages from anywhere in the backend.
Provides a high-level API for broadcasting messages to users, organizations, or platform-wide.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.logger.logger import Logger
from src.services.websocket.redis_pubsub import redis_pubsub


class MessageBroadcaster:
    """
    Service API for broadcasting WebSocket messages from anywhere in the backend.

    Provides convenient methods for sending messages to:
    - Individual users (all their sessions)
    - All users in an organization
    - All connected users platform-wide

    Messages are automatically formatted with timestamp and routed via Redis pub/sub
    for cross-worker delivery.
    """

    def _build_message(
        self, message_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Build a properly formatted WebSocket message with timestamp.

        Args:
            message_type: The message type identifier
            payload: The message payload data

        Returns:
            Formatted message dict with type, payload, and ISO8601 timestamp
        """
        return {
            "type": message_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def send_to_user(
        self,
        user_id: UUID,
        message_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """
        Send a message to all sessions of a specific user.

        Args:
            user_id: The target user ID
            message_type: The message type identifier (e.g., "notification")
            payload: The message payload data

        Returns:
            True if the message was published successfully, False otherwise
        """
        message = self._build_message(message_type, payload)

        try:
            result = await redis_pubsub.publish_to_user(user_id, message)
            if result:
                Logger.debug(
                    "Broadcast message type '%s' to user %s",
                    message_type,
                    user_id,
                )
            else:
                Logger.warning(
                    "Failed to broadcast message type '%s' to user %s (Redis unavailable)",
                    message_type,
                    user_id,
                )
            return result
        except Exception as e:
            Logger.error(
                "Error broadcasting message type '%s' to user %s: %s",
                message_type,
                user_id,
                str(e),
            )
            return False

    async def send_to_organization(
        self,
        organization_id: UUID,
        message_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """
        Send a message to all users in an organization.

        Args:
            organization_id: The target organization ID
            message_type: The message type identifier (e.g., "notification")
            payload: The message payload data

        Returns:
            True if the message was published successfully, False otherwise
        """
        message = self._build_message(message_type, payload)

        try:
            result = await redis_pubsub.publish_to_org(organization_id, message)
            if result:
                Logger.debug(
                    "Broadcast message type '%s' to organization %s",
                    message_type,
                    organization_id,
                )
            else:
                Logger.warning(
                    "Failed to broadcast message type '%s' to organization %s (Redis unavailable)",
                    message_type,
                    organization_id,
                )
            return result
        except Exception as e:
            Logger.error(
                "Error broadcasting message type '%s' to organization %s: %s",
                message_type,
                organization_id,
                str(e),
            )
            return False

    async def send_to_platform(
        self,
        message_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """
        Send a message to all connected users platform-wide.

        Args:
            message_type: The message type identifier (e.g., "system_announcement")
            payload: The message payload data

        Returns:
            True if the message was published successfully, False otherwise
        """
        message = self._build_message(message_type, payload)

        try:
            result = await redis_pubsub.publish_to_platform(message)
            if result:
                Logger.debug("Broadcast message type '%s' to platform", message_type)
            else:
                Logger.warning(
                    "Failed to broadcast message type '%s' to platform (Redis unavailable)",
                    message_type,
                )
            return result
        except Exception as e:
            Logger.error(
                "Error broadcasting message type '%s' to platform: %s",
                message_type,
                str(e),
            )
            return False


# Singleton instance
message_broadcaster = MessageBroadcaster()
