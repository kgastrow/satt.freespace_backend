# shadcn/ui Component Patterns

## Overview

shadcn/ui components using Radix UI primitives + Tailwind CSS. Components are copied into `src/components/ui/` (not npm installed), allowing direct modification.

## Adding Components

```bash
npx shadcn@latest add button card dialog  # Add specific components
```

## Core Utilities

```typescript
import { cn } from '@/lib/utils'  // Merges Tailwind classes intelligently
<div className={cn('p-4 rounded-lg', className)}>...</div>
```

## Common Patterns

### Buttons
- `variant`: `default`, `destructive`, `outline`, `secondary`, `ghost`, `link`
- `size`: `default`, `sm`, `lg`, `icon`
- `asChild`: Compose with other components: `<Button asChild><Link to="/">Go</Link></Button>`

### Toasts (Sonner)
```tsx
import { toast } from 'sonner'
toast.success('Saved', { description: 'Changes saved.' })
toast.error('Failed', { action: { label: 'Retry', onClick: retry } })
```

### Forms
See `ai_docs/frontend/context/forms.md` for React Hook Form + shadcn integration.

## Customizing

Modify files directly in `src/components/ui/`. Add variants rather than forking components.

## Sidebar Component

The sidebar is a modular component in `src/components/ui/sidebar/`:

| File | Purpose |
|------|---------|
| `index.ts` | Re-exports all components |
| `types.ts` | TypeScript interfaces |
| `constants.ts` | Dimensions, animation timings |
| `SidebarContext.tsx` | State management (open, mobile) |
| `Sidebar.tsx` | Main wrapper with collapsible logic |
| `SidebarTrigger.tsx` | Toggle button |
| `SidebarLayout.tsx` | Layout container with sidebar |
| `SidebarContent.tsx` | Scrollable content area |
| `SidebarGroup.tsx` | Group with label and collapsible |
| `SidebarMenu.tsx` | Menu items with icons, tooltips |
| `SidebarMenuSub.tsx` | Nested sub-menus |

Import: `import { Sidebar, SidebarMenu, ... } from '@/components/ui/sidebar'`

## Best Practices

1. Use semantic variants (`variant="destructive"`) over custom styling
2. Use `asChild` to compose with React Router Link
3. Don't remove Radix ARIA attributes (accessibility)
4. Reference CSS variables for theming

## Files

- **Components**: `src/components/ui/`
- **Utils**: `src/lib/utils.ts`

---

## Application Components

Three-tier structure:

```
src/components/
├── ui/                    # shadcn/ui primitives only
├── [component].tsx        # Shared across features
└── [feature]/             # Feature-scoped components
```

### Naming Conventions

- PascalCase for component files: `AuthProvider.tsx`, `NotificationBell.tsx`
- lowercase for feature directories: `auth/`, `settings/`

---

## Providers

| Provider | Purpose |
|----------|---------|
| `AuthProvider` | Authentication state, user context, token management |
| `MaintenanceProvider` | Maintenance mode detection |
| `ErrorBoundary` | Graceful error handling |

See `ai_docs/frontend/context/auth.md` for authentication details.

---

## Guards

| Guard | Purpose |
|-------|---------|
| `AuthGuard` | Requires authenticated user; redirects to login |
| `SuperAdminGuard` | Requires super admin role |

```tsx
<Route element={<AuthGuard />}>
  <Route path="/dashboard" element={<Dashboard />} />
</Route>
```

See `ai_docs/frontend/context/permissions.md` for permission patterns.

---

## AdvancedDataTable (MANDATORY)

**Location:** `src/components/AdvancedDataTable/`

**RULE:** Use `AdvancedDataTable` for ALL tables displaying data from list endpoints. Do not use raw `<Table>` for paginated API data.

**BACKEND REQUIREMENT:** Expects backend to implement standard Query DSL (see `ai_docs/backend/context/api.md`). Sorting, filtering, search require `parse_filters`, `apply_sort`, etc.

### DataTable vs AdvancedDataTable

| Component | Use Case |
|-----------|----------|
| `AdvancedDataTable` | **All API-driven tables** - pagination, sorting, filtering, column visibility |
| `DataTable` | Legacy/simple tables only - row selection without advanced features |

**Prefer AdvancedDataTable for new development.** DataTable remains for simple use cases needing row selection without pagination controls.

### Basic Usage

