# Teardown Test Authentication

Shared helper to cleanup test authentication data after Playwright-based tests complete.

Hard-deletes all data associated with the smoke test organization (not soft delete).

## Variables

adw_id: $ARGUMENT (required - same identifier used in setup_test_auth)

## Instructions

1. **Run the smoke test teardown:**
   ```bash
   cd app/backend && python scripts/teardown_smoke_test.py --adw-id <adw_id>
   ```

2. **Verify cleanup succeeded** by checking the JSON output

## Output Format

```json
{
  "success": true,
  "deleted_org_slug": "smoke-test-{adw_id}",
  "tables_cleaned": ["user", "organization", ...]
}
```

## Important

- **Always run cleanup** even if tests fail - wrap test execution in try/finally logic
- This performs **hard deletes** (not soft deletes) to fully remove test data
- Safe for parallel ADWs - each has unique org slug (`smoke-test-{adw_id}`)
- If org doesn't exist (already cleaned or never created), returns success with empty tables_cleaned
