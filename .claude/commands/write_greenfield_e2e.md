# Write Greenfield E2E Test

Generate a comprehensive TypeScript Playwright test (`.spec.ts`) that exercises ALL functionality implemented for a specific module (or all modules for an audience) in a greenfield project. The test must follow the exact same patterns as the existing E2E tests in `app/frontend/tests/e2e/`.

## Variables

decomposition_path: $1
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

The caller runs an automated quality gate against your generated `.spec.ts` BEFORE handing it to the executor. A failure rejects your file and re-invokes you with `prior_gate_feedback` set to the diagnostic. Plan for these checks up front:

1. **TypeScript compiles** — `tsc --noEmit` must pass on the generated file. Stick to the imports shown in `fixtures/auth.ts` / `fixtures/helpers.ts`; do not invent helpers.
2. **Playwright lists** — `playwright test <file> --list` must discover at least one test. Bad `describe`/`test` nesting fails this check.
3. **Selectors exist in source** — every static `getByTestId('foo')` or `data-testid="foo"` you write MUST be grep-able in `app/frontend/src/`. The gate runs ripgrep/grep against the source tree. **Verify each testid via Grep before saving the file.** If a needed testid is missing, do NOT invent one — fall back to `getByRole`, `getByText`, or `getByLabel`, which the gate skips.
4. **Idempotent test data** — if your test performs any create operation (POST or `.fill('LiteralName')` into a name/title field), the file MUST contain at least one uniqueness primitive: `Date.now()`, `Math.random()`, `crypto.randomUUID()`, or interpolation of `adw_id` / `E2E_ADW_ID`. Hard-coded resource names that collide on re-run are rejected.

If `prior_gate_feedback` is anything other than the literal sentinel `-`, **read it first**. It lists the exact failures from your previous attempt. Address each before regenerating. A value of `-` means this is the first attempt and there is no feedback.

## Reference Implementation

Before writing any code, read these files to understand the required patterns and infrastructure:

1. **`app/frontend/tests/e2e/fixtures/auth.ts`** — Auth fixture that provides `{ auth }` with `accessToken`, `orgSlug`, etc. Tests import `{ test, expect }` from this fixture.
2. **`app/frontend/tests/e2e/fixtures/helpers.ts`** — Shared helpers: `navigateTo`, `selectOption`, `openDialog`, `submitDialog`, `apiCall`, `expectToast`, `clickTableRow`, etc. Use these extensively.
3. **`app/frontend/tests/e2e/08-admin-navigation.spec.ts`** — Reference admin test showing patterns, imports, and structure.
4. **`app/frontend/tests/e2e/02-sidebar-navigation.spec.ts`** — Reference end-user test.
5. **`app/frontend/playwright.config.ts`** — Config showing project structure. Greenfield tests run in the `chromium` project with `storageState` auth (authenticated automatically via `global-setup.ts`).

## Instructions

### 1. Read the Decomposition

Read the decomposition JSON from `{decomposition_path}`. If `{module_id}` is provided (non-empty), find the single module whose `id` matches `{module_id}`. Otherwise, parse all modules where `target_audience` matches `{target_audience}`. Skip `backend_only` modules.

### 2. Research the Implemented Code

For EACH module, research the actual implementation to extract REAL selectors:

**Frontend pages:** `app/frontend/src/pages/**/*.tsx` and `app/frontend/src/features/**/*.tsx`
**Navigation config:** `app/frontend/src/config/navigation.ts`, `adminNav.ts`, `platformAdminNav.ts`
**API routes:** `app/backend/src/api/` for endpoint paths

**CRITICAL**: Only use selectors verified from source code. For shadcn/Radix Select components, use the `selectOption` helper from `fixtures/helpers.ts`.

### 3. Design the User Journey

