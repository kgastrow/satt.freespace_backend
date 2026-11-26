# Help Center / Support Hub

**ADW ID:** 20260114171939-02d3aa57 | **Date:** 2026-01-14 | **Specification:** specs/multi-phase/issue-132-adw-20260114171939-02d3aa57-multi-phase.md

Self-service Help Center with searchable FAQs, articles, and admin content management. Accessible from header dropdown with draft/publish workflow, category organization, rich content support (markdown/HTML), and full i18n (5 languages).

## Technical Implementation

### Backend Files
- `app/backend/src/models/help_center.py` - SQLAlchemy 2.0 async models: HelpCategory, HelpArticle, HelpFaq (multi-tenant with nullable organization_id)
- `app/backend/src/crud/help_center.py` - Async CRUD operations (~1018 lines)
- `app/backend/src/serialisers/help_center.py` - Pydantic v2 serializers for validation
- `app/backend/src/api/help_center.py` - FastAPI router (18 endpoints, ~751 lines)
- `app/backend/alembic/versions/4ad987d47864_add_help_center_tables.py` - Database migration
- `app/backend/tests/unit_tests/test_help_center.py` - Comprehensive tests (~1034 lines)

### Frontend Files
- `app/frontend/src/pages/HelpCenterPage.tsx` - Public help center with search and tabs
- `app/frontend/src/pages/HelpArticlePage.tsx` - Individual article view with breadcrumb
- `app/frontend/src/pages/admin/HelpCenterPage.tsx` - Admin landing page
- `app/frontend/src/pages/admin/HelpArticlesPage.tsx` - Article management with rich editor (~532 lines)
- `app/frontend/src/pages/admin/HelpFaqsPage.tsx` - FAQ management with reordering (~444 lines)
- `app/frontend/src/pages/admin/HelpCategoriesPage.tsx` - Category management (~356 lines)
- `app/frontend/src/store/api/helpCenterApi.ts` - RTK Query API slice (~375 lines)
- `app/frontend/src/types/helpCenter.ts` - TypeScript definitions
- `app/frontend/src/components/ui/accordion.tsx` - Accordion component (Radix UI)
- `app/frontend/src/components/ui/breadcrumb.tsx` - Breadcrumb navigation component
- `app/frontend/src/components/HeaderUserMenu.tsx` - Added Help Center link
- `app/frontend/src/components/AppSidebar.tsx` - Added Help Center to Super Admin section
- `app/frontend/src/router.tsx` - Added routes
- `app/frontend/package.json` - Added dompurify dependency
- All locale files (en, de, xh, zu, nso) - Translation keys: `helpCenter`, `admin`

### Database Schema
Migration `4ad987d47864_add_help_center_tables.py` creates three tables:
- **help_category**: slug, name, description, display_order
- **help_article**: title, slug, content (TEXT), status enum, category_id, featured_image_url, organization_id (nullable)
- **help_faq**: question, answer, status enum, category_id, display_order, organization_id (nullable)

All tables: id (UUID), created_time, updated_time, deleted_time (soft delete)

### Architecture Decisions
- **Multi-tenancy**: Platform-wide by default (organization_id = NULL) with optional org-specific content
- **Draft/Publish**: Status enum (draft/published) gates live visibility; published endpoints filter status
- **Security**: DOMPurify sanitization for HTML content; super admin endpoints require `get_current_super_admin` dependency
- **Search**: PostgreSQL ILIKE pattern matching on titles, questions, and content fields
- **Component Reusability**: Follows AnnouncementsPage.tsx patterns (data tables, dialog forms, confirmation dialogs)

## API Endpoints

**Public (no auth):**
- GET `/api/help/categories`
- GET `/api/help/articles` (filterable by category)
- GET `/api/help/articles/{slug}`
- GET `/api/help/faqs` (filterable by category)
- GET `/api/help/search?q={query}`

**Admin (super admin only):**
- POST/PUT/DELETE `/api/help/categories/*`
- POST/PUT/DELETE `/api/help/articles/*`
- POST/PUT/DELETE `/api/help/faqs/*`

## Routes
- `/help-center` - Public help center
- `/help-center/:slug` - Individual article
- `/admin/help-center` - Admin landing
- `/admin/help-center/articles` - Article management
- `/admin/help-center/faqs` - FAQ management
- `/admin/help-center/categories` - Category management

## User Guide

### End Users
1. Access Help Center from header profile menu (opens new tab)
2. Search by keyword or filter by category
3. View FAQs in accordion format or browse article cards
4. Navigate to articles with breadcrumb navigation
5. Contact support link at bottom

### Super Administrators
1. Navigate to sidebar → Super Admin → Help Center
2. Create/manage categories with display order
3. Create articles with markdown/HTML content and featured image URL
4. Create FAQs with display order within category
5. Save as draft or publish immediately
6. Edit/delete using table actions (soft delete)

## Testing

Run backend tests:
```bash
cd app/backend
make test
```

Coverage: model instantiation, CRUD with tenant isolation, public/authenticated endpoints, search, draft/publish workflow, soft deletes

Frontend tests:
```bash
cd app/frontend
npm run test
```

Manual checklist: header link, search/category filtering, accordion/breadcrumb behavior, admin CRUD, draft/publish workflow, HTML sanitization, responsive layout, i18n

## Dependencies
- **Backend**: SQLAlchemy 2.0 async, Pydantic v2, PostgreSQL ENUM
- **Frontend**: dompurify (^3.2.4), @radix-ui/react-accordion (^1.2.2), Redux Toolkit, React Hook Form, Zod

## Future Enhancements
- **Rich Text Editor**: Implement WYSIWYG for markdown/HTML authoring
- **Full-Text Search**: Replace ILIKE with PostgreSQL tsvector/tsquery or Elasticsearch for scale
- **Caching**: Redis caching for frequently accessed published content
- **Organization-Specific Content**: Leverage nullable organization_id for multi-org help resources
