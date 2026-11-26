# E2E Test Runner

Execute end-to-end (E2E) tests using Playwright browser automation.

**PERFORMANCE**: This skill uses direct Playwright execution (not MCP), making it ~10x faster than interactive browser control.

## Variables

adw_id: $1 if provided, otherwise generate using format YYYYMMDDHHMMSS-<8-char-uuid>
agent_name: $2 if provided, otherwise use 'e2e_test'
e2e_test_file: $3 (path to test spec file like .claude/commands/e2e/test_login_success.md)
application_url: $4 if provided, otherwise determine from port configuration:
  - If `.ports.env` exists, source it and use http://localhost:${FRONTEND_PORT}
  - Otherwise use default http://localhost:5173

## Instructions

### 1. Determine Application URL
- If `application_url` was not provided, check for `.ports.env`:
  - If it exists, source it and use http://localhost:${FRONTEND_PORT}
  - Otherwise use default http://localhost:5173

### 2. Read Test Specification
- Read the `e2e_test_file` to understand the test requirements
- Extract the `User Story`, `Test Steps`, and `Success Criteria`
- Note the test name from the file header

### 3. Prepare Application
- Read and Execute `.claude/commands/prepare_app.md` to prepare the application for the test

### 4. Setup Test Authentication
- Read and Execute `.claude/commands/setup_test_auth.md` with the `adw_id`
- Capture the returned auth data (`access_token`, `refresh_token`, etc.)
- You will use these tokens in the test definition JSON

### 5. Create Screenshot Directory
- Create the screenshot directory structure:
  ```bash
  mkdir -p <absolute path to codebase>/agents/<adw_id>/<agent_name>/img/<test_name>/
  ```

### 6. Generate Test Definition JSON

Based on the test spec file, generate a JSON test definition that can be executed directly.

**Create file**: `<screenshot_dir>/test_definition.json`

**JSON Schema**:
```json
{
  "application_url": "http://localhost:5173",
  "auth": {
    "access_token": "<from step 4>",
    "refresh_token": "<from step 4>"
  },
  "test_name": "Login Success",
  "test_description": "Test successful login flow",
  "steps": [
    {"action": "navigate", "url": "/"},
    {"action": "screenshot", "name": "01_initial.png"},
    {"action": "assertTitle", "text": "Expected Page Title"},
    {"action": "assertVisible", "selector": "[data-testid='query-input']"},
    {"action": "fill", "selector": "[data-testid='query-input']", "text": "user query"},
    {"action": "screenshot", "name": "02_query_entered.png"},
    {"action": "click", "selector": "[data-testid='submit-btn']"},
    {"action": "waitForSelector", "selector": ".results"},
    {"action": "assertText", "selector": ".results", "text": "expected content"},
    {"action": "screenshot", "name": "03_results.png"}
  ]
}
```

**Available Actions**:
| Action | Required Fields | Description |
|--------|----------------|-------------|
| navigate | url | Go to URL (can be relative like "/dashboard") |
| click | selector | Click an element |
| fill | selector, text | Enter text in input field |
| clear | selector | Clear input field |
| press | key (optional: selector) | Press keyboard key (e.g., "Enter") |
| hover | selector | Hover over element |
| scroll | selector (optional) | Scroll element into view or to bottom |
| check | selector | Check a checkbox |
| uncheck | selector | Uncheck a checkbox |
| selectOption | selector, text | Select dropdown option by value |
| wait | timeout | Simple delay in ms |
| waitForSelector | selector | Wait for element to appear |
| waitForUrl | url | Wait for URL to match pattern |
| screenshot | name | Take screenshot with given filename |
| assertVisible | selector | Assert element is visible (fails if not) |
| assertHidden | selector | Assert element is hidden |
| assertText | selector, text | Assert element contains text |
| assertTitle | text | Assert page title contains text |
| assertUrl | text | Assert URL contains pattern |
| assertCount | selector, text | Assert number of matching elements (text = count) |

**Converting Test Specs to Steps**:

