# Resolve Failed Smoke Test

Fix a specific failing smoke test using the provided failure details and screenshots.

## Instructions

1. **Analyze the Smoke Test Failure**
   - Review the test name, description, and error message from the `Smoke Test Failure Input`
   - Examine any screenshots captured during the test
   - Understand what UI behavior the test was trying to validate
   - Identify the root cause (missing element, wrong selector, timing issue, actual bug)

2. **Context Discovery**
   - Check recent changes: `git diff origin/main --stat --name-only`
   - Focus on frontend files that could impact the failing test
   - If a relevant spec exists in `specs/*.md`, read it to understand requirements
   - Review the component/page being tested

3. **Determine Fix Type**
   The failure could be due to:
   - **Actual Bug**: The feature doesn't work as expected → Fix the feature code
   - **Test Issue**: Test assumptions are wrong (selectors, timing) → This is less common for smoke tests since they're dynamically generated
   - **Missing Implementation**: Feature not fully implemented → Complete the implementation
   - **Selector Issue with Component Libraries**: Wrong selector used for shadcn/ui or Radix components → Add `data-testid` to the component

   **Common Radix UI Selector Failures**:
   If the error mentions `button[role='combobox']` or similar role-based selectors timing out:
   - Radix UI's `DropdownMenuTrigger` with `asChild` overrides role attributes
   - Fix: Add `data-testid` attribute to the trigger button in the source code
   - Example: `<Button data-testid="user-actions-menu">...</Button>`
   - The test will use `[data-testid='user-actions-menu']` instead of `button[role='combobox']`

4. **Fix the Issue**
   - Make minimal, targeted changes to resolve only this test failure
   - Ensure the fix aligns with the spec requirements
   - Do not modify unrelated code

5. **Validate the Fix**
   - If possible, manually verify the fix addresses the failure
   - The smoke test will be re-run automatically after this resolution attempt

## Smoke Test Failure Input

$ARGUMENTS

## Report

Provide a concise summary of:
- Root cause identified (UI bug, missing element, timing issue, etc.)
- Specific fix applied
- Files modified
- Confidence level that the fix resolves the issue
