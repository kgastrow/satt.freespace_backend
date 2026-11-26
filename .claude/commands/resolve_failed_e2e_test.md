# Resolve Failed E2E Test

Fix a specific failing E2E test using the provided failure details.

## Instructions

1. **Analyze the E2E Test Failure**
   - Review the JSON data in the `Test Failure Input`, paying attention to:
     - `test_name`: The name of the failing test
     - `test_path`: The path to the test file (you will need this for re-execution)
     - `error`: The specific error that occurred
     - `screenshots`: Any captured screenshots showing the failure state
   - Understand what the test is trying to validate from a user interaction perspective

2. **Understand Test Execution**
   - Read the test file specified in the `test_path` field from the JSON
   - Note the test steps, user story, and success criteria
   - **Determine which E2E system this test belongs to** (this decides how you re-run it):
     - **Playwright `.spec.ts` file** (path under `app/frontend/tests/e2e/`, ends in `.spec.ts`): this is the **standard** greenfield E2E format going forward. Re-run it directly with Playwright.
     - **Legacy markdown spec** (path under `.claude/commands/e2e/`, ends in `.md`): only in this case use the JSON-runner flow. Read `.claude/commands/test_e2e.md` to understand how those markdown specs are converted to a test definition and executed.

3. **Reproduce the Failure**
   - IMPORTANT: Use the `test_path` from the JSON to re-execute the specific E2E test
   - **If the failing test is a Playwright `.spec.ts` file**, re-run only that spec:
     ```bash
     cd app/frontend && npx playwright test <test_path>
     ```
     - If `.ports.env` exists (worktree) or an `application_url` was provided, honor it (e.g. set the base URL / `PLAYWRIGHT_BASE_URL` from `FRONTEND_PORT`) so the test targets the running app.
   - **If the failing test is a legacy markdown spec** in `.claude/commands/e2e/`, follow the execution pattern from `.claude/commands/test_e2e.md` instead.
   - Observe the browser behavior and confirm you can reproduce the exact failure
   - Compare the error you see with the error reported in the JSON

4. **Fix the Issue**
   - Based on your reproduction, identify the root cause
   - Make minimal, targeted changes to resolve only this E2E test failure
   - Consider common E2E issues:
     - Element selector changes
     - Timing issues (elements not ready)
     - UI layout changes
     - Application logic modifications
   - Ensure the fix aligns with the user story and test purpose

5. **Validate the Fix**
   - Re-run the same E2E test using the `test_path` to confirm it now passes:
     - Playwright `.spec.ts`: `cd app/frontend && npx playwright test <test_path>`
     - Legacy markdown spec: re-run via the `.claude/commands/test_e2e.md` flow
   - IMPORTANT: The test must complete successfully before considering it resolved
   - Do NOT run other tests or the full test suite
   - Focus only on fixing this specific E2E test

## Test Failure Input

$ARGUMENTS

## Report

Provide a concise summary of:
- Root cause identified (e.g., missing element, timing issue, incorrect selector)
- Specific fix applied
- Confirmation that the E2E test now passes after your fix