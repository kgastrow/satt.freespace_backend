# Setup Test Authentication

Shared helper to setup authenticated test user for Playwright-based tests (smoke tests, E2E tests).

Creates a dedicated smoke test organization and user, then returns JWT tokens for browser injection.

## Variables

adw_id: $ARGUMENT (required - unique identifier for this test run)

## Instructions

1. **Run the smoke test seeder:**
   ```bash
   cd app/backend && python scripts/seed_smoke_test.py --adw-id <adw_id>
   ```

2. **Capture the JSON output** which contains:
   - `user_id` - Test user UUID
   - `organization_id` - Test organization UUID
   - `org_slug` - Organization slug (`smoke-test-{adw_id}`)
   - `email` - Test user email (`smoke-test@example.com`)
   - `access_token` - JWT for API authentication (24h expiry)
   - `refresh_token` - JWT for token refresh (30d expiry)

3. **Return the auth data** for use by the calling command

## Output Format

Return the JSON output from the seed script:

```json
{
  "user_id": "uuid",
  "organization_id": "uuid",
  "org_slug": "smoke-test-{adw_id}",
  "email": "smoke-test@example.com",
  "access_token": "jwt...",
  "refresh_token": "jwt..."
}
```

## Token Injection Instructions

When using these tokens in Playwright sub-agents, include the following in the sub-agent prompt:

```markdown
## Authentication Setup
Before navigating to authenticated pages, inject tokens:
1. Navigate to application URL first (to set origin)
2. Execute JavaScript to set tokens in browser storage:
   ```javascript
   sessionStorage.setItem('access_token', '<access_token>');
   localStorage.setItem('refresh_token', '<refresh_token>');
   ```
3. Reload the page to pick up the auth state
4. Proceed with test steps
```

## Notes

- Each ADW gets a unique organization slug (`smoke-test-{adw_id}`) for isolation
- Idempotent: re-running for same ADW reuses existing org, generates fresh tokens
- Always pair with `teardown_test_auth.md` for cleanup after tests complete
