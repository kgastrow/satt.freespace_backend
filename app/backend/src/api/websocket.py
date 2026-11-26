"""
WebSocket API endpoint with JWT authentication.
Handles WebSocket connection lifecycle, heartbeat, and message routing.

Security: Token is sent in the first message after connection (not in URL query
parameter) to prevent exposure in browser history, server logs, and proxy logs.
"""

import asyncio
import json
from typing import Any
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.core.security import decode_token
from src.crud.organization import get_organization_by_id
from src.crud.user import get_user_by_id
from src.database import AsyncSessionLocal
from src.logger.logger import Logger
from src.models.user import SuspensionStatus
from src.services.websocket import connection_manager, redis_pubsub, redis_registry
from src.services.websocket.sender import ConnectionSender


router = APIRouter(tags=["websocket"])

# Worker ID for this process (used in Redis registry)
WORKER_ID = str(uuid.uuid4())

# Maximum size for incoming WebSocket messages (64KB)
MAX_MESSAGE_SIZE = 64 * 1024

# Timeout for receiving auth message after connection (seconds)
AUTH_TIMEOUT_SECONDS = 10

# Allowed message types from clients (after authentication)
ALLOWED_MESSAGE_TYPES = {"ping"}

# Re-validation interval in heartbeats (re-validate every N heartbeats)
REVALIDATION_HEARTBEAT_INTERVAL = 10


async def _handle_pubsub_message(
    sender: ConnectionSender,
) -> Any:
    """
    Create a callback for handling pub/sub messages for a connection.

    Returns an async callback that hands messages to the connection's send
    queue. It deliberately does not touch the socket: the pub/sub listener is
    one task per worker that awaits every subscriber's callback in turn, so a
    callback that blocked on TCP drain would stall realtime delivery for every
    other connection on that worker. `deliver` never touches the socket and
    only suspends while this connection is backlogged, bounded by the sender's
    stall grace. See `services/websocket/sender.py`.
    """

    async def callback(message: dict[str, Any]) -> None:
        await sender.deliver(message)

    return callback


