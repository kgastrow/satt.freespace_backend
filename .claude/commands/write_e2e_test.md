# Write E2E Test

Generate a comprehensive TypeScript Playwright test (`.spec.ts`) that exercises ALL functionality for a specific module in a project. Works with any manifest source: greenfield decomposition, discovered features, or existing spec files.

## Variables

manifest_path: $1
target_audience: $2
spec_output_path: $3
test_output_path: $4
adw_id: $5
module_id: $6
prior_gate_feedback: $7  (always present; literal `-` means no feedback / first attempt)

## CRITICAL CONSTRAINTS

- You are a **test author**. Your job is to write comprehensive E2E test files.
- **DO NOT** run tests. The caller handles execution.
- **DO NOT** modify application source code.
- **DO NOT** install packages.
- The ONLY tools you should use are: Read, Glob, Grep, Write, Bash (for syntax validation only)

## Quality Gate (enforced by the orchestrator after you write the file)

The caller runs an automated quality gate against your generated `.spec.ts` BEFORE execution. A failure rejects your file and re-invokes you with `prior_gate_feedback` set to the diagnostic. Plan for these checks:

1. **TypeScript compiles** — `tsc --noEmit` must pass on the generated file.
2. **Playwright lists** — `playwright test <file> --list` must discover at least one test.
3. **Selectors exist** — every static `getByTestId('foo')` / `data-testid="foo"` MUST be grep-able in `app/frontend/src/`. **Verify each testid via Grep before saving.** Prefer `getByRole` / `getByText` / `getByLabel` when a testid isn't in source.
4. **Idempotent test data** — any test that creates resources MUST contain `Date.now()`, `Math.random()`, `crypto.randomUUID()`, or interpolate `adw_id` / `E2E_ADW_ID`. Hard-coded resource names that collide on re-run are rejected.

If `prior_gate_feedback` is anything other than the literal sentinel `-`, **read it first** and fix every listed issue before regenerating. A value of `-` means this is the first attempt and there is no feedback.

## Reference Implementation

Before writing any code, read these files to understand the required patterns and infrastructure:

1. **`app/frontend/tests/e2e/fixtures/auth.ts`** — Auth fixture that provides `{ auth }` with `accessToken`, `orgSlug`, etc. Tests import `{ test, expect }` from this fixture.
2. **`app/frontend/tests/e2e/fixtures/helpers.ts`** — Shared helpers: `navigateTo`, `selectOption`, `openDialog`, `submitDialog`, `apiCall`, `expectToast`, `clickTableRow`, etc. Use these extensively.
3. **`app/frontend/tests/e2e/08-admin-navigation.spec.ts`** — Reference admin test showing patterns, imports, and structure.
4. **`app/frontend/tests/e2e/02-sidebar-navigation.spec.ts`** — Reference end-user test.
5. **`app/frontend/playwright.config.ts`** — Config showing project structure. Tests run in the `chromium` project with `storageState` auth.

## Instructions

### 1. Read the Manifest and Find the Module

Read the manifest JSON from `{manifest_path}`. Find the module whose `id` matches `{module_id}`. The manifest may contain these fields per module:

- `id`, `name`, `description` — always present
- `target_audience` — "end_user", "admin", or "platform_admin"
- `acceptance_criteria` — list of testable criteria (may be empty)
- `user_stories` — user story descriptions (may be empty)
- `spec_path` — path to an existing `.md` test spec with detailed steps (may be empty)
- `routes` — frontend route paths for this feature (may be empty)
- `api_endpoints` — backend API endpoints (may be empty)
- `component_paths` — page component file paths (may be empty)

### 2. Determine Test Guidance

Follow the first matching path:

**Path A — Module has `spec_path`:**
Read the referenced `.md` spec file. It contains detailed test steps, selectors, expected results, and API endpoints. Use this as your primary test design guide. Still research the actual source code to verify selectors match the current implementation.

**Path B — Module has `routes` and `api_endpoints` but no `spec_path`:**
Research the actual code for each route and endpoint. Read page components to identify forms, tables, dialogs, action buttons. Derive test cases from what the code actually does.

**Path C — Module has `acceptance_criteria` (decomposition-style):**
Use the acceptance criteria and user stories to guide test design. Research the implemented code to find real selectors and verify the features exist.

