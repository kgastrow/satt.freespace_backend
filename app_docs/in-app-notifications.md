# In-App Notifications

**ADW ID:** 20260112125641-881e381a
**Date:** 2026-01-12
**Specification:** specs/multi-phase/issue-114-adw-20260112125641-881e381a-multi-phase.md

## Overview

In-app notification system with database persistence and real-time WebSocket delivery. NotificationBell component in header shows unread count; NotificationPanel dropdown displays notifications with mark read/dismiss actions.

## Implementation

### Backend Files

- `app/backend/src/models/user_notification.py` - UserNotification model with composite indexes on (org_id, user_id), (user_id, read_time), (user_id, created_time)
- `app/backend/src/crud/user_notification.py` - CRUD with organization_id filtering
- `app/backend/src/serialisers/user_notification.py` - Pydantic models
- `app/backend/src/api/user_notification.py` - List, mark read/all read, dismiss, unread count endpoints
- `app/backend/src/services/notifications/in_app_provider.py` - Persists to DB, broadcasts via MessageBroadcaster.send_to_user()
- `app/backend/src/services/notifications/dispatcher.py` - Routes "in_app" channel to InAppProvider
- `app/backend/alembic/versions/` - UserNotification table migration

### Frontend Files

- `app/frontend/src/types/in-app-notification.ts` - TypeScript types
- `app/frontend/src/features/in-app-notifications/inAppNotificationsSlice.ts` - Redux slice
- `app/frontend/src/features/in-app-notifications/inAppNotificationsApi.ts` - RTK Query endpoints
- `app/frontend/src/components/NotificationBell.tsx` - Bell icon with badge (shows up to 99+)
- `app/frontend/src/components/NotificationPanel.tsx` - Notification dropdown
- `app/frontend/src/components/NotificationItem.tsx` - Individual notification
- `app/frontend/src/hooks/useInAppNotifications.ts` - WebSocket integration
- `app/frontend/src/layouts/DashboardLayout.tsx` - Includes NotificationBell

### Architecture

**Real-time delivery flow:** Dispatcher → InAppProvider → DB insert → MessageBroadcaster.send_to_user() → Redis pub/sub → WebSocket → Frontend

**Key patterns:**
- Multi-tenant isolation via organization_id filtering on all queries
- Soft deletes with deleted_time (dismissed notifications)
- Optimistic UI updates with automatic error correction
- WebSocket broadcasts use MessageBroadcaster with message type "notification"
- Notifications considered delivered on DB insertion (WebSocket best-effort)

### Usage

**Send via provider:**
```python
from src.services.notifications.in_app_provider import in_app_provider

result = await in_app_provider.send_in_app(
    session=session,
    organization_id=str(org_id),
    user_id=str(user_id),
    title="New Message",
    body="Notification body",
    link="/messages/123",  # Optional
    category_id=str(category_id),  # Optional
)
```

**Send via dispatcher (multi-channel):**
```python
await dispatcher.send(
    channel="in_app",
    subject="Title",
    message="Body",
    metadata={
        "session": session,
        "organization_id": org_id,
        "user_id": user_id,
        "link": "/path",
    }
)
```

**Frontend:** NotificationBell auto-included in DashboardLayout; users click to view/manage notifications.

### Configuration

- `in_app_enabled` on UserNotificationPreference and OrganizationNotificationSettings (default: True)
- Pagination: 20 per page, max 100
- Badge: shows count up to 99, then "99+"

### Testing

Backend: `cd app/backend && make test` - tests in `app/backend/tests/unit_tests/test_in_app_notifications.py` cover model, CRUD, endpoints, provider, tenant isolation

Frontend: `cd app/frontend && npm run test` - covers Redux slice, API, components, WebSocket integration

### Notes

- Integrates with notification preferences, categories, templates
- Logout cleanup via useInAppNotifications hook
- Delivered on insertion; WebSocket is best-effort delivery