When you see test spec instructions like:
- "Navigate to X" → `{"action": "navigate", "url": "X"}`
- "Take a screenshot" → `{"action": "screenshot", "name": "0N_description.png"}`
- "**Verify** element is visible" → `{"action": "assertVisible", "selector": "..."}`
- "**Verify** text contains X" → `{"action": "assertText", "selector": "...", "text": "X"}`
- "Enter/Type X in field" → `{"action": "fill", "selector": "...", "text": "X"}`
- "Click button/link" → `{"action": "click", "selector": "..."}`
- "Wait for results" → `{"action": "waitForSelector", "selector": "..."}`

### CRITICAL: Selector Strategy

**You MUST verify selectors exist before using them.** Wrong selectors cause test failures.

**Step 1: Read the actual component source files** to find real selectors:
```bash
cat app/frontend/src/pages/TargetPage.tsx | head -200
```

**Step 2: Use this selector priority order** (most reliable first):

| Priority | Selector Type | Example | When to Use |
|----------|--------------|---------|-------------|
| 1 | data-testid | `[data-testid='submit-btn']` | Best - explicit test hooks |
| 2 | data-* attributes | `[data-sidebar='menu']` | Good - semantic attributes |
| 3 | name attribute | `input[name='firstName']` | Forms - react-hook-form uses name |
| 4 | Semantic HTML | `main`, `nav`, `table`, `button` | Layout elements |
| 5 | Role attributes | `[role='dialog']` | Accessibility attributes |
| 6 | Text content | `text=Submit` | Buttons/links by visible text |
| 7 | CSS classes | `.card-title` | Last resort - classes can change |

**Common patterns in this codebase**:
- Sidebar uses data attributes: `[data-sidebar='sidebar']`, `[data-sidebar='menu']`
- Forms use `name` attribute: `input[name='firstName']`
- Tables are semantic: `table`, `thead`, `tbody`
- Buttons often have type: `button[type='submit']`

### 7. Execute E2E Test

Run the direct Playwright runner:

```bash
E2E_HEADLESS=false uv run adws/e2e_test_runner.py \
  "<screenshot_dir>/test_definition.json" \
  --screenshot-dir "<screenshot_dir>"
```

**Timeout**: Use a 180-second timeout. E2E tests may take longer than smoke tests.

**Environment Variables**:
- `E2E_HEADLESS=false` - Show browser window (for debugging)
- `E2E_HEADLESS=true` - Headless mode (faster, for CI)

### 8. Parse Results

The runner outputs JSON with:
- `test_name`: Name of the test
- `status`: "passed" or "failed"
- `screenshots`: List of captured screenshot paths
- `steps_passed`: Number of steps that passed
- `steps_failed`: Number of steps that failed
- `error`: First error message if failed
- `step_results`: Detailed results for each step

### 9. Cleanup

After test execution completes (regardless of pass/fail):

- Read and Execute `.claude/commands/teardown_test_auth.md` with the `adw_id`

**IMPORTANT**: Always run cleanup, even if tests fail.

### 10. Report

Return the test result in the Output Format below.

### Output Format

```json
{
  "test_name": "Test Name Here",
  "status": "passed|failed",
  "test_description": "What the test verifies",
  "screenshots": [
    "/absolute/path/to/01_initial.png",
    "/absolute/path/to/02_action.png",
    "/absolute/path/to/03_result.png"
  ],
  "steps_passed": 10,
  "steps_failed": 0,
  "error": null,
  "step_results": [
    {"step": 1, "action": "navigate", "status": "passed"},
    {"step": 2, "action": "assertVisible", "status": "passed"}
  ]
}
```

## Performance Notes

This skill is ~10x faster than the MCP-based approach because:
1. Claude generates test definition ONCE (not per-action decisions)
2. Playwright runs at native speed (no round-trip per action)
3. No Claude "thinking" time between browser actions

Expected execution time:
- Test definition generation: ~15-25 seconds
- Test execution: ~15-30 seconds (depending on complexity)
- Total: ~30-60 seconds (vs 3-5 minutes with MCP)