```tsx
import { AdvancedDataTable, type AdvancedColumn } from '@/components/AdvancedDataTable'

const columns: AdvancedColumn<User>[] = [
  {
    key: 'name',
    header: t('users.table.name'),
    cell: (user) => `${user.first_name} ${user.last_name}`,
    sortable: true,
    searchable: true,
    alwaysVisible: true,
  },
  {
    key: 'status',
    header: t('users.table.status'),
    cell: (user) => <Badge>{user.status}</Badge>,
    filterable: true,
    filterConfig: {
      type: 'select',
      options: [
        { value: 'active', label: 'Active' },
        { value: 'suspended', label: 'Suspended' },
      ],
    },
  },
]

<AdvancedDataTable
  columns={columns}
  data={users}
  isLoading={isLoading}
  sort={sort}
  onSortChange={setSort}
  search={search}
  onSearchChange={setSearch}
  pagination={{
    page,
    pageSize: 10,
    total,
    onPageChange: setPage,
  }}
  visibleColumns={visibleColumns}
  onVisibleColumnsChange={setVisibleColumns}
  onRowClick={(user) => navigate(`/admin/users/${user.id}`)}
  getRowId={(user) => user.id}
/>
```

### Column Configuration

| Property | Description |
|----------|-------------|
| `key` | Unique column identifier |
| `header` | Display header (use i18n) |
| `cell` | `(item: T) => ReactNode` render function |
| `sortable` | Enable column sorting |
| `sortKey` | Backend sort field (defaults to `key`) |
| `searchable` | Include in search |
| `filterable` | Enable column filter |
| `filterConfig` | `{ type: 'select' | 'multiselect' | 'boolean', options?: [...] }` |
| `defaultVisible` | Visible by default (default: true) |
| `alwaysVisible` | Cannot be hidden |
| `hiddenOnMobile` | Hidden on mobile, shown on `md:` breakpoint and above |

### Mobile Responsiveness

Tag secondary columns with `hiddenOnMobile: true` to hide them on screens below the `md` breakpoint. The table applies `hidden md:table-cell` to both `<th>` and `<td>`.

```tsx
{ key: 'phone', header: 'Phone', hiddenOnMobile: true, cell: (u) => u.phone }
```

### Search Placeholder

Pass `searchPlaceholder` to override the default "Search..." text:

```tsx
<AdvancedDataTable searchPlaceholder={t('admin:users.filters.search')} />
```

### tableId Parameter

Pass `tableId` to persist column visibility in user preferences:

```tsx
const TABLE_ID = 'admin-users-table'
const { getTableColumnVisibility, setTableColumnVisibility } = usePreferences()

const visibleColumns = getTableColumnVisibility(TABLE_ID, DEFAULT_VISIBLE_COLUMNS)

<AdvancedDataTable
  tableId={TABLE_ID}
  visibleColumns={visibleColumns}
  onVisibleColumnsChange={(cols) => setTableColumnVisibility(TABLE_ID, cols)}
/>
```

### Pagination Modes

| Mode | Best For | UI |
|------|----------|-----|
| **Offset** (default) | Admin tables, page jumping | Page numbers, total count |
| **Cursor** | Logs, large datasets, real-time | "Load more" button |

```tsx
// Offset (default)
pagination={{ page, pageSize: 10, total, onPageChange: setPage }}

// Cursor
pagination={{
  mode: 'cursor',
  pageSize: 50,
  hasMore: data?.has_more ?? false,
  nextCursor: data?.next_cursor ?? null,
  onLoadMore: handleLoadMore,
  isLoadingMore: isFetching,
}}
```

### Cursor Pagination with Filters (Real Example)

From `UsersPage.tsx` - complete pattern for cursor pagination with URL-synced filters:

