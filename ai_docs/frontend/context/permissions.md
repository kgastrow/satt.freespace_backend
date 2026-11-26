# Frontend Permissions System

Permission gate system for controlling UI visibility and route access.

## Overview

| Feature | Description |
|---------|-------------|
| Source | Backend `GET /user/permissions` |
| Super admin | Bypasses all checks (`is_admin=true`) |
| Impersonation | Super admin bypass disabled during impersonation |

## Key Files

```
app/frontend/src/
├── hooks/usePermissions.ts           # Centralized permission hook (reactive)
├── hooks/usePermission.ts            # Resource-based wrapper + convenience hooks
├── lib/permissions.ts                # Non-reactive permission service (for utilities)
├── components/PermissionGate.tsx     # Component for conditional rendering
├── components/SuperAdminGuard.tsx    # Route guard for super admin only
└── features/auth/authSlice.ts        # Stores permissions in Redux
```

## Permission Hooks

### usePermissions (Primary)
```typescript
import { usePermissions } from '@/hooks/usePermissions'

const { hasPermission, hasAnyPermission, hasAllPermissions, canAccess, isSuperAdmin } = usePermissions()

hasPermission('users:write')              // Single check
hasAnyPermission(['users:write', 'users:delete'])  // OR logic
hasAllPermissions(['users:read', 'users:write'])   // AND logic
canAccess('users', 'write')               // Resource + action
```

### usePermission (Resource-based)
```typescript
import { usePermission } from '@/hooks/usePermission'

const { canRead, canWrite, canDelete, hasPermission } = usePermission('users')

// canRead = canAccess('users', 'read')
// canWrite = canAccess('users', 'write')
// canDelete = canAccess('users', 'delete')
// hasPermission = full permission check function for custom codes
```

### Convenience Hooks
```typescript
import { useHasAnyPermission, useHasAllPermissions } from '@/hooks/usePermission'

// Returns boolean directly
const canManageUsers = useHasAnyPermission(['users:write', 'users:delete'])
const hasFullAccess = useHasAllPermissions(['users:read', 'users:write', 'users:delete'])
```

### Non-reactive Service (for utilities)
```typescript
import { permissions } from '@/lib/permissions'

// Singleton that reads Redux directly - does NOT trigger re-renders
// Use in utility functions, event handlers, or outside React components
if (permissions.hasPermission('users:write')) { /* ... */ }
if (permissions.canAccess('users', 'write')) { /* ... */ }
if (permissions.isSuperAdmin()) { /* ... */ }
if (permissions.isImpersonating()) { /* ... */ }
```

**When to use each:**
| Context | Use |
|---------|-----|
| React component rendering | `usePermissions` or `usePermission` hooks |
| Utility functions | `permissions` service |
| Outside React | `permissions` service |

## Super Admin Bypass During Impersonation

Super admin bypass is disabled when impersonating another user. The check:

```typescript
// From lib/permissions.ts
const isSuperAdmin = (): boolean => {
  const { user, isImpersonating } = getState()
  return user?.is_admin === true && !isImpersonating  // <-- bypass disabled if impersonating
}
```

This ensures admins see exactly what the impersonated user would see.

## Components

### PermissionGate
```typescript
import { PermissionGate } from '@/components/PermissionGate'

// Single permission
<PermissionGate permission="users:write">
  <CreateButton />
</PermissionGate>

// ANY permission (default)
<PermissionGate permission={['users:write', 'users:delete']}>
  <ManagePanel />
</PermissionGate>

// ALL permissions required
<PermissionGate permission={['users:read', 'users:write']} requireAll>
  <EditButton />
</PermissionGate>

// With fallback or redirect
<PermissionGate permission="admin:access" fallback={<AccessDenied />}>
  <AdminPanel />
</PermissionGate>

<PermissionGate permission="users:read" redirectTo="/dashboard">
  <UsersPage />
</PermissionGate>
```

### SuperAdminGuard
```typescript
import { SuperAdminGuard } from '@/components/SuperAdminGuard'

<SuperAdminGuard redirectTo="/dashboard">
  <PlatformAdminPage />
</SuperAdminGuard>
```

## Permission Code Format

**Pattern:** `resource:action` (e.g., `users:read`, `api_keys:write`)

| Action | Purpose |
|--------|---------|
| `read` | View/list |
| `write` | Create/update |
| `delete` | Delete |
| `admin` | Administrative |

## Common Patterns

### Page-Level
```typescript
function UsersPage() {
  const { canRead, canWrite, canDelete } = usePermission('users')
  if (!canRead) return <AccessDenied />
  return (
    <div>
      {canWrite && <CreateUserButton />}
      <UserList />
      {canDelete && <BulkDeleteButton />}
    </div>
  )
}
```

### Form Actions
```typescript
function UserForm() {
  const { canWrite, canDelete } = usePermission('users')
  return (
    <form>
      <input disabled={!canWrite} />
      {canWrite && <Button type="submit">Save</Button>}
      {canDelete && <Button variant="destructive">Delete</Button>}
    </form>
  )
}
```

## Testing

```typescript
render(<UsersPage />, {
  preloadedState: {
    auth: {
      user: { id: '1', permissions: ['users:read', 'users:write'], is_admin: false },
      isAuthenticated: true,
    },
  },
})
```

Test cases: with permission (visible), without permission (hidden), super admin (all visible).

## Security Notes

| Rule | Reason |
|------|--------|
| Frontend = UX only | Backend validates all API calls |
| Don't rely on hidden UI | Users can bypass frontend checks |
| Sync permission codes | Frontend must match backend definitions |
| Handle loading states | Don't render protected content before permissions load |
