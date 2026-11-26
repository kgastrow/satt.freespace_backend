# WebSocket Patterns

## Overview

The application uses WebSockets for real-time bidirectional communication between the server and connected clients. The implementation is built on FastAPI's WebSocket support with Redis pub/sub for cross-worker message routing in multi-process deployments.

## Architecture

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| WebSocket API | `src/api/websocket.py` | Connection endpoint, authentication, message handling |
| ConnectionManager | `src/services/websocket/connection_manager.py` | Local worker connection tracking |
| RedisRegistry | `src/services/websocket/redis_registry.py` | Cross-worker connection tracking |
| RedisPubSub | `src/services/websocket/redis_pubsub.py` | Cross-worker message routing |
| MessageBroadcaster | `src/services/websocket/broadcaster.py` | High-level API for sending messages |
| Serializers | `src/serialisers/websocket.py` | Pydantic models for messages |

### Multi-Worker Architecture

```
                    +------------------+
                    |   Redis Server   |
                    | (Pub/Sub + Hash) |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
+--------v-------+   +-------v--------+   +------v---------+
|   Worker 1     |   |   Worker 2     |   |   Worker 3     |
| ConnectionMgr  |   | ConnectionMgr  |   | ConnectionMgr  |
|  (local WS)    |   |  (local WS)    |   |  (local WS)    |
+----------------+   +----------------+   +----------------+
```

Each worker maintains:
- **ConnectionManager**: Local in-memory tracking of WebSocket connections
- **RedisRegistry**: Registers connections in Redis for cross-worker discovery
- **RedisPubSub**: Subscribes to channels and forwards messages to local connections

## Connection Handling

### Endpoint

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session: AsyncSession = Depends(get_async_session)):
    ...
```

### Connection Lifecycle

1. **Accept**: Server accepts the WebSocket connection
2. **Authenticate**: Wait for auth message with JWT token (10s timeout)
3. **Validate**: Verify JWT, check user exists, organization is active
4. **Confirm**: Send `auth_success` message to client
5. **Register**: Add to ConnectionManager and RedisRegistry
6. **Subscribe**: Subscribe to user, org, and platform pub/sub channels
7. **Message Loop**: Handle ping/pong heartbeats, forward server messages
8. **Cleanup**: Unsubscribe, unregister on disconnect

### Connection Registration (Redis)

```python
# Redis key structure
ws:conn:{connection_id}  -> Hash with connection metadata
ws:user:{user_id}        -> Set of connection_ids for user
ws:org:{org_id}          -> Set of connection_ids for organization
ws:worker:{worker_id}    -> Set of connection_ids for worker

# TTL: 2 hours (refreshed on heartbeat)
```

## Authentication

### Security Design

**Important**: Tokens are sent in the first message after connection, NOT in URL query parameters. This prevents token exposure in:
- Browser history
- Server access logs
- Proxy logs
- Referrer headers

### Authentication Flow

```
Client                          Server
  |                               |
  |------ WebSocket Connect ----->|
  |                               | Accept connection
  |<---- Connection Accepted -----|
  |                               |
  |--- {"type": "auth", "token": "..."}-->|
  |                               | Validate JWT
  |                               | Check user/org
  |<---- {"type": "auth_success"}-|
  |                               |
```

### Authentication Message Format

```json
// Client sends:
{
  "type": "auth",
  "token": "eyJhbGciOiJIUzI1NiIs..."
}

// Server responds (success):
{
  "type": "auth_success"
}
```

### Close Codes

| Code | Meaning |
|------|---------|
| 1008 | Policy violation (invalid token, missing user, etc.) |
| 4003 | Access revoked (inactive org, suspended user) |

### Re-validation During Connection

Long-lived connections are periodically re-validated:

```python
REVALIDATION_HEARTBEAT_INTERVAL = 10  # Re-validate every 10 heartbeats

if heartbeat_count % REVALIDATION_HEARTBEAT_INTERVAL == 0:
    user = await get_user_by_id(session, user_id, org_id)
    if not user or user.suspension_status == SuspensionStatus.SUSPENDED:
        await websocket.close(code=4003, reason="Access revoked")
```

## Message Format

### Standard Message Structure

All WebSocket messages follow this format:

```python
class WebSocketMessage(BaseModel):
    type: str           # Message type identifier
    payload: dict       # Message-specific data
    timestamp: datetime # ISO8601 timestamp
