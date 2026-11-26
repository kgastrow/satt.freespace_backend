# E2E Test: Read Help Center Article

## Test Description
Validate that users can navigate to and read individual help center articles with proper content rendering, breadcrumbs, and navigation.

## User Story
As a user
I want to read individual help center articles
So that I can get detailed information about specific topics

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user session
- At least one published help center article exists with:
  - Valid slug
  - Markdown content with formatting
  - Associated category

## Test Steps

### Test 1: Navigate to Article from Help Center

**Steps:**
1. Navigate to `/help-center`
2. Wait for articles to load
3. Click on an article card
4. **Screenshot:** Article page loaded
5. Verify URL changes to `/help-center/articles/<slug>`
6. Verify article title is displayed as heading
7. Verify breadcrumb navigation shows: Help Center > Category > Article Title
8. Verify article content is rendered

**Expected Results:**
- Navigation from help center to article works
- Article page loads with correct content
- URL uses article slug
- Breadcrumbs provide navigation context

### Test 2: Article Content Rendering

**Steps:**
1. Navigate directly to `/help-center/articles/<known-slug>`
2. **Screenshot:** Article content
3. Verify article title (h1 heading) is displayed
4. Verify article body content is rendered
5. Verify markdown formatting is applied:
   - Headings (h2, h3)
   - Bold and italic text
   - Lists (ordered and unordered)
   - Code blocks (if present)
   - Links (if present)
6. Verify content is properly sanitized (no raw HTML injection)

**Expected Results:**
- Article content renders with proper markdown formatting
- HTML is sanitized via DOMPurify
- Content is readable and well-formatted
- Code blocks have proper styling

### Test 3: Breadcrumb Navigation

**Steps:**
1. Navigate to `/help-center/articles/<known-slug>`
2. **Screenshot:** Breadcrumb navigation
3. Verify breadcrumb structure: Help Center > [Category] > [Article Title]
4. Click on "Help Center" breadcrumb link
5. Verify redirect to `/help-center`
6. Navigate back to article
7. Click on category breadcrumb link
8. Verify redirect to help center with category filter applied

**Expected Results:**
- Breadcrumbs show correct hierarchy
- All breadcrumb links are functional
- Category breadcrumb filters help center by that category

### Test 4: Article Not Found (Invalid Slug)

**Steps:**
1. Navigate to `/help-center/articles/invalid-slug-that-does-not-exist`
2. Wait for API response
3. **Screenshot:** 404 error state
4. Verify error message is displayed
5. Verify "Back to Help Center" button is present
6. Click "Back to Help Center" button
7. Verify redirect to `/help-center`

**Expected Results:**
- Invalid slug shows 404/not found state
- User-friendly error message displayed
- Navigation back to help center works

### Test 5: Invalid Slug Format Validation

**Steps:**
1. Navigate to `/help-center/articles/INVALID_SLUG!@#`
2. **Screenshot:** Invalid slug error
3. Verify slug format validation triggers
4. Verify appropriate error message displayed

**Expected Results:**
- Slug format validation works (`^[a-z0-9]+(?:-[a-z0-9]+)*$`)
- Invalid slugs are rejected before API call
- User sees validation error message

### Test 6: Direct URL Access to Article

**Steps:**
1. Copy article URL `/help-center/articles/<valid-slug>`
2. Open new browser tab/window
3. Paste and navigate to URL directly
4. **Screenshot:** Direct access article page
5. Verify article loads correctly
6. Verify all content is displayed
7. Verify breadcrumbs work

**Expected Results:**
- Direct URL access works (deep linking)
- Article loads without requiring navigation from help center
- All functionality works on direct access

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/help-center/articles/{slug}` | Fetch individual article by slug |

## Request/Response Format

**Get Article Response:**
```json
{
  "id": "uuid",
  "title": "How to Get Started",
  "slug": "how-to-get-started",
  "body": "# Getting Started\n\nThis guide will help you...",
  "category": {
    "id": "uuid",
    "name": "Getting Started",
    "slug": "getting-started"
  },
  "featured_image_url": "https://...",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

**Error Response (404):**
```json
{
  "detail": "Article not found"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Article title | `getByRole('heading', { level: 1 })` |
| Breadcrumb nav | `nav[aria-label="breadcrumb"]` or breadcrumb container |
| Breadcrumb links | Links within breadcrumb navigation |
| Article content | Main content container with rendered markdown |
| Back button | `getByRole('button', { name: /back to help center/i })` |
| Error message | Error alert or message container |

## Success Criteria

- Articles load correctly from help center navigation
- Direct URL access works for articles
- Markdown content renders properly with formatting
- Breadcrumb navigation is functional
- Invalid slugs show appropriate error handling
- Content is properly sanitized

## Notes

- Test with articles containing various markdown elements
- Verify XSS protection via DOMPurify sanitization
- Test article with and without featured images
- Verify i18n translations for UI elements
- Test responsive layout for article content
