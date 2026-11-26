# Skeleton Loaders

**ADW ID:** 20260109111734-06ee647a | **Date:** 2026-01-09
**Specification:** specs/issue-85-adw-20260109111734-06ee647a-sdlc_planner-skeleton-loaders.md

Replaced spinner-based loading states with shape-matching skeleton loaders. Created three specialized components: TableSkeleton, CardSkeleton (default/stats/grid-item variants), and FormSkeleton. Applied consistently across pages with comprehensive test coverage.

## Components & Files

**New Components:**
- `app/frontend/src/components/skeletons/TableSkeleton.tsx` - Table loading states with configurable rows/columns
- `app/frontend/src/components/skeletons/CardSkeleton.tsx` - Three variants: default, stats, grid-item
- `app/frontend/src/components/skeletons/FormSkeleton.tsx` - Form loading states with configurable field count
- `app/frontend/src/components/skeletons/index.ts` - Barrel export

**Updated Pages:**
- `app/frontend/src/components/DataTable.tsx` - Refactored to use TableSkeleton (28→1 lines)
- `app/frontend/src/pages/admin/NotificationsPage.tsx` - CardSkeleton for stats
- `app/frontend/src/pages/FilesPage.tsx` - CardSkeleton variant="grid-item"
- `app/frontend/src/pages/ProfilePage.tsx` - FormSkeleton
- `app/frontend/src/pages/admin/MetricsPage.tsx` - CardSkeleton variant="stats"
- `app/frontend/src/pages/admin/OrganizationMembersPage.tsx` - TableSkeleton
- `app/frontend/src/pages/settings/NotificationPreferencesPage.tsx` - FormSkeleton
- `app/frontend/src/pages/settings/OrganizationSettingsPage.tsx` - FormSkeleton
- `app/frontend/src/components/ui/spinner.tsx` - Deprecation note for page/section loading

**Test Files:**
- `app/frontend/src/components/skeletons/*.test.tsx`

## Architecture

- Single responsibility: dedicated `skeletons/` directory
- TableSkeleton renders actual table headers with skeleton cells
- CardSkeleton supports three use cases: content, stats/metrics, grid items
- FormSkeleton generates label + input field pairs + submit button skeleton
- All components accept optional `className` prop
- Uses base Skeleton from shadcn/ui + Tailwind `animate-pulse`

## Usage

```tsx
import { TableSkeleton, CardSkeleton, FormSkeleton } from '@/components/skeletons'

// Tables and lists
<TableSkeleton
  columns={[
    { key: 'id', header: 'ID', className: 'w-20' },
    { key: 'name', header: 'Name' },
    { key: 'email', header: 'Email' }
  ]}
  rows={5}
/>

// Cards - three variants
<CardSkeleton variant="default" />
<CardSkeleton variant="stats" />
<CardSkeleton variant="grid-item" />

// Forms
<FormSkeleton fields={4} />
```

## Props

| Component | Prop | Type | Default | Options |
|-----------|------|------|---------|---------|
| TableSkeleton | rows | number | 5 | any |
| TableSkeleton | columns | array | required | {key, header, className?} |
| CardSkeleton | variant | string | "default" | "default" \| "stats" \| "grid-item" |
| CardSkeleton | className | string | optional | any |
| FormSkeleton | fields | number | 4 | any |
| FormSkeleton | className | string | optional | any |

## Testing

Run tests: `cd app/frontend && npm run test:run`

## Notes

- Base Skeleton from shadcn/ui unchanged
- Spinner still appropriate for inline loading (buttons, small indicators)
- DataTable auto-loads TableSkeleton when `isLoading={true}`
- Integration tests updated for skeleton states