```

### Example Messages

```json
// Notification message
{
  "type": "notification",
  "payload": {
    "notification": {
      "id": "uuid",
      "title": "New message",
      "body": "You have a new message",
      "link": "/messages/123",
      "read_time": null,
      "created_time": "2024-01-15T10:30:00Z"
    }
  },
  "timestamp": "2024-01-15T10:30:00.123456Z"
}

// Maintenance mode message
{
  "type": "maintenance",
  "payload": {
    "enabled": true,
    "message": "System maintenance in progress"
  },
  "timestamp": "2024-01-15T10:30:00.123456Z"
}

// Announcement message
{
  "type": "announcement_created",
  "payload": {
    "id": "uuid",
    "title": "Important Update",
    "body": "Details here...",
    "priority": "high",
    "is_dismissible": true
  },
  "timestamp": "2024-01-15T10:30:00.123456Z"
}

// Data export status
{
  "type": "data_export_status",
  "payload": {
    "export_id": "uuid",
    "status": "completed",
    "file_size_bytes": 1048576,
    "expires_at": "2024-01-16T10:30:00Z"
  },
  "timestamp": "2024-01-15T10:30:00.123456Z"
}
```

## Client Messages

### Allowed Message Types

After authentication, clients can only send:

```python
ALLOWED_MESSAGE_TYPES = {"ping"}
```

### Ping/Pong Heartbeat

```json
// Client sends:
{"type": "ping"}

// Server responds:
{"type": "pong"}
```

Heartbeats:
- Keep the connection alive
- Refresh Redis TTL
- Trigger periodic re-validation

### Message Size Limit

```python
MAX_MESSAGE_SIZE = 64 * 1024  # 64KB
```

## Broadcasting Messages

### Using MessageBroadcaster

The `MessageBroadcaster` provides a high-level API for sending messages:

```python
from src.services.websocket import message_broadcaster

# Send to a specific user (all their sessions)
await message_broadcaster.send_to_user(
    user_id=UUID("..."),
    message_type="notification",
    payload={"notification": {...}}
)

# Send to all users in an organization
await message_broadcaster.send_to_organization(
    organization_id=UUID("..."),
    message_type="announcement_created",
    payload={...}
)

# Send to all connected users (platform-wide)
await message_broadcaster.send_to_platform(
    message_type="maintenance",
    payload={"enabled": True, "message": "..."}
)
```

### Pub/Sub Channels

```python
# Channel naming convention
ws:user:{user_id}   # User-specific messages
ws:org:{org_id}     # Organization-wide broadcasts
ws:platform         # Platform-wide announcements
```

### Direct Redis Pub/Sub

For lower-level control:

```python
from src.services.websocket import redis_pubsub

# Publish to specific channel
await redis_pubsub.publish_to_user(user_id, message)
await redis_pubsub.publish_to_org(organization_id, message)
await redis_pubsub.publish_to_platform(message)

# Maintenance mode shortcut
await redis_pubsub.broadcast_maintenance_mode(enabled=True, message="...")
```

## Common Use Cases

### 1. In-App Notifications

```python
# In notification dispatcher or background task
from src.services.websocket.broadcaster import message_broadcaster

notification = await create_user_notification(session, ...)

await message_broadcaster.send_to_user(
    user_id=UUID(user_id),
    message_type="notification",
    payload={
        "notification": {
            "id": str(notification.id),
            "title": notification.title,
            "body": notification.body,
            "link": notification.link,
            "read_time": None,
            "created_time": notification.created_time.isoformat(),
        }
    }
)
```

### 2. Maintenance Mode Broadcasts

```python
# When enabling maintenance mode
from src.services.websocket import redis_pubsub

await redis_pubsub.broadcast_maintenance_mode(
    enabled=True,
    message="System maintenance - expected duration 30 minutes"
)
```

### 3. Announcement Updates

```python
# When creating/updating/deleting announcements
await message_broadcaster.send_to_organization(
    organization_id=org_id,
    message_type="announcement_created",  # or "announcement_updated", "announcement_deleted"
    payload={...announcement_data}
)
```

### 4. Background Job Status Updates

```python
# When a data export completes
await message_broadcaster.send_to_user(
    user_id=user_id,
    message_type="data_export_status",
    payload={
        "export_id": str(export.id),
        "status": "completed",
        "file_size_bytes": file_size,
        "expires_at": expires_at.isoformat(),
    }
)
```

## Error Handling

### Connection Errors

```python
try:
    await websocket.send_json(message)