**Module-to-test mapping:**
- Write **1-3 `test()` blocks per module**, each covering a distinct user journey (e.g., create, view/list, edit, delete).
- Each acceptance criterion from the decomposition should be covered by at least one test assertion. If a module has 5 acceptance criteria, spread them across its test blocks — do NOT collapse them into a single test.
- Group related modules into a logical flow within the serial describe block (e.g., create a resource in module A, then verify it appears in module B's list view).
- Aim for **completeness over brevity** — every page, form, and CRUD action described in the decomposition should have a corresponding test. If a module has a list view, a detail view, and a create form, test all three.

**CRITICAL — Test data idempotency (enforced by the quality gate):**
Tests run repeatedly (retry loop + cap-limited resolve loop). Every created resource MUST use a unique name. Prefer interpolating the ADW id so artifacts can be traced back to a run:
```typescript
const adwId = process.env.E2E_ADW_ID ?? 'local';
const uniqueName = `Test Item ${adwId} ${Date.now()}`;
```
Hard-coded names like "Test Item" collide on re-run and FAIL the gate. The gate scans for at least one of `Date.now()`, `Math.random()`, `crypto.randomUUID()`, or a template that interpolates `adw_id` / `E2E_ADW_ID`. If your file has no creates at all, the check is skipped.

**CRITICAL — API verification:**
Every test performing a CRUD operation MUST verify via `apiCall()` from `fixtures/helpers.ts`. The `auth` fixture provides `auth.accessToken` for API calls.

```typescript
test('create item', async ({ page, auth }) => {
  // ... UI interaction ...
  const data = await apiCall(auth.accessToken, 'GET', '/items') as { items: Item[] };
  expect(data.items.some(i => i.name === 'Expected')).toBeTruthy();
});
```

### 4. Write the .md Spec File

Write a markdown test spec to `{spec_output_path}` documenting the test plan. This is a secondary documentation artifact.

### 5. Write the TypeScript Playwright Test File

Write the test to `{test_output_path}`. This is the **primary artifact** — executed by `npx playwright test` and runnable from VS Code.

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
 * Greenfield E2E Tests: {target_audience}
 * ADW: {adw_id}
 *
 * Exercises: [list all module names]
 */

test.describe.serial('{Audience Label} — Greenfield Features', () => {
  // Shared state for ordered tests
  let resourceId: string | undefined;

  test('page loads', async ({ page }) => {
    await navigateTo(page, '/path');
    await expect(page.locator('h1').first()).toBeVisible();
  });

  test('create resource', async ({ page, auth }) => {
    await navigateTo(page, '/path');
    // ... UI interaction using verified selectors ...

    // API verification
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
- **Import from `./fixtures/auth`** — NOT from `@playwright/test` (unless the test doesn't need auth)
- **Use `test.describe.serial()`** — Tests share state and must run in order
- **Use `navigateTo()`** — From helpers, handles `networkidle` wait
- **Use `selectOption()`** — For shadcn Select/Combobox components
- **Use `apiCall()`** — For backend verification, requires `auth.accessToken`
- **API verification is mandatory** for any create/update/delete operation
- **Use `getByRole()`** and `getByText()`** — Playwright best practices for selector resilience
- **For action menus** — Use `[role="menuitem"]` after clicking the trigger button
- **For dialogs** — Use `[role="dialog"]` or `[role="alertdialog"]`
- **No `(?i)` inline regex** — Use `/pattern/i` JavaScript regex flags directly
- **Number prefix** — Use `30` for admin, `31` for end_user, `32` for platform_admin in filename

### 6. Validate Output

After writing both files:
1. Verify the .md spec exists at `{spec_output_path}`
2. Verify the TypeScript file has valid syntax by running from `app/frontend/` (Bash tool):
   ```bash
   cd app/frontend && npx tsc --noEmit 2>&1 | head -30 || echo "TypeScript check done"
   ```
   This runs the full project type-check so imports resolve correctly. Review any errors related to your generated file and fix them before finishing.

## Report

Return a JSON object (no markdown, raw JSON only):

```json
{
  "spec_path": "{spec_output_path}",
  "test_path": "{test_output_path}",
  "modules_covered": ["module-id-1", "module-id-2"],
  "test_count": 5,
  "success": true
}
```