In all paths, you MUST research the actual source code to extract real selectors. Never guess button text, form labels, or dialog titles.

### 3. Research the Implemented Code

For EACH module, research the actual implementation to extract REAL selectors:

**Frontend pages:** `app/frontend/src/pages/**/*.tsx` and `app/frontend/src/features/**/*.tsx`
**Navigation config:** `app/frontend/src/config/navigation.ts`, `adminNav.ts`, `platformAdminNav.ts`
**API routes:** `app/backend/src/api/` for endpoint paths
**i18n translations:** `app/frontend/src/locales/en/common.json` for actual button/label text

**CRITICAL**: Only use selectors verified from source code. For shadcn/Radix Select components, use the `selectOption` helper from `fixtures/helpers.ts`.

### 4. Design the User Journey

**Module-to-test mapping:**
- Write **1-3 `test()` blocks per module**, each covering a distinct user journey (e.g., create, view/list, edit, delete).
- Each acceptance criterion should be covered by at least one test assertion. If a module has 5 acceptance criteria, spread them across its test blocks.
- Aim for **completeness over brevity** — every page, form, and CRUD action should have a corresponding test.

**CRITICAL — Test data idempotency:**
Tests may run multiple times (retry loop). All created resources MUST use unique names:
```typescript
const uniqueName = `Test Item ${Date.now()}`;
```

**CRITICAL — API verification:**
Every test performing a CRUD operation MUST verify via `apiCall()` from `fixtures/helpers.ts`:

```typescript
test('create item', async ({ page, auth }) => {
  // ... UI interaction ...
  const data = await apiCall(auth.accessToken, 'GET', '/items') as { items: Item[] };
  expect(data.items.some(i => i.name === 'Expected')).toBeTruthy();
});
```

### 5. Write the .md Spec File

Write a markdown test spec to `{spec_output_path}` documenting the test plan. This is a secondary documentation artifact.

### 6. Write the TypeScript Playwright Test File

Write the test to `{test_output_path}`. This is the **primary artifact**.

**Required structure:**

```typescript
import { test, expect } from './fixtures/auth';
import {
  navigateTo, selectOption, apiCall, expectToast,
  openDialog, submitDialog, confirmDialog, fillByLabel,
  clickTableRow, waitForTableLoad, expectTableHasRows,
  waitForNavigation, getTableRowCount,
} from './fixtures/helpers';

/**
 * E2E Tests: {module_name}
 * ADW: {adw_id}
 */

test.describe.serial('{Module Name} — E2E', () => {
  let resourceId: string | undefined;

  test('page loads', async ({ page }) => {
    await navigateTo(page, '/path');
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('create resource', async ({ page, auth }) => {
    // ... verified selectors ...
    const data = await apiCall(auth.accessToken, 'GET', '/resource') as { items: Item[] };
    expect(data.items.length).toBeGreaterThanOrEqual(1);
    resourceId = data.items[0].id;
  });

  test('dependent test', async ({ page }) => {
    test.skip(!resourceId, 'Requires create to run first');
    // ...
  });
});
```

**Key rules:**
- **Import from `./fixtures/auth`** — NOT from `@playwright/test`
- **Use `test.describe.serial()`** — Tests share state and must run in order
- **Use `navigateTo()`** — From helpers, handles `networkidle` wait
- **Use `selectOption()`** — For shadcn Select/Combobox components
- **Use `apiCall()`** — For backend verification
- **API verification is mandatory** for any create/update/delete operation
- **Use `getByRole()` and `getByText()`** — Playwright best practices
- **For dialogs** — Use `[role="dialog"]` or `[role="alertdialog"]`
- **No `(?i)` inline regex** — Use `/pattern/i` JavaScript regex flags

### 7. Validate Output

After writing both files:
1. Verify the TypeScript file has valid syntax by running from `app/frontend/` (Bash tool):
   ```bash
   cd app/frontend && npx tsc --noEmit 2>&1 | head -30 || echo "TypeScript check done"
   ```
   Review any errors related to your generated file and fix them before finishing.

## Report

Return a JSON object (no markdown, raw JSON only):

```json
{
  "spec_path": "{spec_output_path}",
  "test_path": "{test_output_path}",
  "module_id": "{module_id}",
  "modules_covered": ["module-id"],
  "test_count": 5,
  "success": true
}
```