async def _authenticate_websocket(
    websocket: WebSocket,
) -> tuple[str, str] | None:
    """
    Wait for and validate authentication message from client.

    Security: Token is sent in the first message (not URL) to prevent exposure
    in browser history, server logs, and proxy logs.

    Returns:
        tuple of (user_id, organization_id) on success, None on failure
    """
    try:
        # Wait for auth message with timeout
        raw_data = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=AUTH_TIMEOUT_SECONDS,
        )

        # Validate message size
        if len(raw_data) > MAX_MESSAGE_SIZE:
            Logger.warning("Auth message too large: %d bytes", len(raw_data))
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Message too large",
            )
            return None

        # Parse JSON
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            Logger.warning("Invalid JSON in auth message")
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid message format",
            )
            return None

        # Validate message structure
        if not isinstance(data, dict) or data.get("type") != "auth":
            Logger.warning("First message must be auth type")
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="First message must be authentication",
            )
            return None

        token = data.get("token")
        if not token or not isinstance(token, str):
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Token is missing",
            )
            return None

        # Validate JWT token
        try:
            claims = decode_token(token)
        except ValueError as e:
            Logger.warning("WebSocket token validation failed: %s", str(e))
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid authentication token",
            )
            return None

        # SECURITY: Enforce the token type. Only genuine access tokens and
        # impersonation tokens may authenticate a WebSocket connection. The
        # pre-2FA interstitial token (purpose "2fa_verification") and other
        # non-access tokens carry a distinct type/purpose and must be rejected,
        # mirroring get_current_user in deps.py.
        if claims.get("type") not in ("access", "impersonation"):
            Logger.warning("WebSocket rejected non-access token type")
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid authentication token",
            )
            return None

        user_id = claims.get("user_id")
        organization_id = claims.get("organization_id")

        if not user_id or not organization_id:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token - missing user or organization",
            )
            return None

        return (user_id, organization_id)

    except asyncio.TimeoutError:
        Logger.warning("WebSocket auth timeout")
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication timeout",
        )
        return None
    except WebSocketDisconnect:
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
) -> None:
    """
    WebSocket endpoint with JWT authentication.

    Security: Token is sent in the first message after connection (not in URL
    query parameter) to prevent exposure in browser history, server logs, and
    proxy logs.

    Connection lifecycle:
    1. Accept WebSocket connection
    2. Wait for auth message with JWT token (10s timeout)
    3. Validate JWT token and extract user/org info
    4. Verify user exists and organization is active
    5. Register connection with ConnectionManager and RedisRegistry
    6. Subscribe to user, org, and platform channels via RedisPubSub
    7. Send auth_success confirmation (connection fully ready)
    8. Handle incoming messages (ping/pong heartbeat)
    9. Clean up on disconnect

    Returns:
        Closes with 1008: Invalid/missing token or auth timeout
        Closes with 4003: Inactive organization
    """
    # Accept connection first, then authenticate via message
    await websocket.accept()

    # Wait for and validate auth message
    auth_result = await _authenticate_websocket(websocket)
    if auth_result is None:
        return

    user_id, organization_id = auth_result

    # Verify organization and user exist - use scoped session for auth only
    # Check validations and store error info
    error_code = None
    error_reason = None

    async with AsyncSessionLocal() as session:
        organization = await get_organization_by_id(session, organization_id)
        if not organization:
            error_code = status.WS_1008_POLICY_VIOLATION
            error_reason = "Organization not found"
        elif not organization.is_active:
            error_code = 4003
            error_reason = "Organization is not active"
        else:
            user = await get_user_by_id(session, user_id, organization_id)
            if not user:
                error_code = status.WS_1008_POLICY_VIOLATION
                error_reason = "User not found"
            elif user.suspension_status == SuspensionStatus.SUSPENDED:
                error_code = status.WS_1008_POLICY_VIOLATION
                error_reason = "User account is suspended"
    # Session is now closed - no longer holding transaction open

    # Reject connection if validation failed
    if error_code is not None:
        await websocket.close(code=error_code, reason=error_reason)
        return

    # Generate unique connection ID
    connection_id = str(uuid.uuid4())
    user_uuid = uuid.UUID(user_id)
    org_uuid = uuid.UUID(organization_id)

    # Register connection locally
    await connection_manager.connect(websocket, connection_id, user_uuid, org_uuid)

    # Bound BEFORE the try, because the finally block below references it.
    # Assigning it inside means an early failure — a Redis blip in
    # register_connection, or a client vanishing before auth_success is sent —
    # raises NameError from the finally, masking the real exception, skipping
    # the whole teardown and leaking the pub/sub callback for the lifetime of
    # the process.
    sender = ConnectionSender(websocket, connection_id)

    # Track heartbeat count for periodic re-validation
    heartbeat_count = 0

    # Everything from here is inside the try. Registration, the sender task,
    # the channel subscriptions and the auth_success send can each raise — a
    # client that vanishes in the milliseconds between auth and confirmation
    # is most likely during exactly the reconnect storm this work exists to
    # prevent. Outside the try, that left an orphaned writer task and a
    # pub/sub callback registered forever.
    try:
        # Register connection in Redis
        await redis_registry.register_connection(
            connection_id=connection_id,
            user_id=user_uuid,
            organization_id=org_uuid,
            worker_id=WORKER_ID,
        )

        # Create message callback for this connection
        sender.start()
        pubsub_callback = await _handle_pubsub_message(sender)

        # Subscribe to user, org, and platform channels
        await redis_pubsub.subscribe_for_connection(
            user_id=user_uuid,
            organization_id=org_uuid,
            callback=pubsub_callback,
            connection_id=connection_id,
        )

        # Send auth success confirmation
        await websocket.send_json({"type": "auth_success"})

        Logger.info(
            "WebSocket connection established: connection_id=%s user_id=%s org_id=%s",
            connection_id,
            user_id,
            organization_id,
        )

        # Message handling loop
        while True:
            try:
                # VULN-ws-004: Receive raw text to validate message size
                raw_data = await websocket.receive_text()

                # Validate message size
                if len(raw_data) > MAX_MESSAGE_SIZE:
                    Logger.warning(
                        "Message too large from connection %s: %d bytes",
                        connection_id,
                        len(raw_data),
                    )
                    continue

                # Parse JSON
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    Logger.warning(
                        "Invalid JSON from connection %s",
                        connection_id,
                    )
                    continue

                # Validate message structure
                if not isinstance(data, dict) or "type" not in data:
                    Logger.warning(
                        "Invalid message format from connection %s",
                        connection_id,
                    )
                    continue

                # Validate message type
                message_type = data.get("type")
                if message_type not in ALLOWED_MESSAGE_TYPES:
                    Logger.warning(
                        "Unknown message type from connection %s: %s",
                        connection_id,
                        message_type,
                    )
                    continue

                # Handle ping/pong heartbeat
                if message_type == "ping":
                    heartbeat_count += 1

                    # VULN-ws-003: Periodic re-validation during long-lived connections
                    if heartbeat_count % REVALIDATION_HEARTBEAT_INTERVAL == 0:
                        async with AsyncSessionLocal() as session:
                            user = await get_user_by_id(
                                session, str(user_uuid), str(org_uuid)
                            )
                            if (
                                not user
                                or user.suspension_status == SuspensionStatus.SUSPENDED
                            ):
                                Logger.info(
                                    "Access revoked for connection %s: user suspended or not found",
                                    connection_id,
                                )
                                await websocket.close(
                                    code=4003, reason="Access revoked"
                                )
                                break
                            org = await get_organization_by_id(session, str(org_uuid))
                            if not org or not org.is_active:
                                Logger.info(
                                    "Access revoked for connection %s: organization inactive",
                                    connection_id,
                                )
                                await websocket.close(
                                    code=4003, reason="Organization inactive"
                                )
                                break

                    await websocket.send_json({"type": "pong"})
                    # Refresh Redis TTL on heartbeat
                    await redis_registry.refresh_connection(connection_id)

            except WebSocketDisconnect:
                break
            except Exception as e:
                Logger.warning(
                    "Error processing WebSocket message for connection %s: %s",
                    connection_id,
                    str(e),
                )
                # Continue listening for messages on non-fatal errors
                continue

    finally:
        # Clean up on disconnect
        Logger.info(
            "WebSocket connection closed: connection_id=%s user_id=%s org_id=%s",
            connection_id,
            user_id,
            organization_id,
        )

        # Unsubscribe FIRST. Stopping the writer first left this connection's
        # callback registered through `sender.stop()` and all three UNSUBSCRIBE
        # round-trips, so every frame arriving in that window — on the org and
        # platform channels, which are still subscribed while the user channel
        # is being torn down — was handed to a sender whose writer was already
        # cancelled: queued, never written, silently discarded, and once 64 had
        # piled up, a detached `_force_close` task fired against an
        # already-dead socket. Dropping the callback first closes that window:
        # nothing is offered to a writer that is about to be stopped.
        await redis_pubsub.unsubscribe_for_connection(
            user_id=user_uuid,
            organization_id=org_uuid,
            connection_id=connection_id,
        )

        # Now that no more frames can arrive, stop the writer.
        await sender.stop()

        # Unregister from Redis
        await redis_registry.unregister_connection(connection_id)

        # Unregister from local connection manager
        await connection_manager.disconnect(connection_id)
