# Smoke Test Generator

Generate and execute contextual smoke tests dynamically based on the specification file and git diff. These smoke tests verify basic functionality of the implemented feature in a real browser environment.

**PERFORMANCE**: This skill uses direct Playwright execution (not MCP), making it ~10x faster than interactive browser control.

**RELIABILITY**: This skill enforces strict selector verification and state validation to prevent flaky tests.

## Variables

spec_file: $ARGUMENT (path to specification file)
adw_id: $ARGUMENT
agent_name: $ARGUMENT if provided, otherwise use 'smoke_test'
application_url: $ARGUMENT if provided, otherwise determine from port configuration:
  - If `.ports.env` exists, source it and use http://localhost:${FRONTEND_PORT}
  - Otherwise use default http://localhost:5173

## Instructions

### 0. Establish Working Directory

**CRITICAL**: This command runs from an isolated worktree directory. All relative paths resolve from this worktree.

1. Get the current working directory and store it:
   ```bash
   WORKTREE_PATH=$(pwd)
   echo "Working directory: $WORKTREE_PATH"
   ```

2. Create necessary directories:
   ```bash
   mkdir -p "${WORKTREE_PATH}/agents/${adw_id}/${agent_name}/img"
   ```

### 1. Check Chrome Availability

Check if Chrome browser automation is available:

```python
import sys
import json
sys.path.insert(0, 'adws')
from adw_modules.utils import is_chrome_available

available, reason = is_chrome_available()
if not available:
    # Output skip JSON
    print(json.dumps({
        "status": "skipped",
        "reason": reason,
        "tests": []
    }))
    sys.exit(0)
```

If Chrome is not available, output the skip JSON and exit successfully.

### 2. Determine Application URL

- If `application_url` was not provided, check for `.ports.env`:
  - If it exists, source it and use http://localhost:${FRONTEND_PORT}
  - Otherwise use default http://localhost:5173

### 3. Analyze Specification File

- Read the `spec_file` to understand what feature was implemented
- Extract key information:
  - Feature description
  - User story
  - Expected UI elements
  - Expected functionality
  - Acceptance criteria

### 4. Analyze Git Changes

Run the following commands to understand what changed:

```bash
# Get list of changed files
git diff origin/main --name-only

# Get detailed changes for UI-related files (frontend/, *.tsx, *.jsx, *.vue, *.html, *.css)
git diff origin/main -- 'app/frontend/**' '*.tsx' '*.jsx' '*.vue' '*.html' '*.css'
```

Focus on:
- New components added
- Modified UI elements
- New routes or pages
- Form fields added
- Button actions

### 5. Research and Document Selectors (REQUIRED)

**CRITICAL**: You MUST complete this step before generating any test JSON. Skipping this step causes flaky tests.

**Step 5a: Identify pages to test**

Based on the spec and git diff, list the pages/routes you will test:
- Example: `/profile`, `/dashboard`, `/settings`

**Step 5b: Read source files and document selectors**

For EACH page you will test, you MUST:
1. Find the component file (e.g., `app/frontend/src/pages/ProfilePage.tsx`)
2. Read the file to extract ACTUAL selectors
3. Document what you found

**Output this table before proceeding:**

```
SELECTOR RESEARCH RESULTS:
==========================
| Page Route | Component File Read | Selectors Found |
|------------|---------------------|-----------------|
| /profile | src/pages/ProfilePage.tsx:1-100 | input[name='firstName'], input[name='lastName'], button[type='submit'] |
| /dashboard | src/pages/Dashboard.tsx:1-150 | [data-testid='stats-card'], table, nav |
```

**DO NOT proceed to step 6 until you have:**
- Read at least ONE source file per page you're testing
- Documented the exact selectors you found (not guessed)
- Verified form fields use `name` attribute (react-hook-form pattern)

### 6. Generate Test Definition JSON

Based on the spec and git diff, generate a test definition JSON file. This is the key step - you're defining WHAT to test, not HOW to interact with the browser step-by-step.

**Create file**: `${WORKTREE_PATH}/agents/${adw_id}/${agent_name}/smoke_tests.json`

