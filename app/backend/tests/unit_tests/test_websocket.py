"""
Unit tests for WebSocket functionality.
Includes tests for serializers, broadcaster, connection manager, Redis pub/sub, and Redis registry.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
from pydantic import ValidationError
import pytest

from src.serialisers.websocket import (
    BroadcastRequest,
    BroadcastTarget,
    ConnectionMetadata,
    WebSocketMessage,
)
from src.services.websocket.broadcaster import MessageBroadcaster, message_broadcaster
from src.services.websocket.connection_manager import ConnectionInfo, ConnectionManager
from src.services.websocket.redis_pubsub import RedisPubSub
from src.services.websocket.redis_registry import RedisRegistry


# =============================================================================
# Serializer Tests
# =============================================================================


class TestBroadcastTarget:
    """Tests for BroadcastTarget enum."""

    def test_user_target_value(self):
        """Test USER target has correct value."""
        assert BroadcastTarget.USER.value == "user"

    def test_organization_target_value(self):
        """Test ORGANIZATION target has correct value."""
        assert BroadcastTarget.ORGANIZATION.value == "organization"

    def test_platform_target_value(self):
        """Test PLATFORM target has correct value."""
        assert BroadcastTarget.PLATFORM.value == "platform"

    def test_all_targets_are_strings(self):
        """Test all targets inherit from str."""
        for target in BroadcastTarget:
            assert isinstance(target.value, str)


class TestWebSocketMessage:
    """Tests for WebSocketMessage model."""

    def test_valid_message(self):
        """Test creating a valid WebSocket message."""
        now = datetime.now(timezone.utc)
        msg = WebSocketMessage(
            type="notification",
            payload={"title": "Test", "body": "Hello"},
            timestamp=now,
        )

        assert msg.type == "notification"
        assert msg.payload == {"title": "Test", "body": "Hello"}
        assert msg.timestamp == now

    def test_message_with_empty_payload(self):
        """Test message with empty payload is valid."""
        now = datetime.now(timezone.utc)
        msg = WebSocketMessage(type="ping", payload={}, timestamp=now)

        assert msg.type == "ping"
        assert msg.payload == {}

    def test_message_with_nested_payload(self):
        """Test message with nested payload structure."""
        now = datetime.now(timezone.utc)
        payload = {
            "data": {"items": [1, 2, 3], "meta": {"count": 3}},
            "action": "update",
        }
        msg = WebSocketMessage(type="data_update", payload=payload, timestamp=now)

        assert msg.payload["data"]["items"] == [1, 2, 3]
        assert msg.payload["data"]["meta"]["count"] == 3

    def test_message_missing_type_raises_error(self):
        """Test that missing type field raises ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            WebSocketMessage(payload={}, timestamp=now)

        assert "type" in str(exc_info.value)

    def test_message_missing_payload_raises_error(self):
        """Test that missing payload field raises ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            WebSocketMessage(type="test", timestamp=now)

        assert "payload" in str(exc_info.value)

    def test_message_missing_timestamp_raises_error(self):
        """Test that missing timestamp field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            WebSocketMessage(type="test", payload={})

        assert "timestamp" in str(exc_info.value)

    def test_message_rejects_extra_fields(self):
        """Test that extra fields are rejected due to ConfigDict(extra='forbid')."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            WebSocketMessage(
                type="test",
                payload={},
                timestamp=now,
                extra_field="not allowed",
            )

        assert "extra" in str(exc_info.value).lower()


class TestConnectionMetadata:
    """Tests for ConnectionMetadata model."""

    def test_valid_connection_metadata(self):
        """Test creating valid connection metadata."""
        user_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)
        conn_id = "conn-12345"

        metadata = ConnectionMetadata(
            user_id=user_id,
            organization_id=org_id,
            connection_id=conn_id,
            connected_at=now,
        )

        assert metadata.user_id == user_id
        assert metadata.organization_id == org_id
        assert metadata.connection_id == conn_id
        assert metadata.connected_at == now

    def test_connection_metadata_accepts_uuid_strings(self):
        """Test that UUID fields accept string representations."""
        user_id = uuid4()
        org_id = uuid4()
        now = datetime.now(timezone.utc)

        metadata = ConnectionMetadata(
            user_id=str(user_id),
            organization_id=str(org_id),
            connection_id="conn-abc",
            connected_at=now,
        )

        assert metadata.user_id == user_id
        assert metadata.organization_id == org_id

    def test_connection_metadata_missing_user_id_raises_error(self):
        """Test that missing user_id raises ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            ConnectionMetadata(
                organization_id=uuid4(),
                connection_id="conn-123",
                connected_at=now,
            )

        assert "user_id" in str(exc_info.value)

    def test_connection_metadata_missing_organization_id_raises_error(self):
        """Test that missing organization_id raises ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            ConnectionMetadata(
                user_id=uuid4(),
                connection_id="conn-123",
                connected_at=now,
            )

        assert "organization_id" in str(exc_info.value)

    def test_connection_metadata_missing_connection_id_raises_error(self):
        """Test that missing connection_id raises ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            ConnectionMetadata(
                user_id=uuid4(),
                organization_id=uuid4(),
                connected_at=now,
            )

        assert "connection_id" in str(exc_info.value)

    def test_connection_metadata_missing_connected_at_raises_error(self):
        """Test that missing connected_at raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ConnectionMetadata(
                user_id=uuid4(),
                organization_id=uuid4(),
                connection_id="conn-123",
            )

        assert "connected_at" in str(exc_info.value)

    def test_connection_metadata_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            ConnectionMetadata(
                user_id=uuid4(),
                organization_id=uuid4(),
                connection_id="conn-123",
                connected_at=now,
                worker_id="worker-1",
            )

        assert "extra" in str(exc_info.value).lower()

    def test_connection_metadata_invalid_uuid_raises_error(self):
        """Test that invalid UUID format raises ValidationError."""
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError) as exc_info:
            ConnectionMetadata(
                user_id="not-a-uuid",
                organization_id=uuid4(),
                connection_id="conn-123",
                connected_at=now,
            )

        assert "user_id" in str(exc_info.value)


class TestBroadcastRequest:
    """Tests for BroadcastRequest model."""

    def test_valid_user_broadcast(self):
        """Test creating a valid user-targeted broadcast."""
        user_id = uuid4()
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(type="notification", payload={}, timestamp=now)

        request = BroadcastRequest(
            target=BroadcastTarget.USER,
            target_id=user_id,
            message=message,
        )

        assert request.target == BroadcastTarget.USER
        assert request.target_id == user_id
        assert request.message == message

    def test_valid_organization_broadcast(self):
        """Test creating a valid organization-targeted broadcast."""
        org_id = uuid4()
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(
            type="alert", payload={"level": "info"}, timestamp=now
        )

        request = BroadcastRequest(
            target=BroadcastTarget.ORGANIZATION,
            target_id=org_id,
            message=message,
        )

        assert request.target == BroadcastTarget.ORGANIZATION
        assert request.target_id == org_id

    def test_valid_platform_broadcast(self):
        """Test creating a valid platform-wide broadcast."""
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(
            type="system_announcement",
            payload={"message": "Maintenance scheduled"},
            timestamp=now,
        )

        request = BroadcastRequest(
            target=BroadcastTarget.PLATFORM,
            target_id=None,
            message=message,
        )

        assert request.target == BroadcastTarget.PLATFORM
        assert request.target_id is None

    def test_platform_broadcast_without_target_id(self):
        """Test platform broadcast can omit target_id entirely."""
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(type="broadcast", payload={}, timestamp=now)

        request = BroadcastRequest(
            target=BroadcastTarget.PLATFORM,
            message=message,
        )

        assert request.target_id is None

    def test_broadcast_request_accepts_target_string(self):
        """Test that target field accepts string value."""
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(type="test", payload={}, timestamp=now)

        request = BroadcastRequest(
            target="platform",
            message=message,
        )

        assert request.target == BroadcastTarget.PLATFORM

    def test_broadcast_request_invalid_target_raises_error(self):
        """Test that invalid target value raises ValidationError."""
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(type="test", payload={}, timestamp=now)

        with pytest.raises(ValidationError) as exc_info:
            BroadcastRequest(
                target="invalid_target",
                message=message,
            )

        assert "target" in str(exc_info.value)

    def test_broadcast_request_missing_target_raises_error(self):
        """Test that missing target raises ValidationError."""
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(type="test", payload={}, timestamp=now)

        with pytest.raises(ValidationError) as exc_info:
            BroadcastRequest(message=message)

        assert "target" in str(exc_info.value)

    def test_broadcast_request_missing_message_raises_error(self):
        """Test that missing message raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            BroadcastRequest(target=BroadcastTarget.PLATFORM)

        assert "message" in str(exc_info.value)

    def test_broadcast_request_rejects_extra_fields(self):
        """Test that extra fields are rejected."""
        now = datetime.now(timezone.utc)
        message = WebSocketMessage(type="test", payload={}, timestamp=now)

        with pytest.raises(ValidationError) as exc_info:
            BroadcastRequest(
                target=BroadcastTarget.PLATFORM,
                message=message,
                priority="high",
            )

        assert "extra" in str(exc_info.value).lower()

    def test_broadcast_request_with_nested_message_dict(self):
        """Test that message can be provided as dict (auto-validated)."""
        now = datetime.now(timezone.utc)

        request = BroadcastRequest(
            target=BroadcastTarget.USER,
            target_id=uuid4(),
            message={
                "type": "notification",
                "payload": {"data": "test"},
                "timestamp": now,
            },
        )

        assert isinstance(request.message, WebSocketMessage)
        assert request.message.type == "notification"