except Exception as e:
    logger.warning("Failed to send message to connection %s: %s", connection_id, str(e))
    # Connection will be cleaned up on next heartbeat failure
```

### Redis Unavailable

The system degrades gracefully when Redis is unavailable:

```python
if not await self._is_available():
    logger.warning("Redis unavailable, skipping message publish")
    return False  # Message not delivered, but no exception
```

### Message Callback Errors

```python
for callback in callbacks.values():
    try:
        await callback(parsed_message)
    except Exception as e:
        logger.error("Error in message callback for channel %s: %s", channel, str(e))
        # Continue processing other callbacks
```

## Frontend Integration

### WebSocket Hook

```typescript
// app/frontend/src/hooks/useWebSocket.ts
const { connectionStatus, messages, sendPing, disconnect, connect } = useWebSocket()
```

### Connection Status

```typescript
type WebSocketConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'
```

### Processing Messages

Each message type has a dedicated processor hook:

```typescript
// In AuthProvider (called once to avoid duplicates)
useNotificationProcessor()    // Handles "notification" messages
useMaintenanceWebSocket()     // Handles "maintenance" messages
useAnnouncementWebSocket()    // Handles announcement_* messages
useDataExportWebSocket()      // Handles "data_export_status" messages
```

### Reconnection Strategy

```typescript
const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000
const RECONNECT_MULTIPLIER = 2

// Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
```

### Access Revoked Handling

```typescript
if (event.code === 4003) {  // WS_CLOSE_CODE_ACCESS_REVOKED
  dispatch(setError('websocket.access_revoked'))
  dispatch(logout())
  // Don't attempt to reconnect
}
```

## Testing

### Test Setup

```python
# Create test app without lifespan
app = FastAPI()

# Mock WebSocket dependencies
with patch("src.api.websocket.redis_registry") as mock_registry, \
     patch("src.api.websocket.redis_pubsub") as mock_pubsub:
    mock_registry.register_connection = AsyncMock(return_value=True)
    mock_pubsub.subscribe_for_connection = AsyncMock(return_value=True)
    ...
```

### Authentication Tests

```python
# Test missing token
with pytest.raises(WebSocketDisconnect) as exc_info:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth"})
        websocket.receive_json()
assert exc_info.value.code == 1008

# Test successful connection
with client.websocket_connect("/ws") as websocket:
    websocket.send_json({"type": "auth", "token": valid_token})
    response = websocket.receive_json()
    assert response == {"type": "auth_success"}
```

### Ping/Pong Tests

```python
# Verify heartbeat works
websocket.send_json({"type": "ping"})
response = websocket.receive_json()
assert response == {"type": "pong"}
```

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Redis connection for pub/sub |

### Constants

```python
# In websocket.py
AUTH_TIMEOUT_SECONDS = 10           # Auth message timeout
MAX_MESSAGE_SIZE = 64 * 1024        # 64KB message limit
REVALIDATION_HEARTBEAT_INTERVAL = 10  # Re-validate every N heartbeats

# In redis_registry.py
CONNECTION_TTL = 7200               # 2 hours Redis TTL
```

## Security Considerations

1. **Token in Message**: JWT sent in first message, not URL, to prevent logging exposure
2. **Message Size Limit**: 64KB limit prevents memory exhaustion attacks
3. **Auth Timeout**: 10-second timeout prevents connection hoarding
4. **Periodic Re-validation**: Suspended users/inactive orgs disconnected during heartbeat
5. **Allowed Message Types**: Whitelist of client message types (only "ping" allowed)
6. **Organization Isolation**: Connections are scoped to organization via pub/sub channels

## Related Documentation

- [Notifications](./notifications.md) - Notification system using WebSocket for in-app delivery
- [Background Jobs](./background_jobs.md) - ARQ tasks that may broadcast WebSocket messages
- [API](./api.md) - REST API patterns (WebSocket endpoint registered in router)
- [Caching](./caching.md) - Redis usage for pub/sub and connection registry
