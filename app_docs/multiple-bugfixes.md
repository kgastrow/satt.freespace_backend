# Multiple Bugfix Collection

**ADW ID:** 20260115145816-d8c99769 | **Date:** 2026-01-15 | **Specification:** specs/multi-phase/issue-147-adw-20260115145816-d8c99769-multi-phase.md

## Overview

Collection of 8 independent bug fixes: impersonation session endpoint HTTP status, user profile organization data, help categories drag-and-drop, API key permission codes, announcement image upload, media visibility in files, and 2FA organization settings.

## Bugs Addressed

1. **Impersonation Session (Phase 1)**: GET `/api/v1/admin/impersonate/session` now returns 200 with `{ active: false }` instead of 404 when inactive
2. **User Profile Organization (Phase 2)**: GET `/api/v1/user/me` includes full organization object instead of just organization_id
3. **Help Categories Drag-and-Drop (Phase 3)**: Added reorder functionality to HelpCategoriesPage using SortableList
4. **API Key Permission Codes (Phase 4)**: Use permission codes (strings) instead of UUIDs; validate non-empty permissions
5. **API Key Edit Dialog (Phase 5)**: Show only assigned permissions for specific API keys
6. **Announcement Image Upload (Phase 6)**: Fixed callback to properly set featured_image_url
7. **Media in Files Listing (Phase 7)**: Include media records in files API via _media_to_file_dict() helper
8. **Organization 2FA Toggle (Phase 8)**: Added super admin toggle in OrganizationsPage

## Implementation

### Backend Files
- `app/backend/src/api/impersonation.py`: Return ImpersonationSessionStatusResponse with active flag
- `app/backend/src/serialisers/impersonation_session.py`: ImpersonationSessionStatusResponse model
- `app/backend/src/api/user.py`: Eager load organization in /user/me endpoint
- `app/backend/src/serialisers/user.py`: Add organization field to UserProfileResponse
- `app/backend/src/api/api_key.py`: Validate non-empty permissions on creation
- `app/backend/src/crud/file.py`: Add _media_to_file_dict() helper; update get_files() to merge media records
- `app/backend/src/crud/file_usage.py`: Include media table in storage calculations
- `app/backend/tests/unit_tests/test_bugfixes_issue_147.py`: Comprehensive test suite (730+ lines)

### Frontend Files
- `app/frontend/src/pages/admin/HelpCategoriesPage.tsx`: SortableList drag-and-drop reorder
- `app/frontend/src/pages/admin/ApiKeysPage.tsx`: Send permission codes instead of UUIDs; show assigned permissions in edit dialog
- `app/frontend/src/components/permissions/ApiKeyPermissionSelector.tsx`: Track/return permission codes; filter by assigned
- `app/frontend/src/pages/admin/AnnouncementsPage.tsx`: Fix handleImageUploadSuccess to set featured_image_url
- `app/frontend/src/components/MediaUploader.tsx`: Updated onUploadSuccess callback format
- `app/frontend/src/pages/admin/OrganizationsPage.tsx`: Add 2FA toggle with load2FASettings and handleToggle2FA
- `app/frontend/src/features/organizations/organizationsApi.ts`: Add get/set org 2FA endpoints
- `app/frontend/src/locales/*.json`: i18n translations (en, de, xh, zu, nso)

## Key Changes

- **API Consistency**: Impersonation endpoint returns 200 with status flag instead of 404
- **Enhanced User Profile**: Organization data eagerly loaded to reduce frontend API calls
- **Media-Files Unification**: Media records merged at CRUD layer via _media_to_file_dict() helper
- **Permission Architecture**: Permission codes (strings) consistently used instead of UUIDs
- **Storage Calculations**: Both file and media tables included in quota calculations
- **Admin UX**: Drag-and-drop reordering, 2FA controls, and image upload fixes

## Usage Examples

### Impersonation Session Check
```typescript
const response = await api.get('/admin/impersonate/session')
if (response.active) {
  console.log('Impersonating:', response.session)
} else {
  // User is not impersonating
}
```

### User Organization Data
```typescript
const user = await api.get('/user/me')
console.log(user.organization.name)
console.log(user.organization.slug)
```

### Help Categories Reorder
1. Navigate to Admin > Help Center > Categories
2. Click "Reorder" button
3. Drag categories to desired order
4. Click "Save Order" to persist

### API Key Permissions
1. Navigate to Admin > API Keys
2. Click "Create API Key" and select permissions (minimum one required)
3. Backend receives permission codes, frontend sends codes instead of UUIDs
4. Edit dialog shows only assigned permissions

### Announcement Images
Drag and drop image onto MediaUploader; featured_image_url automatically populated.

### Files Listing
Media uploads now appear in user and admin Files pages; storage calculations include media.

### Organization 2FA
Super admins can toggle 2FA per organization via "2FA Allowed" column in Organizations page.

## Dependencies

- **Phase 5 depends on Phase 4**: Permission selector changes affect how permissions are tracked
- **All other phases are independent**
- Single test file (`test_bugfixes_issue_147.py`) consolidates all backend tests
- All changes use existing infrastructure and are backward-compatible

## Testing

```bash
cd app/backend && make test          # Run all backend tests
cd app/frontend && npm run test      # Run frontend tests
cd app/frontend && npm run build     # Verify build and type generation
```

Test coverage: impersonation session status, user profile organization data, API key validation, media-in-files, storage calculations, and i18n compliance (all 5 locales).
