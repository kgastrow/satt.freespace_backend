# E2E Test: Browse Help Center Articles

## Test Description
Validate that users can browse the help center, view categories, search for articles, and navigate between articles and FAQs.

## User Story
As a user
I want to browse the help center
So that I can find answers to my questions and learn how to use the application

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user session
- Help center has:
  - At least 2 categories with articles
  - At least 3 articles (including one featured)
  - At least 2 FAQs

## Test Steps

### Test 1: View Help Center Page with Categories

**Steps:**
1. Navigate to `/help-center`
2. **Screenshot:** Help center page loaded
3. Verify page title "Help Center" is displayed
4. Verify search input field is present
5. Verify category filter buttons are displayed
6. Verify "Articles" and "FAQs" tabs are present
7. Verify article cards are displayed in grid layout
8. Verify at least one featured article has a featured image

**Expected Results:**
- Help center page loads successfully
- Categories are fetched from `GET /help-center/categories`
- Articles are fetched from `GET /help-center/articles`
- Default tab is "Articles"
- Article cards show title, excerpt, and category badge

### Test 2: Filter Articles by Category

**Steps:**
1. Navigate to `/help-center`
2. Note the current article count
3. Click on a specific category button
4. **Screenshot:** Filtered articles view
5. Verify only articles from selected category are shown
6. Verify category button shows active/selected state
7. Click "All" category button
8. Verify all articles are shown again

**Expected Results:**
- Category filter works correctly
- API call includes category filter parameter
- Article count updates based on filter
- Active category is visually indicated

### Test 3: Search Help Center

**Steps:**
1. Navigate to `/help-center`
2. Enter search term in search input (e.g., "getting started")
3. Wait for search debounce (500ms)
4. **Screenshot:** Search results
5. Verify search results are displayed
6. Verify results include articles matching search term
7. Clear search input
8. Verify original articles list is restored

**Expected Results:**
- Search uses `GET /help-center/search` endpoint
- Search results show matching articles and FAQs
- Empty search restores original listing
- Search is debounced to prevent excessive API calls

### Test 4: Switch Between Articles and FAQs Tabs

**Steps:**
1. Navigate to `/help-center`
2. Verify "Articles" tab is active by default
3. Click "FAQs" tab
4. **Screenshot:** FAQs tab view
5. Verify FAQs are displayed in accordion format
6. Click on an FAQ to expand it
7. Verify FAQ answer is displayed
8. Click on the same FAQ to collapse it
9. Verify FAQ answer is hidden
10. Click "Articles" tab
11. Verify article cards are displayed again

**Expected Results:**
- Tab switching works correctly
- FAQs are fetched from `GET /help-center/faqs`
- FAQ accordion expands/collapses on click
- Tab state is maintained during session

### Test 5: View Article Card Details

**Steps:**
1. Navigate to `/help-center`
2. Locate an article card in the grid
3. **Screenshot:** Article card
4. Verify article card shows:
   - Title
   - Excerpt/description
   - Category badge
   - Featured image (if applicable)
5. Verify card is clickable/has hover state

**Expected Results:**
- Article cards display all required information
- Cards have proper visual feedback on hover
- Cards link to individual article pages

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/help-center/categories` | Fetch help center categories |
| GET | `/help-center/articles` | Fetch articles (with optional category filter) |
| GET | `/help-center/faqs` | Fetch FAQs |
| GET | `/help-center/search` | Search articles and FAQs |

## Request/Response Format

**Get Categories Response:**
```json
{
  "categories": [
    { "id": "uuid", "name": "Getting Started", "slug": "getting-started" },
    { "id": "uuid", "name": "Account", "slug": "account" }
  ]
}
```

**Get Articles Response:**
```json
{
  "articles": [
    {
      "id": "uuid",
      "title": "How to Get Started",
      "slug": "how-to-get-started",
      "excerpt": "Learn the basics...",
      "category": { "id": "uuid", "name": "Getting Started" },
      "featured_image_url": "https://..."
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page title | `getByRole('heading', { name: /help center/i })` |
| Search input | `getByPlaceholder(/search/i)` or `input[type="search"]` |
| Category buttons | `getByRole('button', { name: /<category-name>/i })` |
| Articles tab | `getByRole('tab', { name: /articles/i })` |
| FAQs tab | `getByRole('tab', { name: /faqs/i })` |
| Article cards | `[data-testid="article-card"]` or article card elements |
| FAQ accordions | Accordion trigger elements |

## Success Criteria

- Help center page loads with categories and articles
- Category filtering works correctly
- Search returns relevant results
- Tab switching between Articles and FAQs works
- FAQ accordion expands/collapses properly
- All UI elements are properly translated

## Notes

- Verify i18n translations for all labels and headings
- Test with empty categories (no articles)
- Test search with no results
- Verify responsive layout on different screen sizes