**JSON Schema**:
```json
{
  "application_url": "http://localhost:5173",
  "auth": {
    "access_token": "<will be filled in step 6.5>",
    "refresh_token": "<will be filled in step 6.5>"
  },
  "tests": [
    {
      "name": "Test Name - Clear and Descriptive",
      "description": "What this test verifies (1 sentence)",
      "steps": [
        {"action": "navigate", "url": "/dashboard"},
        {"action": "waitForSelector", "selector": "[data-testid='feature-element']", "timeout": 5000},
        {"action": "screenshot", "name": "01_feature_visible.png"},
        {"action": "click", "selector": "[data-testid='action-button']"},
        {"action": "assertVisible", "selector": ".result-element"},
        {"action": "screenshot", "name": "02_action_completed.png"}
      ]
    }
  ]
}
```

**Available Actions**:
| Action | Required Fields | Description |
|--------|----------------|-------------|
| navigate | url | Go to URL (can be relative like "/dashboard") |
| click | selector | Click an element |
| fill | selector, text | Enter text in input field |
| press | key (optional: selector) | Press keyboard key (e.g., "Enter") |
| waitForSelector | selector | Wait for element to appear |
| waitForUrl | url | Wait for URL to match pattern |
| screenshot | name | Take screenshot with given filename |
| assertVisible | selector | Assert element is visible (fails if not) |
| assertHidden | selector | Assert element is hidden |
| assertText | selector, text | Assert element contains text |
| wait | timeout | Simple delay in ms (use sparingly) |
| hover | selector | Hover over element |
| selectOption | selector, text | Select dropdown option by value |

**Test Design Guidelines**:
- Generate 2-4 tests maximum (smoke tests, not comprehensive regression)
- Each test should have 5-10 steps (including mandatory validation steps)
- Focus on:
  1. **UI Visibility** - New elements are visible
  2. **Interactivity** - Buttons/links are clickable
  3. **Form Input** - Forms accept input
  4. **Happy Path** - Main user journey works

### Timeout Guidelines

Use appropriate timeouts for different action types:

| Action Type | Timeout | Reason |
|-------------|---------|--------|
| navigate | 15000ms | Network/SSR can be slow |
| waitForSelector (after navigate) | 10000ms | React hydration takes time |
| waitForSelector (after action) | 5000ms | UI updates should be fast |
| click, fill, hover | 5000ms | Default is fine |
| waitForUrl | 10000ms | Redirects may have delays |
| assertions | 3000ms | Should be immediate |

### MANDATORY Test Structure Pattern

**Every test MUST follow this structure. Deviations cause flaky tests.**

```json
{
  "name": "Feature Name - What It Tests",
  "description": "One sentence describing the verification",
  "steps": [
    // PHASE 1: Navigate and validate page loaded
    {"action": "navigate", "url": "/target-page", "timeout": 15000},
    {"action": "waitForSelector", "selector": "<page-specific-element>", "timeout": 10000},
    {"action": "screenshot", "name": "01_page_loaded.png"},

    // PHASE 2: Verify preconditions before action
    {"action": "assertVisible", "selector": "<element-to-interact-with>"},

    // PHASE 3: Perform action
    {"action": "click", "selector": "<element-to-interact-with>"},

    // PHASE 4: Wait for and verify result
    {"action": "waitForSelector", "selector": "<expected-result-element>", "timeout": 5000},
    {"action": "screenshot", "name": "02_action_result.png"}
  ]
}
```

**Required pattern for each test:**
1. **Navigate** with 15000ms timeout
2. **Wait for page-specific element** with 10000ms timeout (proves correct page loaded)
3. **Screenshot** the initial state
4. **Assert precondition** before any interaction
5. **Perform action** (click, fill, etc.)
6. **Wait for result** (new element, URL change, etc.)
7. **Screenshot** the result

**Anti-patterns that cause flaky tests:**
- ❌ Clicking without first asserting the element is visible
- ❌ Navigating without waiting for page-specific content
- ❌ Using default 5000ms timeout for navigation
- ❌ Assuming page state without verification
- ❌ Multiple actions without intermediate validation

### CRITICAL: Selector Strategy

**You MUST verify selectors exist before using them.** Wrong selectors cause test failures.

**Step 1: Read the actual component source files** to find real selectors:
```bash
# Find the component file for the page you're testing
cat app/frontend/src/pages/ProfilePage.tsx | head -200
```

**Step 2: Use this selector priority order** (most reliable first):

