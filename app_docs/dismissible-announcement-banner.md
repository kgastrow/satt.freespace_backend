# Dismissible Announcement Banner

**ADW ID:** 20260113151705-126ea7b8 | **Date:** 2026-01-14 | **Spec:** specs/multi-phase/issue-125-adw-20260113151705-126ea7b8-multi-phase.md

Organization and platform-wide dismissible announcement system with priority levels, scheduling, CTA buttons, and per-user dismissal tracking. Stacked card UI with smooth animations.

## Architecture

**Backend:**
- Models: `Announcement`, `AnnouncementDismissal` with multi-tenancy (NULL `organization_id` = platform-wide)
- CRUD: Tenant-isolated queries combining org-specific + platform-wide announcements
- API: Full REST endpoints with permission checks
- Migration: `95cf50fe008c_add_announcement_tables.py`

**Frontend:**
- Types: `app/frontend/src/types/announcement.ts`
- State: RTK Query API + Redux slice with optimistic updates
- Components: `AnnouncementBanner` (fixed-position stacked display), `AnnouncementCard` (individual card, 200 lines)
- Hook: `useAnnouncements` for sorted announcements and dismissal actions
- Integration: `RootLayout.tsx` (positioned at 56px from top)

**Features:**
- Multi-tenancy: org-scoped and platform-wide
- Priorities: critical > high > normal > low
- Scheduling: start/end date visibility control
- Customization: background color, featured image, CTA styling
- Dismissal: per-user persistent state
- Non-dismissible mode: forces CTA engagement
- Visual: stacked deck (3 cards max), 8px vertical offset, 2% scale reduction per card

## File Locations

**Backend:**
- Models: `app/backend/src/models/announcement.py`, `app/backend/src/models/announcement_dismissal.py`
- CRUD: `app/backend/src/crud/announcement.py`, `app/backend/src/crud/announcement_dismissal.py`
- API: `app/backend/src/api/announcement.py` (306 lines)
- Serializers: `app/backend/src/serialisers/announcement.py`
- Tests: `app/backend/tests/unit_tests/test_announcement.py` (1195 lines)
- Migration: `app/backend/alembic/versions/95cf50fe008c_add_announcement_tables.py`

**Frontend:**
- Types: `app/frontend/src/types/announcement.ts`
- API: `app/frontend/src/features/announcements/announcementsApi.ts`
- State: `app/frontend/src/features/announcements/announcementsSlice.ts`
- Hook: `app/frontend/src/hooks/useAnnouncements.ts`
- Components: `app/frontend/src/components/AnnouncementBanner.tsx`, `AnnouncementCard.tsx`
- Tests: `app/frontend/src/components/AnnouncementBanner.test.tsx` (506 lines), `announcementsSlice.test.ts` (256 lines)

## Key Patterns

**Multi-Tenancy:** NULL `organization_id` = platform-wide; UUID = org-specific. Queries fetch both scopes.

**Sorting Order:**
1. Non-dismissible first
2. Priority: critical → high → normal → low
3. Platform-wide before org-specific
4. Newest first (created_time)

**Permissions:**
- `announcements:read` - View announcements (admin)
- `announcements:write` - Create/update (org owner/admin)
- `announcements:delete` - Delete (org owner/admin)
- Super admins create platform-wide (NULL organization_id)

**UI:** Absolute positioning with calculated offsets. Top card fully visible; up to 2 cards peek behind with 8px vertical offset and 2% scale reduction per card.

**Optimistic Updates:** Dismissal updates UI immediately while API call completes in background.

## API Endpoints

```bash
# Get active announcements for current user
GET /api/v1/announcements/active

# Create announcement (org_id auto-populated from context, or NULL for platform-wide)
POST /api/v1/announcements
{
  "title": "string",
  "body": "string",
  "priority": "critical|high|normal|low",
  "start_time": "2026-01-15T00:00:00Z",  # optional
  "end_time": "2026-01-20T00:00:00Z",     # optional
  "is_dismissible": true,
  "cta_text": "string",                    # optional
  "cta_url": "string",                    # optional
  "background_color": "string",           # optional
  "featured_image_url": "string"          # optional
}

# Dismiss announcement
POST /api/v1/announcements/{announcement_id}/dismiss

# List all announcements (admin)
GET /api/v1/announcements

# Update announcement
PUT /api/v1/announcements/{announcement_id}

# Delete announcement (soft delete)
DELETE /api/v1/announcements/{announcement_id}
```

## Database Schema

Two tables:
- **announcement:** Announcement definitions with org scoping. Indexes on `organization_id`, `priority`, `start_time`, `end_time`. Soft deletes via `deleted_time`.
- **announcement_dismissal:** User dismissals with unique constraint on (announcement_id, user_id). Tracks per-user dismissal state.

## Testing

**Backend:** `cd app/backend && make test`
- Model relationships and CRUD with multi-tenancy
- API endpoints and permissions
- Dismissal tracking and tenant isolation
- Non-dismissible, platform-wide, priority sorting edge cases

**Frontend:** `cd app/frontend && npm run test`
- Component rendering, dismissal, CTA clicks, stacked display
- Redux state updates, sorting, optimistic updates

**Manual:** Create announcements with different priorities/scopes, verify stacking (max 3), dismiss animations, non-dismissible CTAs, scheduling (appear/disappear), tenant isolation, platform-wide as super admin.

## Notes

- Soft deletes via `deleted_time`, never hard deleted
- RTK Query invalidates cache on mutations
- CSS transitions for 60fps animations
- Keyboard accessible dismiss/CTA buttons
- Mobile responsive with adaptive padding/scaling
- No new environment variables required