# =============================================================================
# MessageBroadcaster Tests
# =============================================================================


class TestMessageBroadcasterBuildMessage:
    """Tests for message building functionality."""

    def test_build_message_structure(self):
        """Test that _build_message creates properly formatted message."""
        broadcaster = MessageBroadcaster()
        message = broadcaster._build_message(
            message_type="notification",
            payload={"title": "Hello", "body": "World"},
        )

        assert message["type"] == "notification"
        assert message["payload"] == {"title": "Hello", "body": "World"}
        assert "timestamp" in message

    def test_build_message_timestamp_is_iso8601(self):
        """Test that timestamp is in ISO8601 format."""
        broadcaster = MessageBroadcaster()
        message = broadcaster._build_message(
            message_type="test",
            payload={},
        )

        # Should be parseable as ISO8601
        timestamp = message["timestamp"]
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None
        assert parsed.tzinfo is not None  # Should have timezone info

    def test_build_message_timestamp_is_utc(self):
        """Test that timestamp is in UTC."""
        broadcaster = MessageBroadcaster()

        before = datetime.now(timezone.utc)
        message = broadcaster._build_message(
            message_type="test",
            payload={},
        )
        after = datetime.now(timezone.utc)

        timestamp_str = message["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # Timestamp should be between before and after
        assert before <= timestamp <= after

    def test_build_message_with_complex_payload(self):
        """Test building message with complex nested payload."""
        broadcaster = MessageBroadcaster()
        payload = {
            "id": str(uuid4()),
            "data": {
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "boolean": True,
                "null": None,
            },
        }

        message = broadcaster._build_message(
            message_type="complex",
            payload=payload,
        )

        assert message["payload"] == payload


class TestMessageBroadcasterSendToUser:
    """Tests for send_to_user functionality."""

    @pytest.mark.asyncio
    async def test_send_to_user_success(self):
        """Test sending message to user successfully."""
        broadcaster = MessageBroadcaster()
        user_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_user = AsyncMock(return_value=True)

            result = await broadcaster.send_to_user(
                user_id=user_id,
                message_type="notification",
                payload={"title": "Hello"},
            )

            assert result is True
            mock_pubsub.publish_to_user.assert_called_once()

            # Verify message format
            call_args = mock_pubsub.publish_to_user.call_args
            assert call_args[0][0] == user_id
            message = call_args[0][1]
            assert message["type"] == "notification"
            assert message["payload"] == {"title": "Hello"}
            assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_send_to_user_redis_unavailable(self):
        """Test send_to_user returns False when Redis is unavailable."""
        broadcaster = MessageBroadcaster()
        user_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_user = AsyncMock(return_value=False)

            result = await broadcaster.send_to_user(
                user_id=user_id,
                message_type="notification",
                payload={"title": "Hello"},
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_user_handles_exception(self):
        """Test send_to_user handles exceptions gracefully."""
        broadcaster = MessageBroadcaster()
        user_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_user = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            result = await broadcaster.send_to_user(
                user_id=user_id,
                message_type="notification",
                payload={"title": "Hello"},
            )

            assert result is False


class TestMessageBroadcasterSendToOrganization:
    """Tests for send_to_organization functionality."""

    @pytest.mark.asyncio
    async def test_send_to_organization_success(self):
        """Test sending message to organization successfully."""
        broadcaster = MessageBroadcaster()
        org_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_org = AsyncMock(return_value=True)

            result = await broadcaster.send_to_organization(
                organization_id=org_id,
                message_type="broadcast",
                payload={"announcement": "Update available"},
            )

            assert result is True
            mock_pubsub.publish_to_org.assert_called_once()

            # Verify message format
            call_args = mock_pubsub.publish_to_org.call_args
            assert call_args[0][0] == org_id
            message = call_args[0][1]
            assert message["type"] == "broadcast"
            assert message["payload"] == {"announcement": "Update available"}
            assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_send_to_organization_redis_unavailable(self):
        """Test send_to_organization returns False when Redis is unavailable."""
        broadcaster = MessageBroadcaster()
        org_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_org = AsyncMock(return_value=False)

            result = await broadcaster.send_to_organization(
                organization_id=org_id,
                message_type="broadcast",
                payload={"announcement": "Update available"},
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_organization_handles_exception(self):
        """Test send_to_organization handles exceptions gracefully."""
        broadcaster = MessageBroadcaster()
        org_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_org = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            result = await broadcaster.send_to_organization(
                organization_id=org_id,
                message_type="broadcast",
                payload={"announcement": "Update available"},
            )

            assert result is False


class TestMessageBroadcasterSendToPlatform:
    """Tests for send_to_platform functionality."""

    @pytest.mark.asyncio
    async def test_send_to_platform_success(self):
        """Test sending message to platform successfully."""
        broadcaster = MessageBroadcaster()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_platform = AsyncMock(return_value=True)

            result = await broadcaster.send_to_platform(
                message_type="system_announcement",
                payload={"message": "System maintenance in 1 hour"},
            )

            assert result is True
            mock_pubsub.publish_to_platform.assert_called_once()

            # Verify message format
            call_args = mock_pubsub.publish_to_platform.call_args
            message = call_args[0][0]
            assert message["type"] == "system_announcement"
            assert message["payload"] == {"message": "System maintenance in 1 hour"}
            assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_send_to_platform_redis_unavailable(self):
        """Test send_to_platform returns False when Redis is unavailable."""
        broadcaster = MessageBroadcaster()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_platform = AsyncMock(return_value=False)

            result = await broadcaster.send_to_platform(
                message_type="system_announcement",
                payload={"message": "System maintenance in 1 hour"},
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_platform_handles_exception(self):
        """Test send_to_platform handles exceptions gracefully."""
        broadcaster = MessageBroadcaster()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_platform = AsyncMock(
                side_effect=Exception("Connection failed")
            )

            result = await broadcaster.send_to_platform(
                message_type="system_announcement",
                payload={"message": "System maintenance in 1 hour"},
            )

            assert result is False


class TestMessageBroadcasterMessageFormat:
    """Tests for message format consistency."""

    @pytest.mark.asyncio
    async def test_message_format_has_required_fields(self):
        """Test that all messages have required fields."""
        broadcaster = MessageBroadcaster()
        captured_messages = []

        def capture_user_message(uid, msg):
            captured_messages.append(msg)
            return True

        def capture_org_message(oid, msg):
            captured_messages.append(msg)
            return True

        def capture_platform_message(msg):
            captured_messages.append(msg)
            return True

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_user = AsyncMock(side_effect=capture_user_message)
            mock_pubsub.publish_to_org = AsyncMock(side_effect=capture_org_message)
            mock_pubsub.publish_to_platform = AsyncMock(
                side_effect=capture_platform_message
            )

            await broadcaster.send_to_user(uuid4(), "type1", {"key": "value1"})
            await broadcaster.send_to_organization(uuid4(), "type2", {"key": "value2"})
            await broadcaster.send_to_platform("type3", {"key": "value3"})

            for message in captured_messages:
                assert "type" in message
                assert "payload" in message
                assert "timestamp" in message
                assert isinstance(message["type"], str)
                assert isinstance(message["payload"], dict)
                assert isinstance(message["timestamp"], str)


class TestMessageBroadcasterSingleton:
    """Tests for the global message_broadcaster singleton."""

    def test_singleton_import(self):
        """Test that message_broadcaster singleton can be imported."""
        assert isinstance(message_broadcaster, MessageBroadcaster)

    def test_module_import(self):
        """Test importing from the package."""
        from src.services.websocket import MessageBroadcaster, message_broadcaster

        assert isinstance(message_broadcaster, MessageBroadcaster)


class TestMessageBroadcasterGracefulDegradation:
    """Tests for graceful degradation when dependencies fail."""

    @pytest.mark.asyncio
    async def test_all_methods_return_false_on_failure(self):
        """Test that all broadcast methods return False on failure, never raise."""
        broadcaster = MessageBroadcaster()
        user_id = uuid4()
        org_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_user = AsyncMock(return_value=False)
            mock_pubsub.publish_to_org = AsyncMock(return_value=False)
            mock_pubsub.publish_to_platform = AsyncMock(return_value=False)

            # None of these should raise
            result1 = await broadcaster.send_to_user(user_id, "test", {})
            result2 = await broadcaster.send_to_organization(org_id, "test", {})
            result3 = await broadcaster.send_to_platform("test", {})

            assert result1 is False
            assert result2 is False
            assert result3 is False

    @pytest.mark.asyncio
    async def test_all_methods_catch_exceptions(self):
        """Test that all broadcast methods catch exceptions, never propagate."""
        broadcaster = MessageBroadcaster()
        user_id = uuid4()
        org_id = uuid4()

        with patch("src.services.websocket.broadcaster.redis_pubsub") as mock_pubsub:
            mock_pubsub.publish_to_user = AsyncMock(
                side_effect=RuntimeError("Test error")
            )
            mock_pubsub.publish_to_org = AsyncMock(
                side_effect=RuntimeError("Test error")
            )
            mock_pubsub.publish_to_platform = AsyncMock(
                side_effect=RuntimeError("Test error")
            )

            # None of these should raise
            result1 = await broadcaster.send_to_user(user_id, "test", {})
            result2 = await broadcaster.send_to_organization(org_id, "test", {})
            result3 = await broadcaster.send_to_platform("test", {})

            assert result1 is False
            assert result2 is False
            assert result3 is False


# =============================================================================
# ConnectionManager Tests
# =============================================================================


class TestConnectionInfo:
    """Tests for ConnectionInfo dataclass."""

    def test_connection_info_creation(self):
        """Test ConnectionInfo is created with correct defaults."""
        websocket = MagicMock()
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "test-conn-123"

        info = ConnectionInfo(
            websocket=websocket,
            connection_id=connection_id,
            user_id=user_id,
            organization_id=org_id,
        )

        assert info.websocket == websocket
        assert info.connection_id == connection_id
        assert info.user_id == user_id
        assert info.organization_id == org_id
        assert isinstance(info.connected_at, datetime)

    def test_connection_info_custom_connected_at(self):
        """Test ConnectionInfo with custom connected_at."""
        websocket = MagicMock()
        user_id = uuid4()
        org_id = uuid4()
        custom_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        info = ConnectionInfo(
            websocket=websocket,
            connection_id="test-conn",
            user_id=user_id,
            organization_id=org_id,
            connected_at=custom_time,
        )

        assert info.connected_at == custom_time


class TestConnectionManager:
    """Tests for ConnectionManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager for each test."""
        return ConnectionManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_stores_connection(self, manager, mock_websocket):
        """Test that connect() stores the connection properly."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)

        assert manager.connection_count == 1
        assert manager.get_connection(connection_id) == mock_websocket

    @pytest.mark.asyncio
    async def test_connect_indexes_by_user(self, manager, mock_websocket):
        """Test that connect() indexes connection by user_id."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)

        user_connections = manager.get_connections_for_user(user_id)
        assert len(user_connections) == 1
        assert user_connections[0] == mock_websocket

    @pytest.mark.asyncio
    async def test_connect_indexes_by_org(self, manager, mock_websocket):
        """Test that connect() indexes connection by organization_id."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)

        org_connections = manager.get_connections_for_org(org_id)
        assert len(org_connections) == 1
        assert org_connections[0] == mock_websocket

    @pytest.mark.asyncio
    async def test_multiple_connections_same_user(self, manager):
        """Test multiple connections for the same user (multi-session support)."""
        user_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws2 = MagicMock()

        await manager.connect(ws1, "conn-1", user_id, org_id)
        await manager.connect(ws2, "conn-2", user_id, org_id)

        user_connections = manager.get_connections_for_user(user_id)
        assert len(user_connections) == 2
        assert ws1 in user_connections
        assert ws2 in user_connections

    @pytest.mark.asyncio
    async def test_multiple_users_same_org(self, manager):
        """Test multiple users in the same organization."""
        user1_id = uuid4()
        user2_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws2 = MagicMock()

        await manager.connect(ws1, "conn-1", user1_id, org_id)
        await manager.connect(ws2, "conn-2", user2_id, org_id)

        org_connections = manager.get_connections_for_org(org_id)
        assert len(org_connections) == 2
        assert ws1 in org_connections
        assert ws2 in org_connections

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager, mock_websocket):
        """Test that disconnect() removes the connection."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)
        await manager.disconnect(connection_id)

        assert manager.connection_count == 0
        assert manager.get_connection(connection_id) is None

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_user_index(self, manager, mock_websocket):
        """Test that disconnect() cleans up user connection index."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)
        await manager.disconnect(connection_id)

        user_connections = manager.get_connections_for_user(user_id)
        assert len(user_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_org_index(self, manager, mock_websocket):
        """Test that disconnect() cleans up organization connection index."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)
        await manager.disconnect(connection_id)

        org_connections = manager.get_connections_for_org(org_id)
        assert len(org_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_connection(self, manager):
        """Test that disconnect() handles unknown connection gracefully."""
        await manager.disconnect("unknown-conn")
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_partial_user_cleanup(self, manager):
        """Test that disconnect() only removes the specific connection from user index."""
        user_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws2 = MagicMock()

        await manager.connect(ws1, "conn-1", user_id, org_id)
        await manager.connect(ws2, "conn-2", user_id, org_id)
        await manager.disconnect("conn-1")

        user_connections = manager.get_connections_for_user(user_id)
        assert len(user_connections) == 1
        assert ws2 in user_connections

    @pytest.mark.asyncio
    async def test_get_connections_for_user_empty(self, manager):
        """Test get_connections_for_user returns empty list for unknown user."""
        unknown_user_id = uuid4()
        connections = manager.get_connections_for_user(unknown_user_id)
        assert connections == []

    @pytest.mark.asyncio
    async def test_get_connections_for_org_empty(self, manager):
        """Test get_connections_for_org returns empty list for unknown org."""
        unknown_org_id = uuid4()
        connections = manager.get_connections_for_org(unknown_org_id)
        assert connections == []

    @pytest.mark.asyncio
    async def test_get_all_connections(self, manager):
        """Test get_all_connections returns all active connections."""
        user1_id = uuid4()
        user2_id = uuid4()
        org1_id = uuid4()
        org2_id = uuid4()

        ws1 = MagicMock()
        ws2 = MagicMock()
        ws3 = MagicMock()

        await manager.connect(ws1, "conn-1", user1_id, org1_id)
        await manager.connect(ws2, "conn-2", user2_id, org1_id)
        await manager.connect(ws3, "conn-3", user1_id, org2_id)

        all_connections = manager.get_all_connections()
        assert len(all_connections) == 3
        assert ws1 in all_connections
        assert ws2 in all_connections
        assert ws3 in all_connections

    @pytest.mark.asyncio
    async def test_get_connection(self, manager, mock_websocket):
        """Test get_connection returns specific WebSocket."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        await manager.connect(mock_websocket, connection_id, user_id, org_id)

        result = manager.get_connection(connection_id)
        assert result == mock_websocket

    @pytest.mark.asyncio
    async def test_get_connection_not_found(self, manager):
        """Test get_connection returns None for unknown connection."""
        result = manager.get_connection("unknown-conn")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_to_connection_success(self, manager, mock_websocket):
        """Test send_to_connection sends message successfully."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"
        message = {"type": "test", "payload": {"data": "value"}}

        await manager.connect(mock_websocket, connection_id, user_id, org_id)
        result = await manager.send_to_connection(connection_id, message)

        assert result is True
        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_connection_not_found(self, manager):
        """Test send_to_connection returns False for unknown connection."""
        message = {"type": "test", "payload": {}}
        result = await manager.send_to_connection("unknown-conn", message)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_connection_error(self, manager):
        """Test send_to_connection handles send errors gracefully."""
        user_id = uuid4()
        org_id = uuid4()
        connection_id = "conn-1"

        ws = MagicMock()
        ws.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        await manager.connect(ws, connection_id, user_id, org_id)
        result = await manager.send_to_connection(connection_id, {"type": "test"})

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_to_connections(self, manager):
        """Test broadcast_to_connections sends to multiple connections."""
        user_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()
        ws3 = MagicMock()
        ws3.send_json = AsyncMock()

        await manager.connect(ws1, "conn-1", user_id, org_id)
        await manager.connect(ws2, "conn-2", user_id, org_id)
        await manager.connect(ws3, "conn-3", user_id, org_id)

        message = {"type": "broadcast", "payload": {"data": "test"}}
        result = await manager.broadcast_to_connections(
            ["conn-1", "conn-2", "conn-3"], message
        )

        assert result == 3
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_to_connections_partial_failure(self, manager):
        """Test broadcast_to_connections counts partial failures."""
        user_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock(side_effect=Exception("Failed"))

        await manager.connect(ws1, "conn-1", user_id, org_id)
        await manager.connect(ws2, "conn-2", user_id, org_id)

        message = {"type": "broadcast", "payload": {}}
        result = await manager.broadcast_to_connections(["conn-1", "conn-2"], message)

        assert result == 1

    @pytest.mark.asyncio
    async def test_send_to_user(self, manager):
        """Test send_to_user sends to all user connections."""
        user_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1, "conn-1", user_id, org_id)
        await manager.connect(ws2, "conn-2", user_id, org_id)

        message = {"type": "user_message", "payload": {"info": "test"}}
        result = await manager.send_to_user(user_id, message)

        assert result == 2
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_user_no_connections(self, manager):
        """Test send_to_user returns 0 for user with no connections."""
        user_id = uuid4()
        result = await manager.send_to_user(user_id, {"type": "test"})
        assert result == 0

    @pytest.mark.asyncio
    async def test_send_to_org(self, manager):
        """Test send_to_org sends to all org connections."""
        user1_id = uuid4()
        user2_id = uuid4()
        org_id = uuid4()

        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1, "conn-1", user1_id, org_id)
        await manager.connect(ws2, "conn-2", user2_id, org_id)

        message = {"type": "org_broadcast", "payload": {"announcement": "test"}}
        result = await manager.send_to_org(org_id, message)

        assert result == 2
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_org_no_connections(self, manager):
        """Test send_to_org returns 0 for org with no connections."""
        org_id = uuid4()
        result = await manager.send_to_org(org_id, {"type": "test"})
        assert result == 0

    @pytest.mark.asyncio
    async def test_send_to_all(self, manager):
        """Test send_to_all sends to all active connections."""
        user1_id = uuid4()
        user2_id = uuid4()
        org1_id = uuid4()
        org2_id = uuid4()

        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()
        ws3 = MagicMock()
        ws3.send_json = AsyncMock()

        await manager.connect(ws1, "conn-1", user1_id, org1_id)
        await manager.connect(ws2, "conn-2", user2_id, org1_id)
        await manager.connect(ws3, "conn-3", user1_id, org2_id)

        message = {"type": "platform", "payload": {"system": "announcement"}}
        result = await manager.send_to_all(message)

        assert result == 3
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_all_empty(self, manager):
        """Test send_to_all returns 0 with no connections."""
        result = await manager.send_to_all({"type": "test"})
        assert result == 0

    @pytest.mark.asyncio
    async def test_connection_count(self, manager):
        """Test connection_count property."""
        user_id = uuid4()
        org_id = uuid4()

        assert manager.connection_count == 0

        ws1 = MagicMock()
        ws2 = MagicMock()

        await manager.connect(ws1, "conn-1", user_id, org_id)
        assert manager.connection_count == 1

        await manager.connect(ws2, "conn-2", user_id, org_id)
        assert manager.connection_count == 2

        await manager.disconnect("conn-1")
        assert manager.connection_count == 1

        await manager.disconnect("conn-2")
        assert manager.connection_count == 0


class TestConnectionManagerSingleton:
    """Tests for the global connection_manager singleton."""

    def test_singleton_import(self):
        """Test that connection_manager singleton can be imported."""
        from src.services.websocket.connection_manager import connection_manager

        assert isinstance(connection_manager, ConnectionManager)

    def test_module_import(self):
        """Test importing from the package."""
        from src.services.websocket import ConnectionManager, connection_manager

        assert isinstance(connection_manager, ConnectionManager)


# =============================================================================
# RedisPubSub Tests
# =============================================================================


class TestRedisPubSub:
    """Tests for RedisPubSub class."""

    @pytest.fixture(autouse=True)
    def reset_channel_ns(self):
        """Reset channel namespace to empty so tests don't depend on env Redis DB."""
        with patch("src.services.websocket.redis_pubsub._CHANNEL_NS", ""):
            yield

    @pytest.fixture
    def fake_redis(self):
        """Create a fake Redis instance for testing."""
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def pubsub(self, fake_redis):
        """Create a RedisPubSub with mocked cache service."""
        pubsub_instance = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis
            pubsub_instance._get_redis = lambda: fake_redis
            yield pubsub_instance
        # Ensure cleanup after each test
        asyncio.get_event_loop().run_until_complete(pubsub_instance.stop())

    @pytest.fixture
    def mock_unavailable_pubsub(self):
        """Create a RedisPubSub with unavailable Redis."""
        pubsub_instance = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = None
            yield pubsub_instance

    def test_get_user_channel(self):
        """Test user channel name generation."""
        user_id = uuid4()
        channel = RedisPubSub.get_user_channel(user_id)
        assert channel == f"ws:user:{user_id}"

    def test_get_org_channel(self):
        """Test organization channel name generation."""
        org_id = uuid4()
        channel = RedisPubSub.get_org_channel(org_id)
        assert channel == f"ws:org:{org_id}"

    def test_get_platform_channel(self):
        """Test platform channel name."""
        channel = RedisPubSub.get_platform_channel()
        assert channel == "ws:platform"

    @pytest.mark.asyncio
    async def test_is_available_with_redis(self, fake_redis):
        """Test _is_available returns True when Redis is available."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis
            result = await pubsub._is_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_is_available_without_redis(self, mock_unavailable_pubsub):
        """Test _is_available returns False when Redis is unavailable."""
        result = await mock_unavailable_pubsub._is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_success(self, fake_redis):
        """Test publishing a message to a channel."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            channel = "test:channel"
            message = {"type": "test", "payload": {"data": "value"}}

            result = await pubsub.publish(channel, message)
            assert result is True

    @pytest.mark.asyncio
    async def test_publish_redis_unavailable(self, mock_unavailable_pubsub):
        """Test publish returns False when Redis is unavailable."""
        result = await mock_unavailable_pubsub.publish(
            "test:channel",
            {"type": "test", "payload": {}},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_to_user(self, fake_redis):
        """Test publishing to a user-specific channel."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            user_id = uuid4()
            message = {"type": "notification", "payload": {"title": "Hello"}}

            result = await pubsub.publish_to_user(user_id, message)
            assert result is True

    @pytest.mark.asyncio
    async def test_publish_to_org(self, fake_redis):
        """Test publishing to an organization channel."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            org_id = uuid4()
            message = {"type": "broadcast", "payload": {"announcement": "Update"}}

            result = await pubsub.publish_to_org(org_id, message)
            assert result is True

    @pytest.mark.asyncio
    async def test_publish_to_platform(self, fake_redis):
        """Test publishing to the platform-wide channel."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            message = {"type": "system", "payload": {"status": "maintenance"}}

            result = await pubsub.publish_to_platform(message)
            assert result is True

    @pytest.mark.asyncio
    async def test_subscribe_redis_unavailable(self, mock_unavailable_pubsub):
        """Test subscribe returns False when Redis is unavailable."""
        callback = AsyncMock()
        result = await mock_unavailable_pubsub.subscribe("test:channel", callback)
        assert result is False

    @pytest.mark.asyncio
    async def test_unsubscribe_no_pubsub(self):
        """Test unsubscribe returns True when no pubsub exists."""
        pubsub = RedisPubSub()
        result = await pubsub.unsubscribe("test:channel")
        assert result is True

    @pytest.mark.asyncio
    async def test_subscribe_for_connection(self, fake_redis):
        """Test subscribing to all channels for a connection."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            user_id = uuid4()
            org_id = uuid4()
            callback = AsyncMock()

            await pubsub.subscribe_for_connection(user_id, org_id, callback)

            # Should subscribe to 3 channels: user, org, platform
            assert len(pubsub._subscriptions) == 3
            assert pubsub.get_user_channel(user_id) in pubsub._subscriptions
            assert pubsub.get_org_channel(org_id) in pubsub._subscriptions
            assert pubsub.get_platform_channel() in pubsub._subscriptions

            await pubsub.stop()

    @pytest.mark.asyncio
    async def test_subscribe_for_connection_redis_unavailable(
        self, mock_unavailable_pubsub
    ):
        """Test subscribe_for_connection handles Redis unavailability."""
        user_id = uuid4()
        org_id = uuid4()
        callback = AsyncMock()

        result = await mock_unavailable_pubsub.subscribe_for_connection(
            user_id, org_id, callback
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, fake_redis):
        """Test stop() properly cleans up resources."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            callback = AsyncMock()
            await pubsub.subscribe("test:channel", callback)

            await pubsub.stop()

            assert pubsub._running is False
            assert pubsub._listener_task is None
            assert pubsub._pubsub is None
            assert len(pubsub._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_message_serialization(self, fake_redis):
        """Test that messages are properly JSON serialized."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            # Test with various data types
            message = {
                "type": "test",
                "payload": {
                    "string": "value",
                    "number": 42,
                    "float": 3.14,
                    "boolean": True,
                    "null": None,
                    "list": [1, 2, 3],
                    "nested": {"key": "value"},
                },
            }

            result = await pubsub.publish("test:channel", message)
            assert result is True

    @pytest.mark.asyncio
    async def test_message_with_uuid_serialization(self, fake_redis):
        """Test that messages with UUID values are serialized properly."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            user_id = uuid4()
            message = {
                "type": "test",
                "payload": {"user_id": user_id},
            }

            # Should not raise - UUID is handled by default=str in json.dumps
            result = await pubsub.publish("test:channel", message)
            assert result is True

    @pytest.mark.asyncio
    async def test_listener_task_created_on_subscribe(self, fake_redis):
        """Test that listener task is created when first subscription happens."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            callback = AsyncMock()

            assert pubsub._listener_task is None
            assert pubsub._running is False

            await pubsub.subscribe("test:channel", callback)

            assert pubsub._running is True
            assert pubsub._listener_task is not None

            await pubsub.stop()

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_same_listener(self, fake_redis):
        """Test that multiple subscriptions use the same listener task."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            callback = AsyncMock()

            await pubsub.subscribe("channel-1", callback)
            first_task = pubsub._listener_task

            await pubsub.subscribe("channel-2", callback)
            second_task = pubsub._listener_task

            # Same task should be reused
            assert first_task is second_task

            await pubsub.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_keeps_listener_running_when_empty(self, fake_redis):
        """Unsubscribing the last channel must NOT stop the listener.

        Auto-stopping on empty used to race with a concurrent subscribe()
        from a reconnecting client: stop() suspends on listener cancellation,
        the new subscribe registers callbacks on state that stop() then
        wipes, and the worker ends up with a dead listener. The listener is
        cheap to keep idle; only the lifespan shutdown calls stop().
        """
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = fake_redis

            callback = AsyncMock()

            await pubsub.subscribe("test:channel", callback)
            assert pubsub._running is True

            await pubsub.unsubscribe("test:channel")

            assert pubsub._running is True
            assert pubsub._subscriptions == {}

            await pubsub.stop()
            assert pubsub._running is False


class TestRedisPubSubChannelPatterns:
    """Tests for channel naming conventions."""

    @pytest.fixture(autouse=True)
    def reset_channel_ns(self):
        """Reset channel namespace to empty so tests don't depend on env Redis DB."""
        with patch("src.services.websocket.redis_pubsub._CHANNEL_NS", ""):
            yield

    def test_user_channel_pattern(self):
        """Test user channel follows expected pattern."""
        user_id = uuid4()
        channel = RedisPubSub.get_user_channel(user_id)
        assert channel.startswith("ws:user:")
        assert str(user_id) in channel

    def test_org_channel_pattern(self):
        """Test org channel follows expected pattern."""
        org_id = uuid4()
        channel = RedisPubSub.get_org_channel(org_id)
        assert channel.startswith("ws:org:")
        assert str(org_id) in channel

    def test_platform_channel_pattern(self):
        """Test platform channel is exactly as expected."""
        channel = RedisPubSub.get_platform_channel()
        assert channel == "ws:platform"


class TestRedisPubSubSingleton:
    """Tests for the global redis_pubsub singleton."""

    def test_singleton_import(self):
        """Test that redis_pubsub singleton can be imported."""
        from src.services.websocket.redis_pubsub import redis_pubsub

        assert isinstance(redis_pubsub, RedisPubSub)

    def test_module_import(self):
        """Test importing from the package."""
        from src.services.websocket import RedisPubSub, redis_pubsub

        assert isinstance(redis_pubsub, RedisPubSub)


class TestRedisPubSubGracefulDegradation:
    """Tests for graceful degradation when Redis is unavailable."""

    @pytest.fixture
    def unavailable_pubsub(self):
        """Create a RedisPubSub with unavailable Redis."""
        pubsub = RedisPubSub()
        with patch("src.services.websocket.redis_pubsub.cache_service") as mock_cache:
            mock_cache._redis = None
            yield pubsub

    @pytest.mark.asyncio
    async def test_publish_fails_gracefully(self, unavailable_pubsub):
        """Test publish returns False instead of raising exception."""
        result = await unavailable_pubsub.publish(
            "test:channel",
            {"type": "test", "payload": {}},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_to_user_fails_gracefully(self, unavailable_pubsub):
        """Test publish_to_user returns False instead of raising exception."""
        result = await unavailable_pubsub.publish_to_user(
            uuid4(),
            {"type": "test", "payload": {}},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_to_org_fails_gracefully(self, unavailable_pubsub):
        """Test publish_to_org returns False instead of raising exception."""
        result = await unavailable_pubsub.publish_to_org(
            uuid4(),
            {"type": "test", "payload": {}},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_to_platform_fails_gracefully(self, unavailable_pubsub):
        """Test publish_to_platform returns False instead of raising exception."""
        result = await unavailable_pubsub.publish_to_platform(
            {"type": "test", "payload": {}},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_fails_gracefully(self, unavailable_pubsub):
        """Test subscribe returns False instead of raising exception."""
        callback = AsyncMock()
        result = await unavailable_pubsub.subscribe("test:channel", callback)
        assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_for_connection_fails_gracefully(self, unavailable_pubsub):
        """Test subscribe_for_connection returns False instead of raising."""
        callback = AsyncMock()
        result = await unavailable_pubsub.subscribe_for_connection(
            uuid4(),
            uuid4(),
            callback,
        )
        assert result is False


# =============================================================================
# RedisRegistry Tests
# =============================================================================


class TestRedisRegistry:
    """Tests for RedisRegistry class."""

    @pytest.fixture
    def fake_redis(self):
        """Create a fake Redis instance for testing."""
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def registry(self, fake_redis):
        """Create a RedisRegistry with mocked cache service."""
        registry = RedisRegistry()
        with patch("src.services.websocket.redis_registry.cache_service") as mock_cache:
            mock_cache._redis = fake_redis
            registry._get_redis = lambda: fake_redis
            yield registry

    @pytest.fixture
    def mock_unavailable_registry(self):
        """Create a RedisRegistry with unavailable Redis."""
        registry = RedisRegistry()
        with patch("src.services.websocket.redis_registry.cache_service") as mock_cache:
            mock_cache._redis = None
            yield registry

    @pytest.mark.asyncio
    async def test_is_available_with_redis(self, fake_redis):
        """Test _is_available returns True when Redis is available."""
        registry = RedisRegistry()
        with patch("src.services.websocket.redis_registry.cache_service") as mock_cache:
            mock_cache._redis = fake_redis
            result = await registry._is_available()
            assert result is True

    @pytest.mark.asyncio
    async def test_is_available_without_redis(self, mock_unavailable_registry):
        """Test _is_available returns False when Redis is unavailable."""
        result = await mock_unavailable_registry._is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_register_connection_success(self, registry, fake_redis):
        """Test registering a connection stores data in Redis."""
        connection_id = "conn-123"
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        result = await registry.register_connection(
            connection_id=connection_id,
            user_id=user_id,
            organization_id=org_id,
            worker_id=worker_id,
        )

        assert result is True

        # Verify connection hash was stored
        conn_key = f"ws:conn:{connection_id}"
        conn_data = await fake_redis.hgetall(conn_key)
        assert conn_data["connection_id"] == connection_id
        assert conn_data["user_id"] == str(user_id)
        assert conn_data["organization_id"] == str(org_id)
        assert conn_data["worker_id"] == worker_id
        assert "connected_at" in conn_data

        # Verify user set membership
        user_key = f"ws:user:{user_id}"
        user_connections = await fake_redis.smembers(user_key)
        assert connection_id in user_connections

        # Verify org set membership
        org_key = f"ws:org:{org_id}"
        org_connections = await fake_redis.smembers(org_key)
        assert connection_id in org_connections

        # Verify worker set membership
        worker_key = f"ws:worker:{worker_id}"
        worker_connections = await fake_redis.smembers(worker_key)
        assert connection_id in worker_connections

    @pytest.mark.asyncio
    async def test_register_connection_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test register_connection returns False when Redis is unavailable."""
        result = await mock_unavailable_registry.register_connection(
            connection_id="conn-123",
            user_id=uuid4(),
            organization_id=uuid4(),
            worker_id="worker-1",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_unregister_connection_success(self, registry, fake_redis):
        """Test unregistering a connection removes data from Redis."""
        connection_id = "conn-123"
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        # First register
        await registry.register_connection(
            connection_id=connection_id,
            user_id=user_id,
            organization_id=org_id,
            worker_id=worker_id,
        )

        # Then unregister
        result = await registry.unregister_connection(connection_id)
        assert result is True

        # Verify connection hash was removed
        conn_key = f"ws:conn:{connection_id}"
        conn_data = await fake_redis.hgetall(conn_key)
        assert len(conn_data) == 0

        # Verify user set membership removed
        user_key = f"ws:user:{user_id}"
        user_connections = await fake_redis.smembers(user_key)
        assert connection_id not in user_connections

        # Verify org set membership removed
        org_key = f"ws:org:{org_id}"
        org_connections = await fake_redis.smembers(org_key)
        assert connection_id not in org_connections

    @pytest.mark.asyncio
    async def test_unregister_connection_not_found(self, registry):
        """Test unregistering a non-existent connection returns True."""
        result = await registry.unregister_connection("unknown-conn")
        assert result is True

    @pytest.mark.asyncio
    async def test_unregister_connection_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test unregister_connection returns False when Redis is unavailable."""
        result = await mock_unavailable_registry.unregister_connection("conn-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_connection_success(self, registry, fake_redis):
        """Test getting connection metadata."""
        connection_id = "conn-123"
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        await registry.register_connection(
            connection_id=connection_id,
            user_id=user_id,
            organization_id=org_id,
            worker_id=worker_id,
        )

        result = await registry.get_connection(connection_id)

        assert result is not None
        assert result["connection_id"] == connection_id
        assert result["user_id"] == str(user_id)
        assert result["organization_id"] == str(org_id)
        assert result["worker_id"] == worker_id

    @pytest.mark.asyncio
    async def test_get_connection_not_found(self, registry):
        """Test getting non-existent connection returns None."""
        result = await registry.get_connection("unknown-conn")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_connection_redis_unavailable(self, mock_unavailable_registry):
        """Test get_connection returns None when Redis is unavailable."""
        result = await mock_unavailable_registry.get_connection("conn-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_connections(self, registry):
        """Test getting all connections for a user."""
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        # Register multiple connections for the same user
        await registry.register_connection("conn-1", user_id, org_id, worker_id)
        await registry.register_connection("conn-2", user_id, org_id, worker_id)

        connections = await registry.get_user_connections(user_id)

        assert len(connections) == 2
        conn_ids = [c["connection_id"] for c in connections]
        assert "conn-1" in conn_ids
        assert "conn-2" in conn_ids

    @pytest.mark.asyncio
    async def test_get_user_connections_empty(self, registry):
        """Test getting connections for a user with no connections."""
        user_id = uuid4()
        connections = await registry.get_user_connections(user_id)
        assert connections == []

    @pytest.mark.asyncio
    async def test_get_user_connections_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test get_user_connections returns empty list when Redis unavailable."""
        result = await mock_unavailable_registry.get_user_connections(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_org_connections(self, registry):
        """Test getting all connections for an organization."""
        user1_id = uuid4()
        user2_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        # Register connections for different users in the same org
        await registry.register_connection("conn-1", user1_id, org_id, worker_id)
        await registry.register_connection("conn-2", user2_id, org_id, worker_id)

        connections = await registry.get_org_connections(org_id)

        assert len(connections) == 2
        conn_ids = [c["connection_id"] for c in connections]
        assert "conn-1" in conn_ids
        assert "conn-2" in conn_ids

    @pytest.mark.asyncio
    async def test_get_org_connections_empty(self, registry):
        """Test getting connections for an org with no connections."""
        org_id = uuid4()
        connections = await registry.get_org_connections(org_id)
        assert connections == []

    @pytest.mark.asyncio
    async def test_get_org_connections_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test get_org_connections returns empty list when Redis unavailable."""
        result = await mock_unavailable_registry.get_org_connections(uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_get_worker_connections(self, registry):
        """Test getting all connection IDs for a worker."""
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        await registry.register_connection("conn-1", user_id, org_id, worker_id)
        await registry.register_connection("conn-2", user_id, org_id, worker_id)

        connection_ids = await registry.get_worker_connections(worker_id)

        assert len(connection_ids) == 2
        assert "conn-1" in connection_ids
        assert "conn-2" in connection_ids

    @pytest.mark.asyncio
    async def test_get_worker_connections_empty(self, registry):
        """Test getting connections for a worker with no connections."""
        connection_ids = await registry.get_worker_connections("unknown-worker")
        assert connection_ids == []

    @pytest.mark.asyncio
    async def test_get_worker_connections_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test get_worker_connections returns empty list when Redis unavailable."""
        result = await mock_unavailable_registry.get_worker_connections("worker-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_refresh_connection_success(self, registry, fake_redis):
        """Test refreshing connection TTL."""
        connection_id = "conn-123"
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        await registry.register_connection(
            connection_id=connection_id,
            user_id=user_id,
            organization_id=org_id,
            worker_id=worker_id,
        )

        result = await registry.refresh_connection(connection_id)
        assert result is True

        # Verify TTL was refreshed (should be close to CONNECTION_TTL)
        conn_key = f"ws:conn:{connection_id}"
        ttl = await fake_redis.ttl(conn_key)
        assert ttl > 0
        assert ttl <= RedisRegistry.CONNECTION_TTL

    @pytest.mark.asyncio
    async def test_refresh_connection_not_found(self, registry):
        """Test refreshing a non-existent connection returns False."""
        result = await registry.refresh_connection("unknown-conn")
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_connection_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test refresh_connection returns False when Redis unavailable."""
        result = await mock_unavailable_registry.refresh_connection("conn-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_worker_connections(self, registry):
        """Test cleaning up all connections for a worker."""
        user_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        await registry.register_connection("conn-1", user_id, org_id, worker_id)
        await registry.register_connection("conn-2", user_id, org_id, worker_id)

        removed = await registry.cleanup_worker_connections(worker_id)

        assert removed == 2

        # Verify connections are gone
        conn1 = await registry.get_connection("conn-1")
        conn2 = await registry.get_connection("conn-2")
        assert conn1 is None
        assert conn2 is None

    @pytest.mark.asyncio
    async def test_cleanup_worker_connections_empty(self, registry):
        """Test cleaning up connections for a worker with no connections."""
        removed = await registry.cleanup_worker_connections("unknown-worker")
        assert removed == 0

    @pytest.mark.asyncio
    async def test_cleanup_worker_connections_redis_unavailable(
        self, mock_unavailable_registry
    ):
        """Test cleanup_worker_connections returns 0 when Redis unavailable."""
        result = await mock_unavailable_registry.cleanup_worker_connections("worker-1")
        assert result == 0

    @pytest.mark.asyncio
    async def test_multi_session_support(self, registry):
        """Test that a user can have multiple connections (multi-session)."""
        user_id = uuid4()
        org_id = uuid4()

        # Register multiple connections for the same user (different devices/tabs)
        await registry.register_connection("conn-1", user_id, org_id, "worker-1")
        await registry.register_connection("conn-2", user_id, org_id, "worker-2")
        await registry.register_connection("conn-3", user_id, org_id, "worker-1")

        connections = await registry.get_user_connections(user_id)
        assert len(connections) == 3

    @pytest.mark.asyncio
    async def test_connection_isolation_between_users(self, registry):
        """Test that connections are properly isolated between users."""
        user1_id = uuid4()
        user2_id = uuid4()
        org_id = uuid4()
        worker_id = "worker-1"

        await registry.register_connection("conn-1", user1_id, org_id, worker_id)
        await registry.register_connection("conn-2", user2_id, org_id, worker_id)

        user1_connections = await registry.get_user_connections(user1_id)
        user2_connections = await registry.get_user_connections(user2_id)

        assert len(user1_connections) == 1
        assert len(user2_connections) == 1
        assert user1_connections[0]["connection_id"] == "conn-1"
        assert user2_connections[0]["connection_id"] == "conn-2"

    @pytest.mark.asyncio
    async def test_connection_isolation_between_orgs(self, registry):
        """Test that connections are properly isolated between organizations."""
        user_id = uuid4()
        org1_id = uuid4()
        org2_id = uuid4()
        worker_id = "worker-1"

        # Note: In practice a user belongs to one org at a time in the connection,
        # but testing the registry's org isolation
        await registry.register_connection("conn-1", user_id, org1_id, worker_id)
        await registry.register_connection("conn-2", uuid4(), org2_id, worker_id)

        org1_connections = await registry.get_org_connections(org1_id)
        org2_connections = await registry.get_org_connections(org2_id)

        assert len(org1_connections) == 1
        assert len(org2_connections) == 1
        assert org1_connections[0]["connection_id"] == "conn-1"
        assert org2_connections[0]["connection_id"] == "conn-2"


class TestRedisRegistrySingleton:
    """Tests for the global redis_registry singleton."""

    def test_singleton_import(self):
        """Test that redis_registry singleton can be imported."""
        from src.services.websocket.redis_registry import redis_registry

        assert isinstance(redis_registry, RedisRegistry)

    def test_module_import(self):
        """Test importing from the package."""
        from src.services.websocket import RedisRegistry, redis_registry

        assert isinstance(redis_registry, RedisRegistry)


# =============================================================================
# Pub/Sub Listener Resilience Tests
# =============================================================================


class _FakePubSub:
    """Minimal stand-in for redis.asyncio.client.PubSub driving `_pump`.

    `messages` is a script: a dict is yielded as a frame, an exception
    instance is raised, and `None` means "nothing this tick".
    """

    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.subscribed: list[str] = []
        self.closed = False
        self.exhausted = asyncio.Event()

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if not self.messages:
            self.exhausted.set()
            await asyncio.sleep(0.01)
            return None
        item = self.messages.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def subscribe(self, *channels):
        self.subscribed.extend(channels)

    async def unsubscribe(self, *channels):
        pass

    async def aclose(self):
        self.closed = True


def _frame(channel: str, payload: str) -> dict:
    return {"type": "message", "channel": channel, "data": payload}


class TestRedisPubSubListenerResilience:
    """The listener must survive a subscription changing mid-broadcast.

    Regression guard for a defect that silently killed realtime for the whole
    process: `_listen` iterated `self._subscriptions[channel]` directly while
    `await`ing each callback. The await yields, and `subscribe`/`unsubscribe`
    mutate that dict under a lock the listener does not hold — so a WebSocket
    connecting or disconnecting during a broadcast raised
    "dictionary changed size during iteration" FROM THE ITERATOR, which escaped
    the per-callback handler, unwound the listener loop and stopped it with
    `_running=True`. Every connected user stopped receiving live updates, with
    nothing surfaced to any client, until the backend restarted.
    """

    @pytest.mark.asyncio
    async def test_callback_subscribing_mid_broadcast_does_not_kill_the_pump(self):
        pubsub = RedisPubSub()
        channel = "ws:org:test"
        delivered: list[str] = []

        async def quiet(message):
            delivered.append("quiet")

        # A callback that mutates the very dict being iterated — exactly what a
        # WebSocket connecting mid-broadcast does.
        async def greedy(message):
            delivered.append("greedy")
            pubsub._subscriptions[channel][f"late-{len(delivered)}"] = quiet

        pubsub._subscriptions[channel] = {"a": greedy, "b": quiet}
        pubsub._pubsub = _FakePubSub([_frame(channel, '{"type": "x"}')])
        pubsub._running = True

        task = asyncio.create_task(pubsub._pump())
        await asyncio.wait_for(pubsub._pubsub.exhausted.wait(), timeout=1)
        pubsub._running = False
        await asyncio.wait_for(task, timeout=1)

        # Both original callbacks ran, and the pump returned cleanly rather
        # than raising RuntimeError out of the iterator.
        assert delivered == ["greedy", "quiet"]
        # …and the newly-added subscriber is present for the NEXT message.
        assert len(pubsub._subscriptions[channel]) == 3

    @pytest.mark.asyncio
    async def test_unsubscribing_mid_broadcast_does_not_kill_the_pump(self):
        pubsub = RedisPubSub()
        channel = "ws:org:test"
        delivered: list[str] = []

        async def other(message):
            delivered.append("other")

        async def leaver(message):
            delivered.append("leaver")
            # A disconnecting client removes its own callback.
            pubsub._subscriptions[channel].pop("b", None)

        pubsub._subscriptions[channel] = {"a": leaver, "b": other}
        pubsub._pubsub = _FakePubSub([_frame(channel, '{"type": "x"}')])
        pubsub._running = True

        task = asyncio.create_task(pubsub._pump())
        await asyncio.wait_for(pubsub._pubsub.exhausted.wait(), timeout=1)
        pubsub._running = False
        await asyncio.wait_for(task, timeout=1)

        # The snapshot means the removed callback still receives THIS message —
        # a harmless stale delivery — and crucially nothing raised.
        assert delivered == ["leaver", "other"]
        assert "b" not in pubsub._subscriptions[channel]

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_stop_delivery_to_others(self):
        pubsub = RedisPubSub()
        channel = "ws:org:test"
        delivered: list[str] = []

        async def broken(message):
            raise ValueError("consumer blew up")

        async def healthy(message):
            delivered.append("healthy")

        pubsub._subscriptions[channel] = {"a": broken, "b": healthy}
        pubsub._pubsub = _FakePubSub([_frame(channel, '{"type": "x"}')])
        pubsub._running = True

        task = asyncio.create_task(pubsub._pump())
        await asyncio.wait_for(pubsub._pubsub.exhausted.wait(), timeout=1)
        pubsub._running = False
        await asyncio.wait_for(task, timeout=1)

        assert delivered == ["healthy"]

    @pytest.mark.asyncio
    async def test_listener_survives_a_pump_crash_and_reconnects(self, monkeypatch):
        """A non-ConnectionError failure used to end realtime permanently.

        The old loop caught only CancelledError and redis.ConnectionError, so
        anything else unwound `while self._running` while `_running` stayed
        True — and `subscribe()`'s `if not self._running` guard then refused to
        start a replacement. The supervisor must instead back off, reconnect
        and keep pumping.
        """
        pubsub = RedisPubSub()
        channel = "ws:org:test"
        pubsub._subscriptions[channel] = {"a": AsyncMock()}

        monkeypatch.setattr(RedisPubSub, "_LISTEN_BACKOFF_BASE", 0.001)
        monkeypatch.setattr(RedisPubSub, "_LISTEN_BACKOFF_MAX", 0.001)

        # First pump raises something the old handler did not cover.
        pubsub._pubsub = _FakePubSub([RuntimeError("dict changed size")])

        replacement = _FakePubSub()
        reconnected = asyncio.Event()

        async def fake_reconnect():
            pubsub._pubsub = replacement
            reconnected.set()
            return True

        pubsub._reconnect = fake_reconnect  # type: ignore[method-assign]

        pubsub._spawn_listener()
        await asyncio.wait_for(reconnected.wait(), timeout=2)
        await asyncio.wait_for(replacement.exhausted.wait(), timeout=2)

        # Still alive and pumping on the rebuilt connection.
        assert pubsub._running is True
        assert pubsub._listener_task is not None
        assert pubsub._listener_task.done() is False

        await pubsub.stop()
        assert pubsub._running is False

    @pytest.mark.asyncio
    async def test_reconnect_rebuilds_pubsub_and_replays_all_channels(self):
        """`_pubsub` must actually be rebuilt after a connection error.

        The old handler slept 1s on redis.ConnectionError and reused the dead
        PubSub forever; nothing but `stop()` ever set `_pubsub = None`, so the
        recovery branch in `subscribe()` was unreachable and a Redis restart
        left the worker spinning on a dead socket.
        """
        pubsub = RedisPubSub()
        dead = _FakePubSub()
        pubsub._pubsub = dead
        pubsub._subscriptions = {"ws:user:a": {"c1": AsyncMock()}, "ws:platform": {}}

        fresh = _FakePubSub()
        fake_redis_client = MagicMock()
        fake_redis_client.pubsub = MagicMock(return_value=fresh)
        pubsub._get_redis = lambda: fake_redis_client  # type: ignore[method-assign]

        assert await pubsub._reconnect() is True

        assert dead.closed is True
        assert pubsub._pubsub is fresh
        assert sorted(fresh.subscribed) == ["ws:platform", "ws:user:a"]

    @pytest.mark.asyncio
    async def test_reconnect_reports_failure_without_a_redis_client(self):
        pubsub = RedisPubSub()
        pubsub._pubsub = _FakePubSub()
        pubsub._get_redis = lambda: None  # type: ignore[method-assign]

        assert await pubsub._reconnect() is False
        # Left as None so `subscribe()`'s recovery branch can rebuild it.
        assert pubsub._pubsub is None

    @pytest.mark.asyncio
    async def test_watchdog_restarts_a_listener_that_dies_with_subscribers(self):
        pubsub = RedisPubSub()
        pubsub._subscriptions = {"ws:platform": {"c1": AsyncMock()}}
        pubsub._pubsub = _FakePubSub()

        pubsub._spawn_listener()
        first = pubsub._listener_task
        assert first is not None

        # Kill the listener the way an unanticipated cancellation would, but
        # without going through stop() — the watchdog must notice.
        pubsub._running = False
        await asyncio.wait_for(first, timeout=2)
        await asyncio.sleep(0)  # let the done-callback run

        assert pubsub._listener_task is not None
        assert pubsub._listener_task is not first
        assert pubsub._running is True

        await pubsub.stop()

    @pytest.mark.asyncio
    async def test_watchdog_does_not_resurrect_the_listener_during_stop(self):
        pubsub = RedisPubSub()
        pubsub._subscriptions = {"ws:platform": {"c1": AsyncMock()}}
        pubsub._pubsub = _FakePubSub()

        pubsub._spawn_listener()
        await pubsub.stop()
        await asyncio.sleep(0)

        assert pubsub._running is False
        assert pubsub._listener_task is None
        assert pubsub._subscriptions == {}


class _CountingPubSub(_FakePubSub):
    """Records how many listener tasks are inside `get_message` at once.

    Two `_listen` tasks on one PubSub socket is the failure mode of a listener
    spawned off a flag instead of off the task; redis-py's PubSub is not safe
    for concurrent readers.
    """

    def __init__(self):
        super().__init__()
        self.inflight = 0
        self.max_inflight = 0

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            return await super().get_message(ignore_subscribe_messages, timeout)
        finally:
            self.inflight -= 1


def _live_listen_tasks() -> list[asyncio.Task]:
    """Every unfinished `RedisPubSub._listen` task on this loop, tracked or not.

    Deliberately does NOT go through `_listener_task`: the whole point of the
    orphan defect was that the service dropped its own reference, so a check
    that trusts that reference cannot see the leak.
    """
    live = []
    for task in asyncio.all_tasks():
        coro = task.get_coro()
        if (
            "RedisPubSub._listen" in getattr(coro, "__qualname__", "")
            and not task.done()
        ):
            live.append(task)
    return live


class TestRedisPubSubShutdownRaces:
    """`stop()` must actually stop the service, whatever a client is doing.

    `stop()` used to be the ONLY method that mutated `_pubsub`,
    `_subscriptions` and `_listener_task` without holding `_get_lock()` — and it
    suspended half-way through, at `await self._listener_task`. A `subscribe()`
    landing in that window took the lock, cleared `_stopping`, spawned a fresh
    listener and opened a fresh Redis pub/sub connection; `stop()` then resumed
    and blindly assigned `_listener_task = None`, dropping the reference, and
    the identity guard in `_on_listener_done` guaranteed the orphan was never
    noticed. `stop()` returned reporting `_running=True` with a live listener
    and an unclosed connection — which `main.py` then tears down underneath it.

    Reachable on any rolling restart with a handshake in flight.
    """

    @pytest.fixture(autouse=True)
    def reset_channel_ns(self):
        with patch("src.services.websocket.redis_pubsub._CHANNEL_NS", ""):
            yield

    @staticmethod
    def _redis_returning(pubsubs: list):
        """A Redis client handing out a fresh fake PubSub per `pubsub()` call."""
        client = MagicMock()

        def make():
            fresh = _FakePubSub()
            pubsubs.append(fresh)
            return fresh

        client.pubsub = MagicMock(side_effect=make)
        client.ping = AsyncMock(return_value=True)
        return client

    @pytest.mark.asyncio
    async def test_stop_is_not_defeated_by_a_subscribe_in_its_suspension(self):
        """The race, made deterministic with a gate rather than left to luck."""
        pubsubs: list[_FakePubSub] = []
        client = self._redis_returning(pubsubs)
        pubsub = RedisPubSub()
        pubsub._get_redis = lambda: client  # type: ignore[method-assign]

        before = set(_live_listen_tasks())
        assert await pubsub.subscribe("ws:user:a", AsyncMock(), callback_id="a")
        first = pubsub._listener_task
        assert first is not None

        # Park a reconnecting client's subscribe() just before it takes the
        # lock, then release it only once stop() is suspended on the listener.
        gate = asyncio.Event()
        real_is_available = pubsub._is_available

        async def gated_is_available():
            await gate.wait()
            return await real_is_available()

        pubsub._is_available = gated_is_available  # type: ignore[method-assign]

        racer = asyncio.create_task(
            pubsub.subscribe("ws:user:b", AsyncMock(), callback_id="b")
        )
        await asyncio.sleep(0)  # park the racer at the gate

        stopper = asyncio.create_task(pubsub.stop())
        while not first.done():
            await asyncio.sleep(0)
        assert not stopper.done(), "stop() must still be mid-shutdown"

        gate.set()
        await asyncio.wait_for(asyncio.gather(stopper, racer), timeout=5)
        await asyncio.sleep(0)

        orphans = [t for t in _live_listen_tasks() if t not in before]
        for task in orphans:  # never leak into the rest of the suite
            task.cancel()

        assert orphans == [], "a listener task survived stop()"
        assert pubsub._running is False, "stop() returned reporting it is running"
        assert pubsub._listener_task is None
        assert pubsub._pubsub is None
        assert pubsub._subscriptions == {}
        assert all(
            p.closed for p in pubsubs
        ), "a pub/sub connection opened during shutdown was never closed"

    @pytest.mark.asyncio
    async def test_subscribe_is_refused_while_shutting_down(self):
        """Refusing is the honest answer, and it is what keeps stop() final.

        The caller's socket is about to die with the process; `main.py` closes
        the Redis pool on the next line. Rebuilding the connection here is
        exactly how a handshake used to outlive shutdown.
        """
        pubsubs: list[_FakePubSub] = []
        client = self._redis_returning(pubsubs)
        pubsub = RedisPubSub()
        pubsub._get_redis = lambda: client  # type: ignore[method-assign]

        assert await pubsub.subscribe("ws:platform", AsyncMock(), callback_id="a")
        await pubsub.stop()

        assert (
            await pubsub.subscribe("ws:platform", AsyncMock(), callback_id="b") is False
        )
        assert pubsub._subscriptions == {}
        assert pubsub._listener_task is None
        assert _live_listen_tasks() == []

    @pytest.mark.asyncio
    async def test_set_redis_rearms_the_service_after_a_stop(self):
        """A process that starts a new lifespan must get a working service.

        `set_redis` is the lifespan's start hook, so it is what lifts the
        shutdown latch — otherwise the refusal above would be permanent.
        """
        pubsubs: list[_FakePubSub] = []
        client = self._redis_returning(pubsubs)
        pubsub = RedisPubSub()
        pubsub._get_redis = lambda: client  # type: ignore[method-assign]

        await pubsub.subscribe("ws:platform", AsyncMock(), callback_id="a")
        await pubsub.stop()
        assert pubsub._stopping is True

        pubsub.set_redis(client)
        assert pubsub._stopping is False
        assert await pubsub.subscribe("ws:platform", AsyncMock(), callback_id="b")

        await pubsub.stop()

    @pytest.mark.asyncio
    async def test_subscribe_never_stacks_a_second_listener_on_a_live_task(self):
        """`_running` is a request, not a fact.

        It means "the pump should keep draining"; it does not mean "a listener
        exists". Spawning off the flag started a SECOND `_listen` task on top of
        a live one whenever the two disagreed — and then two tasks call
        `get_message` on the same PubSub socket, while `stop()` only ever awaits
        the one it holds in `_listener_task`. Gating on the task itself makes
        that structurally impossible.
        """
        pubsubs: list[_FakePubSub] = []
        client = self._redis_returning(pubsubs)
        pubsub = RedisPubSub()
        pubsub._get_redis = lambda: client  # type: ignore[method-assign]

        counting = _CountingPubSub()
        pubsub._pubsub = counting
        pubsub._subscriptions["ws:platform"] = {"a": AsyncMock()}
        pubsub._spawn_listener()
        first = pubsub._listener_task
        await asyncio.sleep(0.02)

        for _ in range(20):
            # The window: the flag says "not running" while the task is alive.
            pubsub._running = False
            await pubsub.subscribe("ws:platform", AsyncMock(), callback_id="b")
            await asyncio.sleep(0)

        await asyncio.sleep(0.02)
        assert pubsub._listener_task is first, "the listener task was replaced"
        assert len(_live_listen_tasks()) == 1, "a second listener was stacked"
        assert (
            counting.max_inflight == 1
        ), "two listeners read the same PubSub socket concurrently"
        assert pubsub._running is True

        await pubsub.stop()
        assert _live_listen_tasks() == []
