# Feedback Widget System

**ADW ID:** 20260115222931-020a6fe1 | **Date:** 2026-01-16
**Specification:** specs/multi-phase/issue-159-adw-20260115222931-020a6fe1-multi-phase.md

User feedback collection system with floating widget, S3 attachments, admin dashboard, role-based permissions, and full i18n support (en, de, xh, zu, nso).

## Architecture

**Backend:**
- Models: `app/backend/src/models/feedback.py` - Feedback and FeedbackAttachment SQLAlchemy models with indexes
- CRUD: `app/backend/src/crud/feedback.py` - Async operations with organization-scoped filtering, pagination
- API: `app/backend/src/api/feedback.py` - FastAPI endpoints with authentication and permission checks
- Serializers: `app/backend/src/serialisers/feedback.py` - Pydantic v2 request/response models
- Migration: `app/backend/alembic/versions/78cedf331de5_add_feedback_models.py`
- Seed: `app/backend/scripts/seed_first_tenant.py` - Feedback permissions and feature flag
- Tests: `app/backend/tests/unit_tests/test_feedback.py` - 2206 lines covering models, CRUD, API, multi-tenancy

**Frontend:**
- API: `app/frontend/src/features/feedback/feedbackApi.ts` - RTK Query endpoints
- Types: `app/frontend/src/features/feedback/types.ts` - TypeScript schemas
- Widget: `app/frontend/src/features/feedback/components/FeedbackWidget.tsx` - Floating button with feature flag
- Form: `app/frontend/src/features/feedback/components/FeedbackForm.tsx` - React Hook Form + Zod validation, screenshot capture, file upload
- Rating: `app/frontend/src/features/feedback/components/StarRating.tsx`
- List: `app/frontend/src/features/feedback/pages/FeedbackListPage.tsx` - DataTable with filters, bulk actions
- Detail: `app/frontend/src/features/feedback/pages/FeedbackDetailPage.tsx` - Attachments viewer, response panel
- Filters: `app/frontend/src/features/feedback/components/FeedbackFilters.tsx`
- Response: `app/frontend/src/features/feedback/components/FeedbackResponsePanel.tsx` - Admin response and status management
- Stats: `app/frontend/src/features/feedback/components/FeedbackStatsCard.tsx`
- Routes: `app/frontend/src/router.tsx` - /admin/feedback and /admin/feedback/:id
- Sidebar: `app/frontend/src/components/AppSidebar.tsx` - Feedback menu with permission check
- i18n: `app/frontend/src/locales/{en,de,xh,zu,nso}/feedback.json`

## Key Design Patterns

- **Multi-tenancy**: All queries filter by `organization_id`; super admins can filter across orgs
- **Soft deletes**: Uses `deleted_time` field, never hard deletes
- **Auto-capture**: Page URL, user agent, screen resolution on submission
- **Attachments**: Screenshots and files up to 5MB via S3 with org-scoped paths
- **Validation**: Rating (1-5), subject (100 chars), message (2000 chars)
- **Permissions**: feedback:view (Org Admin/Owner/Super Admin), feedback:respond (same), feedback:delete (Owner/Super Admin only)
- **Feature flag**: `feedback_widget` enables per-organization rollout

## Usage

**End Users:** Click floating button (bottom-right) → Select type (bug/suggestion/complaint/praise/other) → Rate (1-5 stars) → Enter subject (100 char max) + message (2000 char max) → Optionally attach screenshot/file → Submit

**Admins:** Feedback menu (requires feedback:view) → Filter by type/status/rating/date/org → Bulk actions: resolve/dismiss/export CSV → Click item for details → Add response or internal notes → Update status or delete (requires feedback:delete)

## Testing & Deployment

Run backend tests: `cd app/backend && make test`
Run frontend tests: `cd app/frontend && npm run test`
Build frontend: `npm run build` (regenerates types from OpenAPI schema)

No additional environment variables required. Uses existing S3 configuration for file attachments.

## Database Optimization

Indexes on:
- organization_id + status
- organization_id + type
- organization_id + created_time