| Priority | Selector Type | Example | When to Use |
|----------|--------------|---------|-------------|
| 1 | data-testid | `[data-testid='submit-btn']` | Best - explicit test hooks |
| 2 | data-* attributes | `[data-sidebar='menu']` | Good - semantic attributes |
| 3 | name attribute | `input[name='firstName']` | Forms - react-hook-form uses name |
| 4 | id attribute | `input#email` | Only if id exists in source |
| 5 | href for links | `a[href='/profile']` | Navigation links |
| 6 | type attribute | `button[type='submit']` | Buttons without IDs |
| 7 | Semantic HTML | `main`, `nav`, `table` | Layout elements |
| 8 | CSS classes | `.card-title` | Last resort - classes can change |

**NEVER use `role` attributes as selectors** - Component libraries (Radix UI, shadcn/ui) dynamically set and override ARIA roles for accessibility. A `role="combobox"` in JSX may become `role="button"` or be removed entirely in the rendered DOM.

**Common patterns in this codebase**:
- Forms use `name` attribute (react-hook-form): `input[name='firstName']`
- Sidebar uses data attributes: `[data-sidebar='sidebar']`, `[data-sidebar='menu']`
- Navigation links use href: `a[href='/files']`, `a[href='/admin/users']`
- Tables are semantic: `table`, `thead`, `tbody`
- Buttons often have type: `button[type='submit']`

**shadcn/ui & Radix UI Components** (CRITICAL):

This codebase uses shadcn/ui components built on Radix UI primitives. These components:
- Use `asChild` prop which merges props onto child elements (may override explicit attributes)
- Dynamically set ARIA roles for accessibility compliance
- Have wrapper elements that may not match your selector expectations

| Component | Trigger Selector Strategy | Notes |
|-----------|---------------------------|-------|
| DropdownMenu | `[data-testid='...']` or `button:has-text('...')` | Never use `role` - Radix overrides it |
| Select | `[data-testid='...']` or `button` inside SelectTrigger | The trigger is a button, not the SelectTrigger itself |
| Dialog | Click trigger button, wait for `[role='dialog']` | Dialog role IS reliable (set by Radix) |
| Popover | `[data-testid='...']` on trigger | Content appears in portal |

**Example - DropdownMenu Actions (common in tables)**:
```tsx
// SOURCE CODE:
<DropdownMenuTrigger asChild>
  <Button data-testid="user-actions-menu" role="combobox">...</Button>
</DropdownMenuTrigger>

// CORRECT selector: [data-testid='user-actions-menu']
// WRONG selector: button[role='combobox']  ← Radix overrides this!
```

