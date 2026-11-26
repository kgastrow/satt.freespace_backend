# Review

Follow the `Instructions` below to **review work done against a specification file** (specs/*.md) to ensure implemented features match requirements. Use the spec file to understand the requirements and then use the git diff if available to understand the changes made. Capture screenshots of critical functionality paths. If there are issues, report them if not then report success.

**PERFORMANCE**: This skill uses direct Playwright execution (not MCP), making it ~10x faster than interactive browser control.

## Variables

adw_id: $1
spec_file: $2
agent_name: $3 if provided, otherwise use 'reviewer'
review_image_dir: `<absolute path to codebase>/agents/<adw_id>/<agent_name>/review_img/`

## Instructions

### 1. Understand Context
- Check current git branch using `git branch` to understand context
- Run `git diff origin/main` to see all changes made in current branch. Continue even if there are no changes related to the spec file.
- Find the spec file by looking for specs/*.md files in the diff that match the current branch name
- Read the identified spec file to understand requirements

### 2. Setup
- Read and **Execute** `.claude/commands/prepare_app.md` to prepare the application for the review
- Note: prepare_app.md will automatically detect and use ports from `.ports.env` if running in a worktree environment
- The application URL will be http://localhost:PORT where PORT is from `.ports.env` (FRONTEND_PORT) or default 5173
- Create the review image directory: `mkdir -p <review_image_dir>`

**CRITICAL - App Startup Failure Handling**:
- If the app fails to start (e.g., "Address already in use"), follow the error handling in prepare_app.md
- You get **maximum 2 attempts** to start the app (initial + 1 retry after killing processes)
- If app still fails after 2 attempts: **SKIP screenshot capture entirely** and proceed to step 8
- Do NOT keep retrying, do NOT change ports, do NOT try alternative approaches
- Set a flag: `app_startup_failed = true` to use in later steps

### 3. Setup Review Authentication

**Skip this step if `app_startup_failed = true`** - proceed directly to step 8.

Setup authenticated user for review that requires login:

- Read and Execute `.claude/commands/setup_test_auth.md` with the `adw_id`
- Capture the returned auth data (`access_token`, `refresh_token`, etc.)
- You will use these tokens in the capture definition JSON

### 4. Generate Screenshot Capture Definition (if UI validation applicable)

**Skip this step if `app_startup_failed = true`** - proceed directly to step 8.

Based on the spec requirements and git diff, generate a JSON file defining what screenshots to capture.

**Create file**: `<review_image_dir>/capture_definition.json`

**JSON Schema**:
```json
{
  "application_url": "http://localhost:5173",
  "auth": {
    "access_token": "<from step 3>",
    "refresh_token": "<from step 3>"
  },
  "captures": [
    {
      "name": "01_feature_overview.png",
      "description": "Main feature view showing the new functionality",
      "url": "/dashboard",
      "wait_for": "[data-sidebar='sidebar']",
      "actions": [],
      "full_page": false
    },
    {
      "name": "02_feature_detail.png",
      "description": "Detailed view of the specific feature",
      "url": "/feature-page",
      "wait_for": ".feature-element",
      "actions": [
        {"action": "click", "selector": ".expand-button"},
        {"action": "wait", "timeout": 500}
      ]
    }
  ]
}
```

**Available Actions** (optional, use sparingly):
| Action | Fields | Description |
|--------|--------|-------------|
| click | selector | Click an element |
| fill | selector, text | Enter text in input |
| hover | selector | Hover over element |
| wait | timeout (ms) | Simple delay |
| scroll | selector (optional) | Scroll element into view or to bottom |

**Capture Guidelines**:
- Generate 2-5 captures maximum (focus on critical paths)
- Use direct URL navigation (more reliable than clicking through UI)
- Wait for key elements to ensure page is loaded
- Focus on:
  1. **Main feature view** - The primary new functionality
  2. **Key interactions** - Important user flows
  3. **Edge cases** - If spec mentions specific scenarios
  4. **Before/after states** - If the feature involves state changes

### CRITICAL: Selector Strategy

**You MUST verify selectors exist before using them.** Wrong selectors cause capture failures.

**Step 1: Read the actual component source files** to find real selectors:
```bash
# Find the component file for the page you're testing
cat app/frontend/src/pages/DashboardPage.tsx | head -200
```

**Step 2: Use this selector priority order** (most reliable first):

| Priority | Selector Type | Example | When to Use |
|----------|--------------|---------|-------------|
| 1 | data-testid | `[data-testid='submit-btn']` | Best - explicit test hooks |
| 2 | data-* attributes | `[data-sidebar='menu']` | Good - semantic attributes |
| 3 | name attribute | `input[name='firstName']` | Forms - react-hook-form uses name |
| 4 | Semantic HTML | `main`, `nav`, `table` | Layout elements |
| 5 | CSS classes | `.card-title` | Last resort - classes can change |

**Common patterns in this codebase**:
- Sidebar uses data attributes: `[data-sidebar='sidebar']`, `[data-sidebar='menu']`
- Forms use `name` attribute: `input[name='firstName']`
- Tables are semantic: `table`, `thead`, `tbody`

### 5. Execute Screenshot Capture

**Skip this step if `app_startup_failed = true`** - proceed directly to step 8.

Run the direct Playwright runner:

```bash
REVIEW_HEADLESS=false uv run adws/review_screenshot_runner.py \
  "<review_image_dir>/capture_definition.json" \
  --screenshot-dir "<review_image_dir>"
```

**Timeout**: Use a 120-second timeout. If it times out, note it in issues.

**Environment Variables**:
- `REVIEW_HEADLESS=false` - Show browser window (for debugging)
- `REVIEW_HEADLESS=true` - Headless mode (faster, for CI)

**Screenshot Capture Failure Handling**:
- If the screenshot runner fails, **do NOT retry more than once**
- If it fails twice, proceed to step 8 with whatever screenshots were captured (could be none)
- Add an issue noting "Screenshot capture failed: <reason>"

### 6. Parse Results and Review

**Skip this step if `app_startup_failed = true`** - proceed directly to step 8.

The runner outputs JSON with:
- `success`: Whether all captures succeeded
- `screenshots`: List of captured screenshot paths
- `issues`: Any problems encountered during capture

**Review the screenshots**:
- Read each screenshot file to visually inspect the implementation
- Compare what you see against the spec requirements
- Note any discrepancies

### 7. Cleanup Review Data

**Skip this step if `app_startup_failed = true`** - no cleanup needed if auth was never set up.

After review completes:

- Read and Execute `.claude/commands/teardown_test_auth.md` with the `adw_id`

**IMPORTANT**: Always run cleanup if auth was set up, even if review encounters errors.

### 8. Pattern Compliance Validation

After reviewing functionality, validate the implementation against documented patterns:

1. **Read `.claude/commands/conditional_context.md`** to identify which patterns apply based on files changed
2. **Check critical patterns** (report violations as `blocker`):
   - **Multi-tenancy**: If CRUD operations were added/modified, verify they filter by `organization_id`
   - **i18n**: If frontend UI text was added, verify strings use `t()` function (not hardcoded) with keys present in ALL locale files under `app/frontend/src/locales/`
   - **Responsive**: If UI was added/modified, verify it renders correctly on BOTH mobile (390x844) and desktop (1440x900) - no desktop-only layouts
   - **Soft deletes**: If delete operations exist, verify they use `deleted_time` (not hard deletes)
   - **Async patterns**: If I/O operations exist, verify they use `async/await`
3. **Check recommended patterns** (report violations as `tech_debt`):
   - Auth dependencies on protected endpoints
   - Type hints on function signatures
   - Consistent naming conventions

**Pattern Violation Format** (add to `review_issues`):
```json
{
  "review_issue_number": N,
  "screenshot_path": "",
  "issue_description": "Pattern violation: [pattern name] - [specific issue]",
  "issue_resolution": "[How to fix]",
  "issue_severity": "blocker" or "tech_debt"
}
```

### 9. Issue Severity Guidelines

Think hard about the impact of the issue on the feature and the user:

- `skippable` - Non-blocker, still a minor problem
- `tech_debt` - Non-blocker, creates technical debt for future
- `blocker` - Must be fixed before release, harms user experience or breaks functionality

### 10. Report

Return ONLY the JSON output as specified in the `Output Structure` section below.

- Ultra think as you work through the review process
- Focus on critical functionality paths and user experience
- Don't report issues if they are not critical to the feature
- `success` should be `true` if there are NO BLOCKING issues
- `success` should be `false` ONLY if there are BLOCKING issues
- `screenshots` should ALWAYS contain paths to screenshots, regardless of success status

**If `app_startup_failed = true`**:
- Review is still valid based on git diff analysis alone
- Add a `tech_debt` issue: "App startup failed - screenshots could not be captured. Review based on code analysis only."
- `success` can still be `true` if no code issues were found
- `screenshots` will be empty array `[]`

### Output Structure

```json
{
    "success": "boolean - true if there are NO BLOCKING issues (can have skippable/tech_debt issues), false if there are BLOCKING issues",
    "review_summary": "string - 2-4 sentences describing what was built and whether it matches the spec. Written as if reporting during a standup meeting. Example: 'The natural language query feature has been implemented with drag-and-drop file upload and interactive table display. The implementation matches the spec requirements for SQL injection protection and supports both CSV and JSON formats. Minor UI improvements could be made but all core functionality is working as specified.'",
    "review_issues": [
        {
            "review_issue_number": "number - the issue number based on the index of this issue",
            "screenshot_path": "string - /absolute/path/to/screenshot_that_shows_review_issue.png",
            "issue_description": "string - description of the issue",
            "issue_resolution": "string - description of the resolution",
            "issue_severity": "string - severity of the issue between 'skippable', 'tech_debt', 'blocker'"
        }
    ],
    "screenshots": [
        "string - /absolute/path/to/screenshot_showcasing_functionality.png"
    ]
}
```

## Performance Notes

This skill is ~10x faster than the MCP-based approach because:
1. Claude generates capture definitions ONCE (not per-action decisions)
2. Playwright runs at native speed (no round-trip per action)
3. No Claude "thinking" time between browser actions

Expected execution time:
- Capture definition generation: ~15-20 seconds
- Screenshot capture execution: ~10-15 seconds (for 2-5 screenshots)
- Total: ~30-45 seconds (vs 2-4 minutes with MCP)
