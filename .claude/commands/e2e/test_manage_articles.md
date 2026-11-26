# E2E Test: Manage Help Center Articles (Admin)

## Test Description
Validate that administrators can create, edit, and delete help center articles through the admin interface.

## User Story
As an administrator
I want to manage help center articles
So that I can provide up-to-date documentation and help content for users

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with help center management permissions
- At least one help center category exists

## Test Steps

### Test 1: Access Admin Articles Management Page

**Steps:**
1. Login as admin user
2. Navigate to admin help center management page (e.g., `/admin/help-center/articles`)
3. **Screenshot:** Articles management page
4. Verify page title shows "Manage Articles" or similar
5. Verify articles table/list is displayed
6. Verify "Create Article" button is present
7. Verify existing articles show: title, category, status, actions

**Expected Results:**
- Admin can access articles management page
- Articles are fetched from `GET /help-center/articles`
- Table shows all articles with relevant columns
- Create button is visible and enabled

### Test 2: Create New Article

**Steps:**
1. Navigate to admin articles management page
2. Click "Create Article" button
3. **Screenshot:** Create article form/dialog
4. Fill in article details:
   - Title: "Test Article Title"
   - Slug: "test-article-title" (or auto-generated)
   - Category: Select from dropdown
   - Body: "# Test Content\n\nThis is test content with **bold** and *italic* text."
5. **Screenshot:** Filled form
6. Click "Save" or "Create" button
7. Wait for success response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify new article appears in the list
11. Verify article can be viewed on help center

**Expected Results:**
- Create form opens with all required fields
- Form validates required fields (title, body, category)
- Article is created via `POST /help-center/articles`
- Success notification shown
- Article appears in list and is viewable

### Test 3: Edit Existing Article

**Steps:**
1. Navigate to admin articles management page
2. Locate an existing article in the list
3. Click "Edit" button/action for the article
4. **Screenshot:** Edit article form with pre-filled data
5. Verify form is pre-filled with existing article data
6. Modify article title: "Updated Article Title"
7. Modify article body: Add new paragraph
8. **Screenshot:** Modified form
9. Click "Save" or "Update" button
10. Wait for success response
11. **Screenshot:** Success state
12. Verify success toast notification
13. Verify article shows updated data in list
14. Navigate to article page and verify changes

**Expected Results:**
- Edit form opens with existing data pre-filled
- Changes are saved via `PUT /help-center/articles/{id}`
- Success notification shown
- Article list reflects changes
- Article page shows updated content

### Test 4: Delete Article

**Steps:**
1. Navigate to admin articles management page
2. Locate an article to delete
3. Note the article title for verification
4. Click "Delete" button/action for the article
5. **Screenshot:** Delete confirmation dialog
6. Verify confirmation dialog appears
7. Verify dialog shows article title being deleted
8. Click "Confirm" or "Delete" button
9. Wait for success response
10. **Screenshot:** Success state after deletion
11. Verify success toast notification
12. Verify article is removed from list
13. Try to access deleted article URL
14. Verify 404 error is shown

**Expected Results:**
- Delete requires confirmation
- Article is deleted via `DELETE /help-center/articles/{id}`
- Success notification shown
- Article removed from list
- Deleted article URL returns 404

### Test 5: Article Form Validation

**Steps:**
1. Navigate to admin articles management page
2. Click "Create Article" button
3. Click "Save" without filling any fields
4. **Screenshot:** Validation errors
5. Verify title field shows required error
6. Verify body field shows required error
7. Verify category field shows required error
8. Enter only title, leave body empty
9. Click "Save"
10. Verify body validation error persists
11. Fill all required fields correctly
12. Verify form can now be submitted

**Expected Results:**
- Empty form submission shows validation errors
- All required fields must be filled
- Validation messages are clear and helpful
- Form submits only with valid data

### Test 6: Article Slug Handling

**Steps:**
1. Click "Create Article" button
2. Enter title: "My New Article About Features"
3. Verify slug is auto-generated: "my-new-article-about-features"
4. Manually modify slug to: "custom-slug"
5. **Screenshot:** Custom slug entered
6. Save the article
7. Verify article is accessible at `/help-center/articles/custom-slug`
8. Edit the article
9. Try to change slug to invalid format: "Invalid Slug!"
10. Verify slug validation error

**Expected Results:**
- Slug auto-generates from title
- Custom slugs are allowed
- Slug format validation enforced
- Article accessible at custom slug URL

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/help-center/articles` | List all articles |
| POST | `/help-center/articles` | Create new article |
| PUT | `/help-center/articles/{id}` | Update existing article |
| DELETE | `/help-center/articles/{id}` | Delete article |
| GET | `/help-center/categories` | Get categories for dropdown |

## Request/Response Format

**Create Article Request:**
```json
{
  "title": "Test Article Title",
  "slug": "test-article-title",
  "body": "# Test Content\n\nThis is test content.",
  "category_id": "uuid",
  "featured_image_url": "https://..."
}
```

**Create Article Response:**
```json
{
  "id": "uuid",
  "title": "Test Article Title",
  "slug": "test-article-title",
  "body": "# Test Content\n\nThis is test content.",
  "category": { "id": "uuid", "name": "Category Name" },
  "created_at": "2024-01-15T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|add article/i })` |
| Articles table | Table element with article rows |
| Edit button | `getByRole('button', { name: /edit/i })` per row |
| Delete button | `getByRole('button', { name: /delete/i })` per row |
| Title input | `getByLabelText(/title/i)` |
| Slug input | `getByLabelText(/slug/i)` |
| Body textarea | `getByLabelText(/body|content/i)` |
| Category select | `getByLabelText(/category/i)` |
| Save button | `getByRole('button', { name: /save|create|update/i })` |
| Confirm delete | `getByRole('button', { name: /confirm|delete/i })` in dialog |

## Success Criteria

- Admin can access articles management
- CRUD operations work correctly
- Form validation prevents invalid submissions
- Slug auto-generation and custom slugs work
- Delete requires confirmation
- Success/error notifications display properly
- Changes reflect in help center immediately

## Notes

- Verify admin permissions are required
- Test with markdown preview if available
- Verify image upload for featured images
- Test category assignment changes
- Verify i18n translations in admin interface
