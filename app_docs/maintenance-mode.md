# Maintenance Mode Feature

**ADW ID:** 20260115150417-a61b77b0
**Specification:** specs/multi-phase/issue-148-adw-20260115150417-a61b77b0-multi-phase.md

System-wide maintenance mode allowing super administrators to activate maintenance periods or schedule them with timezone-aware scheduling. Shows maintenance page to users (except configurable super admin bypass), disconnects WebSocket connections, and includes automatic polling.

## Implementation

### Backend Files
- `app/backend/src/api/maintenance.py` - Public status endpoint
- `app/backend/src/api/admin.py` - Admin configuration endpoints
- `app/backend/src/crud/maintenance.py` - CRUD operations (stored in SystemConfig)
- `app/backend/src/serialisers/maintenance.py` - Pydantic models
- `app/backend/src/api/websocket.py` - WebSocket connection checks
- `app/backend/src/services/websocket/redis_pubsub.py` - Broadcast mechanism
- `app/backend/src/core/response_codes.py` - Error codes
- `app/backend/tests/unit_tests/test_maintenance.py` - Tests (590 lines)

### Frontend Files
- `app/frontend/src/features/maintenance/maintenanceSlice.ts` - Redux state
- `app/frontend/src/features/maintenance/maintenanceApi.ts` - RTK Query (60s polling)
- `app/frontend/src/components/MaintenanceProvider.tsx` - Provider with auto-polling and page reload
- `app/frontend/src/pages/MaintenancePage.tsx` - Maintenance page
- `app/frontend/src/pages/admin/MaintenanceSettingsPage.tsx` - Admin UI
- `app/frontend/src/pages/NotFoundPage.tsx` - Enhanced 404 page
- `app/frontend/src/layouts/RootLayout.tsx` - MaintenanceProvider integration
- `app/frontend/src/router.tsx` - Routes
- `app/frontend/src/locales/*/admin.json` and `*/errors.json` - i18n (5 locales)

## Architecture

**Storage:** SystemConfig table with key `maintenance.mode` containing:
```json
{
  "enabled": false,
  "message": "We're performing scheduled maintenance",
  "scheduled_start": "2026-01-15T22:00:00Z",
  "scheduled_end": "2026-01-16T02:00:00Z",
  "allow_super_admin": true
}
```

**Key Design Decisions:**
- Global system config (not tenant-scoped)
- Public unauthenticated endpoint at `/api/v1/maintenance/status` for frontend checks before login
- WebSocket close code 4001 (distinct from 4003 for inactive organizations)
- RTK Query 60s polling balances responsiveness vs server load
- Full page reload on maintenance end restores WebSocket state
- All dates in ISO format with timezone, displayed in user's local timezone
- i18n for 5 languages (en, de, xh, zu, nso)

## Usage

**Enable immediately:** Navigate to `/admin/maintenance`, toggle "Enable Maintenance Mode", enter message, configure super admin access, save.

**Schedule future:** Same page, set start/end datetimes instead of enabling immediately.

**User experience:** All pages redirect to maintenance page (unless super admin with bypass), WebSocket disconnects gracefully, page reloads automatically when ended.

**Developer API:**
```typescript
const { data: status } = useGetMaintenanceStatusQuery()
const [updateMaintenance] = useUpdateMaintenanceMutation()

await updateMaintenance({
  enabled: true,
  message: 'System upgrade',
  scheduled_start: null,
  scheduled_end: '2026-01-16T02:00:00Z',
  allow_super_admin: true
})
```

## Testing

Backend: `cd app/backend && make test app/backend/tests/unit_tests/test_maintenance.py`

Coverage: Status endpoint, admin endpoints, WebSocket rejection, super admin bypass, time validation, tenant isolation (global not tenant-scoped).

Frontend: maintenanceReducer added to test store (`app/frontend/src/test/utils.tsx`).

Integration: Start both servers, login as super admin, navigate to `/admin/maintenance`, toggle maintenance, verify page appears and WebSocket disconnects.

## Limitations & Future Work

**Current limitations:**
- Scheduled activation requires manual trigger (no background scheduler)
- No upcoming maintenance notifications
- Message limit 500 characters
- Single window only (no overlaps)

**Future:** Background job scheduling, email notifications, maintenance history UI, org-specific windows, progress indicators, markdown support, rate limiting during maintenance.
