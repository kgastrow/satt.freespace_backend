# API Key Permissions and Rate Limits

**ADW ID:** 20260114230718-46446f59 | **Date:** 2026-01-15
**Specification:** specs/multi-phase/issue-137-adw-20260114230718-46446f59-multi-phase.md

## Overview

Granular API key permissions with permission validation (user cannot assign permissions they don't have) and configurable rate limiting via Redis sliding window algorithm. Permissions are immutable after creation; super admins configure rate limits per permission.

## Implementation

### Backend Files

**Models & Database:**
- `app/backend/src/models/api_key_rate_limit.py` - ApiKeyRateLimit model with soft deletes, unique constraint per permission
- `app/backend/alembic/versions/955d43a4542b_add_apikeyratelimit_model.py` - Migration

**CRUD & API:**
- `app/backend/src/crud/api_key_rate_limit.py` - Rate limit CRUD
- `app/backend/src/crud/__init__.py` - Exports
- `app/backend/src/api/api_key_rate_limit.py` - Super admin CRUD endpoints
- `app/backend/src/api/api_key.py` - Permission validation, assignable-permissions endpoint
- `app/backend/src/api/deps.py` - Rate limit enforcement middleware

**Core Logic:**
- `app/backend/src/core/api_key_rate_limit.py` - Redis sorted set sliding window limiter
- `app/backend/src/core/response_codes.py` - Rate limit response codes
- `app/backend/src/serialisers/api_key_rate_limit.py` - Pydantic models
- `app/backend/src/serialisers/api_key.py` - Permissions field
- `app/backend/main.py` - Rate limiter pool initialization

**Tests:**
- `app/backend/tests/unit_tests/test_api_key_permissions_rate_limits.py` - 1022 lines covering permission validation, rate enforcement, tenant isolation

### Frontend Files

- `app/frontend/src/components/permissions/ApiKeyPermissionSelector.tsx` - Permission selector, grouped by resource, read-only mode
- `app/frontend/src/pages/admin/ApiKeyRateLimitsPage.tsx` - Super admin rate limit CRUD UI
- `app/frontend/src/pages/admin/ApiKeysPage.tsx` - Permission selector integration
- `app/frontend/src/features/apiKeys/apiKeysApi.ts` - Assignable-permissions endpoint
- `app/frontend/src/features/apiKeys/rateLimitsApi.ts` - RTK Query rate limit API
- `app/frontend/src/locales/*/settings.json` - i18n: en, de, xh, zu, nso

## Key Design Decisions

**Sliding Window Algorithm:** Redis sorted sets track request timestamps, preventing fixed-window burst edge cases.

**Permission Validation:** Backend ensures API key permissions ⊆ user's permissions. Super admins unrestricted. No POST/DELETE endpoints for modifying permissions post-creation.

**Graceful Degradation:** Redis unavailable → allow requests (fail open).

**Rate Limit Enforcement:** Most restrictive permission applies when key has multiple. Total limit = `requests_per_minute + burst_limit`. Default: 60 req/min + 10 burst.

**Response Headers:** All responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. On 429: `Retry-After` header.

**Scoping:** Rate limits are global (system-wide), not org-scoped, to prevent infrastructure abuse. Permissions persist if user's permissions revoked.

## Configuration

**Environment Variables:**
- `RATE_LIMIT_ENABLED` (default: true)
- `RATE_LIMIT_BYPASS_ADMIN` (default: false)
- `REDIS_URL` - Redis connection for rate tracking

**Cache:** Rate limit configs cached in memory to avoid DB queries on every request.

## Usage

**Create API Keys:** Admin → API Keys → Create → Select permissions (only shows assignable) → Grouped by resource → Read-only after creation.

**Manage Rate Limits (Super Admin):** Admin → API Key Rate Limits → Create/Edit/Delete. Per-permission config: permission code (e.g., `users:read`), req/min, burst. Limit: 429 with Retry-After on exceed.

## Testing

```bash
cd app/backend
make test  # Rate limit CRUD, permission validation, enforcement, tenant isolation, admin checks, Redis failure edge cases
```

**Manual:** Create key as non-admin, verify permissions shown; attempt edit (read-only); configure rate limit as super admin; exceed and verify 429; check Redis `rate_limit:api_key:{api_key_id}` keys.

## Notes

- Rate limits are global system-wide, not per-organization
- Permissions persist even if creating user's permissions revoked
- Sliding window more accurate than fixed windows, requires Redis sorted sets
- Future: per-organization rate limit overrides for enterprise
- Audit logging for all rate limit configuration changes
