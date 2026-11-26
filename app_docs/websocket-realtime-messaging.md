# WebSocket Real-Time Messaging

**ADW ID:** 20260112111050-f320e7a7 | **Date:** 2026-01-12
**Specification:** specs/multi-phase/issue-112-adw-20260112111050-f320e7a7-multi-phase.md

## Overview

Multi-worker FastAPI WebSocket implementation with three delivery targets: user-specific, organization-wide, and platform-wide. Uses Redis pub/sub for cross-worker routing and Redis hashes for connection registry. JWT authentication via query parameter with tenant isolation.

## Implementation

### Backend Files

- `app/backend/main.py` - Router integration
- `app/backend/src/api/websocket.py` - `/ws` endpoint with JWT auth
- `app/backend/src/serialisers/websocket.py` - Pydantic message models
- `app/backend/src/services/websocket/connection_manager.py` - Local connection tracking
- `app/backend/src/services/websocket/redis_registry.py` - Cross-worker registry (Redis hashes)
- `app/backend/src/services/websocket/redis_pubsub.py` - Message routing (Redis pub/sub)
- `app/backend/src/services/websocket/broadcaster.py` - Broadcast API

### Frontend Files

- `app/frontend/src/types/websocket.ts` - TypeScript types
- `app/frontend/src/hooks/useWebSocket.ts` - React hook with auto-reconnection (exponential backoff: 1s, 2s, 4s... max 30s)
- `app/frontend/src/features/websocket/websocketSlice.ts` - Redux state
- `app/frontend/src/store/index.ts` - Store integration

### Key Patterns

- **Multi-tenant auth**: JWT validates user/org for tenant isolation
- **Multi-session support**: Users receive messages on all active connections
- **Delivery targets**: `ws:user:{user_id}`, `ws:org:{org_id}`, `ws:platform`
- **Graceful degradation**: Falls back to local delivery if Redis unavailable
- **Worker isolation**: Each worker has ConnectionManager; Redis pub/sub routes to all workers

## Usage

### Sending Messages

```python
from src.services.websocket import message_broadcaster

# To user (all sessions)
await message_broadcaster.send_to_user(user_id=uuid, message_type="notification", payload={...})

# To organization
await message_broadcaster.send_to_organization(organization_id=uuid, message_type="data_updated", payload={...})

# To platform
await message_broadcaster.send_to_platform(message_type="system_announcement", payload={...})
```

### Receiving Messages

```tsx
import { useWebSocket } from '@/hooks/useWebSocket'

function MyComponent() {
  const { connectionStatus, messages, sendPing } = useWebSocket()
  // connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
  return <div>Status: {connectionStatus}</div>
}
```

### Message Format

```json
{
  "type": "notification",
  "payload": { "key": "value" },
  "timestamp": "2026-01-12T11:10:50.123456+00:00"
}
```

## Configuration

| Variable | Default |
|----------|---------|
| `VITE_WS_URL` | `ws://localhost:8000` |

Endpoint at `/ws` (outside `/api/v1` prefix).

## Testing

**Backend:** `cd app/backend && make test`
- `tests/unit_tests/test_websocket_serializers.py`
- `tests/unit_tests/test_connection_manager.py`
- `tests/unit_tests/test_redis_registry.py`
- `tests/unit_tests/test_redis_pubsub.py`
- `tests/unit_tests/test_broadcaster.py`
- `tests/api_tests/test_websocket_api.py`

**Frontend:** `cd app/frontend && npm run test`
- `src/test/websocket.test.tsx`

## Notes

- **Heartbeat**: Send `{"type": "ping"}` for `{"type": "pong"}` response and TTL refresh
- **Token refresh**: Hook auto-reconnects on JWT change
- **Out of scope**: Offline queueing, user groups, client-to-server messages (beyond ping)
