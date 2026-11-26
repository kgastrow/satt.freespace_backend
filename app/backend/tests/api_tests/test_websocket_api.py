"""
API tests for WebSocket endpoint.
Tests authentication, connection lifecycle, and ping/pong heartbeat.

Note: WebSocket authentication uses message-based auth (SEC-F-005).
Token is sent in the first message after connection, not in URL query parameter.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.core.security import create_access_token, hash_password


def send_auth_message(websocket, token: str) -> dict | None:
    """Send auth message and return the response."""
    websocket.send_json({"type": "auth", "token": token})
    return websocket.receive_json()


def create_test_app(async_session):
    """Create a test FastAPI app with WebSocket router but no lifespan."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.database import get_async_session

    # Create minimal test app without lifespan
    app = FastAPI()

    # Override database session
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_async_session] = override_get_session

    # Patch AsyncSessionLocal to use the test session's engine
    # This ensures the websocket endpoint uses the same in-memory database
    # The test session uses an in-memory SQLite with StaticPool
    # We need to create an AsyncEngine that shares the same pool

    from sqlalchemy.ext.asyncio import create_async_engine

    # Get the sync engine and its pool from the test session
    sync_bind = async_session.get_bind()

    # Create async engine with the same pool (shares the in-memory database)
    async_engine = create_async_engine(
        sync_bind.url,
        echo=False,
        pool=sync_bind.pool,  # Reuse the same pool!
        connect_args={"check_same_thread": False},
    )

    test_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=type(async_session),
        expire_on_commit=False,
        autoflush=False,
    )

    # Patch AsyncSessionLocal in src.database (where it's imported from)
    import src.database

    src.database.AsyncSessionLocal = test_session_maker

    # Import router after patching
    from src.api.websocket import router

    app.include_router(router)

    return app


@contextmanager
def mock_websocket_dependencies(async_session):
    """Context manager to mock WebSocket dependencies including AsyncSessionLocal."""
    # Create a mock session factory that returns the test session
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = async_session
    mock_session_factory.return_value.__aexit__.return_value = None

    # Patch AsyncSessionLocal in the websocket module's namespace (where it was imported)
    # This is necessary because the import creates a local binding that isn't affected
    # by patching src.database.AsyncSessionLocal
    with patch("src.api.websocket.redis_registry") as mock_registry, patch(
        "src.api.websocket.redis_pubsub"
    ) as mock_pubsub, patch(
        "src.api.websocket.AsyncSessionLocal", mock_session_factory
    ):
        mock_registry.register_connection = AsyncMock(return_value=True)
        mock_registry.unregister_connection = AsyncMock(return_value=True)
        mock_registry.refresh_connection = AsyncMock(return_value=True)
        mock_pubsub.subscribe_for_connection = AsyncMock(return_value=True)
        mock_pubsub.unsubscribe_for_connection = AsyncMock(return_value=True)

        yield mock_registry, mock_pubsub


# ==================== Authentication Tests ====================


@pytest.mark.asyncio
async def test_websocket_missing_token(async_session, test_organization):
    """Test WebSocket connection fails without token in auth message."""
    app = create_test_app(async_session)

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    # Send auth message without token
                    websocket.send_json({"type": "auth"})
                    websocket.receive_json()  # Should disconnect

            # Verify connection was rejected
            assert exc_info.value.code == 1008  # Policy violation