**DO NOT**:
- Guess selectors without reading source code
- Use `#id` syntax unless you've confirmed the id exists
- Use dynamic classes like `.css-1abc2de` (generated, will break)
- Assume standard HTML ids exist (e.g., don't assume `#email` - verify it)
- Click on links that are hidden inside dropdowns, modals, or collapsed menus
- Use `role` attribute selectors (e.g., `[role='combobox']`) - component libraries override these
- Trust JSX attributes without verifying rendered DOM (use data-testid for reliability)

**Example - Finding form field selectors**:
```tsx
// In source: <Input name="firstName" ... />
// Correct selector: input[name='firstName']
// WRONG: input#firstName (no id attribute!)

// In source: <Input id="email" name="email" ... />
// Both work: input#email OR input[name='email']
```

### Navigation Strategy

**PREFER direct URL navigation over clicking links:**

When you need to test a page, use the `navigate` action with the URL directly rather than clicking sidebar/menu links. This is more reliable because:
1. Links may be hidden in dropdowns or collapsed menus
2. Links may require hover or click to reveal
3. Direct navigation is faster and more deterministic

```json
// GOOD - Direct navigation (always works)
{"action": "navigate", "url": "/profile"}
{"action": "navigate", "url": "/admin/users"}

// RISKY - Clicking links (may be hidden in dropdowns)
{"action": "click", "selector": "a[href='/profile']"}  // Could be in a dropdown!
```

**When to click links:**
Only use click-based navigation when testing the navigation UI itself:
1. Sidebar main menu items (usually visible): `a[href='/dashboard']`, `a[href='/files']`
2. Links that are always visible in the main content area

**Avoid clicking:**
- Links inside `DropdownMenu` components (require opening dropdown first)
- Links inside collapsed `Collapsible` or `Accordion` components
- Links in user avatar/profile menus (these are always in dropdowns)

**If you MUST test a dropdown menu:**
```json
// 1. Click the dropdown trigger first (use data-testid, NOT role)
{"action": "click", "selector": "[data-sidebar='menu-button']"},
{"action": "wait", "timeout": 300},
// 2. Then click the revealed item
{"action": "click", "selector": "a[href='/profile']"}
```

**Testing Table Row Actions (DropdownMenu pattern)**:

Tables commonly have action menus in each row. The pattern is:
```tsx
// Source code pattern:
<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <Button data-testid="user-actions-menu">...</Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuItem>Edit</DropdownMenuItem>
    <DropdownMenuItem>Delete</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

```json
// CORRECT approach:
{"action": "click", "selector": "[data-testid='user-actions-menu']"},
{"action": "waitForSelector", "selector": "[role='menu']", "timeout": 5000},
{"action": "click", "selector": "[role='menuitem']:has-text('Edit')"}

// WRONG approach (will timeout):
{"action": "click", "selector": "button[role='combobox']"}  // Radix overrides role!
```

**Key insight**: Use `data-testid` for the trigger, but `role='menu'` and `role='menuitem'` for the opened menu content (Radix DOES set these correctly on the portal content).

### 7. Prepare Application

- Read and Execute `.claude/commands/prepare_app.md` to prepare the application for testing

### 7.5 Setup Smoke Test Authentication

Setup authenticated user for smoke tests that require login:

- Read and Execute `.claude/commands/setup_test_auth.md` with the `adw_id`
- Capture the returned auth data (`access_token`, `refresh_token`, etc.)
- **Update the smoke_tests.json file** with the auth tokens:
  ```bash
  # Update the auth section in the JSON file with actual tokens
  ```

### 8. Execute Smoke Tests with Direct Runner

**CRITICAL**: This is the fast path - direct Playwright execution without MCP round-trips.

Run the smoke test runner:

```bash
SMOKE_TEST_HEADLESS=false uv run adws/smoke_test_runner.py \
  "${WORKTREE_PATH}/agents/${adw_id}/${agent_name}/smoke_tests.json" \
  --screenshot-dir "${WORKTREE_PATH}/agents/${adw_id}/${agent_name}/img" \
  --log-file "${WORKTREE_PATH}/agents/${adw_id}/${agent_name}/playwright.log"
```

**Timeout**: Use a 120-second timeout. If it times out, mark tests as skipped.

**Environment Variables**:
- `SMOKE_TEST_HEADLESS=false` - Show browser window (for debugging)
- `SMOKE_TEST_HEADLESS=true` - Headless mode (faster, for CI)

**Logging**:
The `--log-file` option captures all Playwright commands and their results. This is invaluable for debugging authentication failures and test issues. The log includes:
- Commands sent to Playwright (action, selector, url, etc.)
- Command execution time and success/failure status
- Authentication verification results
- Test start/end markers with pass/fail status

**Fail-Fast Authentication**:
The runner automatically verifies authentication after token injection. If the app redirects to the login page (auth failure), all tests fail immediately with a clear error message instead of silently capturing screenshots of the login page.

### 9. Parse and Output Results

The runner outputs JSON directly. Capture and output it.

If the runner fails or times out, output:
```json
[
  {
    "test_name": "Smoke Test Execution",
    "status": "skipped",
    "test_description": "Direct Playwright execution",
    "screenshots": [],
    "error": "Runner timeout or error: <error message>"
  }
]
```

If successful, output the runner's JSON directly (it's already in the correct format).

### 10. Cleanup Smoke Test Data

After all smoke tests complete (regardless of pass/fail):

- Read and Execute `.claude/commands/teardown_test_auth.md` with the `adw_id`

**IMPORTANT**: Always run cleanup, even if tests fail.

## Success Criteria

- Chrome availability is checked before running tests
- If Chrome unavailable, skip JSON is output and execution succeeds
- 2-4 smoke tests are generated based on spec and git diff
- Tests are defined in a JSON file (reusable for retries)
- Direct Playwright runner executes tests at native speed
- Screenshots are captured at key points
- Results are output as valid JSON array
- Test failures are non-blocking (all tests run even if some fail)
- Cleanup always runs

## Performance Notes

This skill is ~10x faster than the MCP-based approach because:
1. Claude generates test definitions ONCE (not per-action decisions)
2. Playwright runs at native speed (no round-trip per action)
3. No Claude "thinking" time between browser actions

Expected execution time:
- Test generation: ~20-30 seconds
- Test execution: ~10-20 seconds (for 2-4 tests)
- Total: ~40-60 seconds (vs 3-5 minutes with MCP)
