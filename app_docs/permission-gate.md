# Permission Gate

**ADW ID:** 20260108112010-00000000
**Date:** 2026-01-11

## Overview

Frontend permission system that conditionally renders UI elements based on user permissions. Permissions are fetched from `GET /api/v1/user/permissions` after authentication and stored in Redux, enabling role-based UI control.

## Implementation

### Files Modified

- `app/backend/src/api/user.py`: `/permissions` endpoint
- `app/backend/src/serialisers/user.py`: `UserPermissionsResponse` model
- `app/frontend/src/hooks/usePermission.ts`: Permission checking hooks
- `app/frontend/src/components/PermissionGate.tsx`: Gate component and HOC
- `app/frontend/src/features/auth/authApi.ts`: `getUserPermissions` query
- `app/frontend/src/features/auth/authSlice.ts`: Permission state matcher
- `app/frontend/src/components/AuthProvider.tsx`: Auto-fetch permissions on auth
- `app/frontend/src/types/auth.ts`: Extended User with `permissions` field

### Permission Format

Format: `resource:action` (e.g., `users:read`, `api_keys:write`, `roles:delete`). Super admins (`is_admin: true`) bypass all checks.

## Usage

### usePermission Hook

```tsx
import { usePermission } from '@/hooks/usePermission'

const { canRead, canWrite, canDelete } = usePermission('api_keys')
{canWrite && <Button>Create Key</Button>}
```

### useHasAnyPermission / useHasAllPermissions

```tsx
const canManage = useHasAnyPermission(['users:write', 'users:delete'])
const canFullyManage = useHasAllPermissions(['users:read', 'users:write'])
```

### PermissionGate Component

```tsx
import { PermissionGate } from '@/components/PermissionGate'

// Single permission
<PermissionGate permission="users:write">
  <CreateUserButton />
</PermissionGate>

// Multiple (any)
<PermissionGate permission={['users:write', 'users:delete']}>
  <ManageUsersPanel />
</PermissionGate>

// Multiple (all required)
<PermissionGate permission={['users:read', 'users:write']} requireAll>
  <EditUserButton />
</PermissionGate>

// With fallback
<PermissionGate permission="admin:access" fallback={<AccessDenied />}>
  <AdminPanel />
</PermissionGate>
```

### withPermission HOC

```tsx
const ProtectedAdminPanel = withPermission(AdminPanel, 'admin:access')
```

## Guidelines

- Permissions are fetched non-blocking after login
- Use `usePermission` for standard CRUD operations
- Use `PermissionGate` for declarative UI gating
- Use `useHasAnyPermission`/`useHasAllPermissions` for custom logic
