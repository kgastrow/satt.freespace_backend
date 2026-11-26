# Navigation Zones & Page Placement

This app has three distinct navigation zones. Every new page must be placed in the correct zone based on its **target audience** — the people who will use it most.

## The Three Navigation Zones

### 1. Main Sidebar (End-User Workflows)

**Who:** The primary users of the application — the people the product is built for.
**What:** Core workflows, dashboards, day-to-day task pages.
**Where:** Items appear in `AppSidebar`, visible immediately after login.
**Layout:** `DashboardLayout` (sidebar + content).

Use the main sidebar when the page is:
- A **daily-use workflow** (e.g., a task queue, a feed, a workspace)
- A **primary interface** the product is designed around
- Something the user needs to access **within 1-2 clicks from login**
- Used by **most authenticated users**, not just administrators

### 2. Admin Hub (`/admin`) — Organization Administration

**Who:** Organization administrators managing settings, users, and configuration.
**What:** CRUD for reference data, user management, org settings, monitoring.
**Where:** Accessible via a single "Admin Hub" link in the main sidebar (permission-gated). Pages live under `/admin/*` with their own sidebar (`AdminSidebar`).
**Layout:** `AdminLayout` (admin sidebar + content).

Use the admin hub when the page is:
- **Configuration or settings** that change infrequently
- **Reference data management** (lookup tables, templates, definitions)
- **User/role administration**
- **Monitoring and logs** (audit trails, reports)
- Used only by users with **administrative permissions**

### 3. Platform Admin Hub (`/platform-admin`) — Super Admin

**Who:** Platform super-administrators (cross-tenant operations).
**What:** System configuration, tenant management, platform-wide settings.
**Where:** Visible only to super admins in the main sidebar. Pages under `/platform-admin/*`.
**Layout:** `PlatformAdminLayout` (self-guarding, includes `SuperAdminGuard`).

Use the platform admin hub when the page:
- Operates **across tenants** or manages the platform itself
- Is only for **super administrators** (not org-level admins)

## Decision Guide

When adding a new page, ask:

```
Is this page used by the product's primary end-users as part of their core workflow?
├── YES → Main Sidebar
│         Add to navigation config, use DashboardLayout, permission-gate the nav item
│
└── NO → Is it organization-level administration or configuration?
         ├── YES → Admin Hub (/admin/*)
         │         Add to adminNav config, use AdminLayout
         │
         └── NO → Platform Admin Hub (/platform-admin/*)
                   Add to platformAdminNav config, use PlatformAdminLayout
```

**Common mistake:** Putting end-user workflow pages in the admin hub because they require permissions. Having permissions does NOT make something an admin page. A page for field workers to log activities requires permissions but belongs in the main sidebar — it's their primary workflow.

## How to Add Items to Each Zone

### Main Sidebar

1. **Navigation config** (`config/navigation.ts`): Add a `NavItem` to `mainNavigation`
2. **Route**: Add to `router.tsx` under the `DashboardLayout` children
3. **Permissions**: Set `permissions` array on the nav item — `useNavigation` hook filters automatically
4. **Page component**: Create in `pages/` (not `pages/admin/`)

```typescript
// config/navigation.ts — mainNavigation
{
  id: 'workspaces',
  title: 'common:navigation.workspaces',
  url: '/workspaces',
  icon: Layout,
  permissions: ['workspaces:read'],
}
```

### Admin Hub

1. **Admin nav config** (`config/adminNav.ts`): Add item to an existing category or create a new one
2. **Route config** (`config/routes.ts`): Add `RouteConfig` with `layout: 'admin'`
3. **Route generation**: Routes are auto-generated via `generateRoutes(adminRoutes)` in `router.tsx`
4. **Page component**: Create in `pages/admin/`

```typescript
// config/adminNav.ts — add to a category
{
  id: 'templates',
  labelKey: 'admin:nav.content.templates',
  path: '/admin/templates',
  icon: FileText,
  permissions: ['templates:read', 'templates:write'],
}
```

### Platform Admin Hub

1. **Platform admin nav config** (`config/platformAdminNav.ts`): Add item
2. **Route config** (`config/routes.ts`): Add with `layout: 'platform-admin'`
3. **Page component**: Create in `pages/platform-admin/`

## Splitting a Feature Across Zones

Some features have pages in multiple zones. This is normal and expected:

- **End-user view** in main sidebar (e.g., "My Reports" dashboard)
- **Admin configuration** in admin hub (e.g., "Report Templates" management)
- Both share the same backend APIs and RTK Query slices

When a feature spans zones, create separate page components for each zone but share:
- RTK Query API slices (`store/api/`)
- Shared types (`types/`)
- Shared utility components (if any)

## Permission Gating (All Zones)

Every zone uses the same permission system:

- **Route-level**: `PermissionGate` wraps the page (auto-applied by `generateRoutes()` for admin routes, manual for main sidebar routes)
- **Nav-level**: `useNavigation` hook filters nav items by permissions
- **Inline**: `PermissionGate` with `fallback` prop hides individual UI elements

See `permissions.md` for the full permission hook and gate API.