```tsx
const TABLE_ID = 'admin-users-table'

// State management
const [cursor, setCursor] = useState<string | null>(null)
const [allUsers, setAllUsers] = useState<UserListItem[]>([])
const [searchParams, setSearchParams] = useSearchParams()

// Filters from URL
const filters: FilterState = useMemo(() => {
  const f: FilterState = {}
  const status = searchParams.get('status')
  if (status) f.suspension_status = status
  return f
}, [searchParams])

// Key to detect filter/search changes (triggers cursor reset)
const queryKey = useMemo(() => JSON.stringify({ ...filters, search }), [filters, search])

// Reset cursor when filters change
useEffect(() => {
  setCursor(null)
  setAllUsers([])
}, [queryKey])

// API call with cursor
const { data, isLoading, isFetching } = useGetUsersCursorQuery({
  limit: pageSize,
  cursor: cursor || undefined,
  fields: fieldsParam,
  'filter[status]': filters.suspension_status as string | undefined,
  q: search || undefined,
})

// Accumulate data across pages
useEffect(() => {
  if (data?.items) {
    if (cursor === null) {
      setAllUsers(data.items)  // First page - replace
    } else {
      // Append, avoiding duplicates
      setAllUsers((prev) => {
        const existingIds = new Set(prev.map((u) => u.id))
        return [...prev, ...data.items.filter((u) => !existingIds.has(u.id))]
      })
    }
  }
}, [data, cursor])

// Load more handler
const handleLoadMore = useCallback(() => {
  if (data?.next_cursor) setCursor(data.next_cursor)
}, [data?.next_cursor])

// Table component
<AdvancedDataTable
  columns={columns}
  data={allUsers}
  isLoading={isLoading && allUsers.length === 0}
  filters={filters}
  onFiltersChange={handleFiltersChange}
  search={search}
  onSearchChange={handleSearchChange}
  pagination={{
    mode: 'cursor',
    pageSize,
    hasMore: data?.has_more || false,
    nextCursor: data?.next_cursor || null,
    onLoadMore: handleLoadMore,
    isLoadingMore: isFetching,
  }}
  tableId={TABLE_ID}
/>
```

### Virtual Scrolling

For tables with 100+ rows:

```tsx
<AdvancedDataTable
  columns={columns}
  data={largeDataset}
  virtualScroll={{
    enabled: true,
    height: 600,              // Required: container height in pixels
    estimatedRowHeight: 48,   // Default: 48
    overscan: 5,              // Default: 5
  }}
/>
```

### Sparse Fieldsets Integration

Connect visible columns to API field requests (page component responsibility):

```tsx
const COLUMN_FIELD_MAP: Record<string, string[]> = {
  avatar: ['avatar_url'],
  name: ['first_name', 'last_name'],
}

const fieldsParam = useMemo(() => {
  const fields = new Set<string>(['id'])
  visibleColumns.forEach((col) => {
    COLUMN_FIELD_MAP[col]?.forEach((f) => fields.add(f))
  })
  return Array.from(fields).join(',')
}, [visibleColumns])

const { data } = useGetUsersQuery({ fields: fieldsParam })
```

### Mutation Loading States in Tables

Show inline loading for row actions:

```tsx
const [deleteUser, { isLoading: isDeleting }] = useDeleteUserMutation()

// In column definition
{
  key: 'actions',
  cell: (user) => (
    <Button
      variant="ghost"
      size="sm"
      disabled={isDeleting}
      onClick={() => deleteUser(user.id)}
    >
      {isDeleting ? <Spinner className="h-4 w-4" /> : <Trash className="h-4 w-4" />}
    </Button>
  ),
}
```

For tracking which specific row is loading, use local state:

```tsx
const [deletingId, setDeletingId] = useState<string | null>(null)

const handleDelete = async (id: string) => {
  setDeletingId(id)
  try { await deleteUser(id).unwrap() }
  finally { setDeletingId(null) }
}

// In cell: disabled={deletingId === user.id}
```

---

## Performance Patterns

### React.memo

Use for components that re-render frequently with stable props:

```typescript
import { memo } from 'react'
export const MyComponent = memo(function MyComponent({ data }: Props) {
  // ...
})
```

**Memoized components:** `AppSidebar`, `NotificationBell`, `HeaderUserMenu`

**When to use:** Layout components, list items, components with expensive renders and stable props.

**When NOT to use:** Components with frequently changing props or minimal render cost.

---

## Feature Directories

| Directory | Purpose |
|-----------|---------|
| `admin/` | Admin layout (AdminSidebar, PlatformAdminSidebar) |
| `auth/` | Authentication UI (TwoFactorVerification) |
| `connected-accounts/` | OAuth account linking |
| `email-change/` | Email change flow modals |
| `feature-flags/` | Feature flag management |
| `navigation/` | Navigation components (NavRenderer) |
| `password/` | Password requirements display |
| `permissions/` | Permission selectors and dialogs |
| `sessions/` | Session management (SessionCard) |
| `settings/` | Settings page components |
| `skeletons/` | Loading skeleton components (CardSkeleton, FormSkeleton, TableSkeleton) |
| `sso/` | SSO login buttons (SSOButtonGroup) |
| `two-factor/` | 2FA setup and status |
| `user/` | User management dialogs |

---

## Cross-References

- **Authentication**: `ai_docs/frontend/context/auth.md`
- **Forms**: `ai_docs/frontend/context/forms.md`
- **Permissions**: `ai_docs/frontend/context/permissions.md`
- **SSO**: `ai_docs/frontend/context/sso.md`
- **Impersonation**: `ai_docs/frontend/context/impersonation.md`