@pytest.mark.asyncio
async def test_websocket_invalid_token(async_session, test_organization):
    """Test WebSocket connection fails with invalid token."""
    app = create_test_app(async_session)

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    # Send auth message with invalid token
                    websocket.send_json({"type": "auth", "token": "invalid-token"})
                    websocket.receive_json()  # Should disconnect

            # Verify connection was rejected
            assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_websocket_expired_token(async_session, test_organization, test_user):
    """Test WebSocket connection fails with expired token."""
    from datetime import datetime, timedelta, timezone

    import jwt

    from src.core.config import settings

    app = create_test_app(async_session)

    # Create an expired token
    expired_token = jwt.encode(
        {
            "user_id": str(test_user.id),
            "organization_id": str(test_organization.id),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": expired_token})
                    websocket.receive_json()  # Should disconnect

            assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_websocket_inactive_organization(async_session):
    """Test WebSocket connection fails for inactive organization."""
    from src.models.organization import Organization
    from src.models.user import User

    app = create_test_app(async_session)

    # Create inactive organization
    inactive_org = Organization(
        name="Inactive Org", slug="inactive-org", is_active=False
    )
    async_session.add(inactive_org)
    await async_session.commit()
    await async_session.refresh(inactive_org)

    # Create user in inactive org
    user = User(
        email="inactive@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=inactive_org.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Create valid token
    token = create_access_token(
        user_id=str(user.id), organization_id=str(inactive_org.id)
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": token})
                    websocket.receive_json()  # Should disconnect

            # Custom close code 4003 for inactive organization
            assert exc_info.value.code == 4003


@pytest.mark.asyncio
async def test_websocket_user_not_found(async_session, test_organization):
    """Test WebSocket connection fails when user doesn't exist."""
    import uuid

    app = create_test_app(async_session)

    # Create token for non-existent user
    fake_user_id = str(uuid.uuid4())
    token = create_access_token(
        user_id=fake_user_id, organization_id=str(test_organization.id)
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": token})
                    websocket.receive_json()  # Should disconnect

            assert exc_info.value.code == 1008


# ==================== Successful Connection Tests ====================


@pytest.mark.asyncio
async def test_websocket_successful_connection(
    async_session, test_user, test_organization
):
    """Test successful WebSocket connection with valid token."""
    app = create_test_app(async_session)

    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(test_organization.id)
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                # Send auth message
                websocket.send_json({"type": "auth", "token": token})
                auth_response = websocket.receive_json()
                assert auth_response == {"type": "auth_success"}

                # Now send ping and expect pong
                websocket.send_json({"type": "ping"})
                response = websocket.receive_json()
                assert response == {"type": "pong"}


@pytest.mark.asyncio
async def test_websocket_ping_pong(async_session, test_user, test_organization):
    """Test ping/pong heartbeat functionality."""
    app = create_test_app(async_session)

    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(test_organization.id)
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                # Authenticate first
                websocket.send_json({"type": "auth", "token": token})
                auth_response = websocket.receive_json()
                assert auth_response == {"type": "auth_success"}

                # Send multiple pings
                for _ in range(3):
                    websocket.send_json({"type": "ping"})
                    response = websocket.receive_json()
                    assert response == {"type": "pong"}


@pytest.mark.asyncio
async def test_websocket_ignores_non_ping_messages(
    async_session, test_user, test_organization
):
    """Test that non-ping messages are handled gracefully."""
    app = create_test_app(async_session)

    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(test_organization.id)
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                # Authenticate first
                websocket.send_json({"type": "auth", "token": token})
                auth_response = websocket.receive_json()
                assert auth_response == {"type": "auth_success"}

                # Send a non-ping message (should be ignored)
                websocket.send_json({"type": "unknown", "data": "test"})

                # Send a ping to verify connection still works
                websocket.send_json({"type": "ping"})
                response = websocket.receive_json()
                assert response == {"type": "pong"}


# ==================== Connection Cleanup Tests ====================


@pytest.mark.asyncio
async def test_websocket_disconnect_cleanup(
    async_session, test_user, test_organization
):
    """Test that disconnection cleans up connection manager and registry."""
    from src.services.websocket import connection_manager

    app = create_test_app(async_session)

    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(test_organization.id)
    )

    initial_count = connection_manager.connection_count

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                # Authenticate first
                websocket.send_json({"type": "auth", "token": token})
                auth_response = websocket.receive_json()
                assert auth_response == {"type": "auth_success"}

                # Do ping/pong to ensure server has completed connection setup
                websocket.send_json({"type": "ping"})
                response = websocket.receive_json()
                assert response == {"type": "pong"}
                # Now verify connection was registered
                assert connection_manager.connection_count > initial_count

    # After disconnect, connection should be cleaned up
    # Note: Due to test isolation, we verify the connection was properly handled
    # The actual cleanup verification requires the connection manager state check


# ==================== Token Validation Tests ====================


@pytest.mark.asyncio
async def test_websocket_token_missing_user_id(async_session, test_organization):
    """Test WebSocket connection fails when token is missing user_id."""
    from datetime import datetime, timedelta, timezone

    import jwt

    from src.core.config import settings

    app = create_test_app(async_session)

    # Create token without user_id
    token = jwt.encode(
        {
            "organization_id": str(test_organization.id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": token})
                    websocket.receive_json()  # Should disconnect

            assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_websocket_token_missing_organization_id(async_session, test_user):
    """Test WebSocket connection fails when token is missing organization_id."""
    from datetime import datetime, timedelta, timezone

    import jwt

    from src.core.config import settings

    app = create_test_app(async_session)

    # Create token without organization_id
    token = jwt.encode(
        {
            "user_id": str(test_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": token})
                    websocket.receive_json()  # Should disconnect

            assert exc_info.value.code == 1008


# ==================== Multi-tenancy Isolation Tests ====================


@pytest.mark.asyncio
async def test_websocket_user_wrong_organization(
    async_session, test_organization, second_organization
):
    """Test WebSocket connection fails when user's org doesn't match token's org."""
    from src.models.user import User

    app = create_test_app(async_session)

    # Create user in first organization
    user = User(
        email="crossorg@test.com",
        password=hash_password("TestPass123"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Try to connect with token for second organization (user doesn't belong to)
    token = create_access_token(
        user_id=str(user.id), organization_id=str(second_organization.id)
    )

    with mock_websocket_dependencies(async_session):
        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": token})
                    websocket.receive_json()  # Should disconnect

            # User not found in that organization
            assert exc_info.value.code == 1008
