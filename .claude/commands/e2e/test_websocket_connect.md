# E2E Test: WebSocket Connection

## Test Description
Validate that the application establishes and maintains WebSocket connections for real-time features, including authentication, reconnection, and message handling.

## User Story
As a user
I want my browser to maintain a real-time connection
So that I can receive instant notifications, announcements, and updates

## Prerequisites
- Backend server running with WebSocket support
- Frontend dev server running
- Authenticated user session

## Test Steps

### Test 1: Establish WebSocket Connection

**Steps:**
1. Login as regular user
2. Wait for dashboard to fully load
3. Open browser developer tools (Network tab, filter WS)
4. **Screenshot:** Network tab showing WebSocket
5. Verify WebSocket connection is established
6. Verify connection URL format: `ws://localhost:8000/ws?token=...`
7. Verify connection status shows "connected"

**Expected Results:**
- WebSocket connection established automatically on login
- Token passed as query parameter for authentication
- Connection status is "connected"
- No connection errors in console

### Test 2: WebSocket Authentication

**Steps:**
1. Login as user
2. Observe WebSocket connection in Network tab
3. **Screenshot:** WebSocket headers/handshake
4. Verify token is included in connection URL
5. Verify connection is accepted (101 Switching Protocols)
6. Verify no authentication errors in messages

**Expected Results:**
- Token-based authentication works
- Valid token allows connection
- Connection upgrades successfully

### Test 3: Connection Status Indicator

**Steps:**
1. Login and wait for connection
2. Look for connection status indicator in UI (if present)
3. **Screenshot:** Connection status indicator
4. Verify indicator shows "connected" state
5. Disconnect network briefly
6. Verify indicator shows "disconnected" or "reconnecting"
7. Restore network
8. Verify indicator returns to "connected"

**Expected Results:**
- Connection status visible to user (if implemented)
- Status updates reflect actual connection state
- Visual feedback for connectivity issues

### Test 4: Automatic Reconnection

**Steps:**
1. Login and establish WebSocket connection
2. Note current connection in Network tab
3. Simulate network disconnect (DevTools > Network > Offline)
4. **Screenshot:** Connection lost state
5. Wait 2-3 seconds
6. Restore network (uncheck Offline)
7. **Screenshot:** Reconnection attempt
8. Wait for reconnection
9. Verify new WebSocket connection established
10. Verify connection status returns to "connected"

**Expected Results:**
- Automatic reconnection after disconnect
- Exponential backoff (1s base, 2x multiplier, 30s max)
- Connection restored without user intervention
- No duplicate connections

### Test 5: Reconnection Backoff

**Steps:**
1. Login and establish connection
2. Simulate repeated disconnects
3. Observe reconnection timing in console/network
4. **Screenshot:** Console showing backoff delays
5. Verify increasing delays between attempts:
   - 1st retry: ~1s
   - 2nd retry: ~2s
   - 3rd retry: ~4s
   - Max: 30s
6. Verify connection eventually establishes

**Expected Results:**
- Exponential backoff prevents server overload
- Delays increase with each failed attempt
- Maximum delay is capped at 30 seconds

### Test 6: Receive Messages

**Steps:**
1. Login and establish WebSocket connection
2. Open WebSocket messages in Network tab
3. **Screenshot:** WebSocket messages panel
4. Verify message format: `{ type, payload, timestamp }`
5. Wait for any incoming message (ping/announcement/notification)
6. Verify message is properly parsed
7. Verify UI updates based on message (if applicable)

**Expected Results:**
- Messages received in expected format
- Type field identifies message purpose
- Payload contains message data
- Timestamp for message timing

### Test 7: Ping/Pong Heartbeat

**Steps:**
1. Login and establish WebSocket connection
2. Monitor WebSocket messages
3. Wait for heartbeat interval (if implemented)
4. **Screenshot:** Ping/pong messages
5. Verify ping messages are sent
6. Verify pong responses are received
7. Verify connection remains open

**Expected Results:**
- Heartbeat keeps connection alive
- Ping/pong mechanism works
- Connection doesn't timeout during idle

### Test 8: Handle Access Revoked

**Steps:**
1. Login as user
2. Establish WebSocket connection
3. In another session (admin), revoke user's session
4. **Screenshot:** Access revoked handling
5. Verify WebSocket receives close code 4003
6. Verify user is logged out automatically
7. Verify redirect to login page

**Expected Results:**
- Close code 4003 triggers logout
- Session revocation is immediate
- User cannot continue using app

### Test 9: Multiple Tab Behavior

**Steps:**
1. Login in Tab 1
2. Open same application in Tab 2 (same browser)
3. Verify both tabs have WebSocket connections
4. **Screenshot:** Multiple connections (Network tabs)
5. Send a notification (via admin)
6. Verify both tabs receive the notification
7. Close Tab 2
8. Verify Tab 1 connection remains stable

**Expected Results:**
- Each tab has its own connection
- Both tabs receive messages
- Tab closure doesn't affect other tabs

### Test 10: Clean Disconnect on Logout

**Steps:**
1. Login and establish WebSocket connection
2. Note connection in Network tab
3. Click logout button
4. **Screenshot:** Connection closed
5. Verify WebSocket connection closes cleanly
6. Verify close code is normal (1000)
7. Verify no reconnection attempts after logout

**Expected Results:**
- Logout triggers clean disconnect
- No dangling connections
- No reconnection attempts

### Test 11: Connection During Token Refresh

**Steps:**
1. Login with session that will expire soon (or simulate)
2. Establish WebSocket connection
3. Wait for token refresh to occur
4. **Screenshot:** Connection during refresh
5. Verify WebSocket handles token refresh
6. Verify connection remains stable or reconnects with new token

**Expected Results:**
- Token refresh doesn't break connection
- Connection may briefly reconnect
- No authentication errors after refresh

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| WS | `/ws?token={access_token}` | WebSocket connection |

## Message Format

**Incoming Message Structure:**
```json
{
  "type": "notification",
  "payload": {
    "id": "uuid",
    "title": "New message",
    "body": "You have a new notification"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Message Types:**
- `notification`: In-app notification
- `announcement`: System announcement
- `maintenance`: Maintenance mode update
- `export_progress`: Export status update
- `ping`/`pong`: Heartbeat

**Close Codes:**
- `1000`: Normal closure
- `4003`: Access revoked (triggers logout)

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Connection indicator | Status indicator in UI (if present) |
| Notification bell | Notification component that receives WS messages |
| Logout button | `getByRole('button', { name: /logout/i })` |

## Success Criteria

- WebSocket connection establishes on login
- Authentication via token works
- Automatic reconnection on disconnect
- Exponential backoff for retries
- Messages received and parsed correctly
- Access revocation triggers logout
- Clean disconnect on logout
- Multiple tabs work independently

## Notes

- Test with slow/unstable network conditions
- Verify WebSocket security (wss:// in production)
- Monitor memory for leaks during reconnection
- Test maximum message size handling
- Verify browser compatibility
- Consider testing with WebSocket blockers/proxies
