# API Key Authentication

**ADW ID:** 20260110234217-dad997dc | **Date:** 2026-01-11 | **Spec:** specs/multi-phase/issue-107-adw-20260110234217-dad997dc-multi-phase.md

API key authentication system for external integrations with programmatic authentication, tenant isolation, and fine-grained permission control.

## Files Modified

**Database:**
- `app/backend/alembic/versions/f447ed1bbbfd_add_api_key_tables.py` - Migration for api_keys and api_key_permissions tables
- `app/backend/src/models/api_key.py` - ApiKey model (key_hash, prefix, expires_at, last_used_at, soft delete)
- `app/backend/src/models/api_key_permission.py` - Junction table (API key ↔ Permission via permission_id, same pattern as RolePermission)
- `app/backend/src/models/organization.py` - Added api_keys relationship

**Business Logic:**
- `app/backend/src/crud/api_key.py` - Async CRUD: secure generation (secrets.token_urlsafe), bcrypt hashing, validation, permissions
- `app/backend/src/api/api_key.py` - REST endpoints (create, list, get, update, delete, assign permissions)
- `app/backend/src/api/deps.py` - Auth dependencies: `get_current_api_key`, `get_current_user_or_api_key` (dual-auth)
- `app/backend/src/core/security.py` - Security utilities
- `app/backend/src/serialisers/api_key.py` - Pydantic models

**Tests:**
- `app/backend/tests/crud/test_api_key_crud.py` - CRUD & tenant isolation tests
- `app/backend/tests/api/test_api_key_endpoints.py` - Endpoint integration tests
- `app/backend/tests/api/test_api_key_auth.py` - Authentication flow tests

**Frontend:**
- `app/frontend/src/features/apiKeys/apiKeysApi.ts` - RTK Query endpoints
- `app/frontend/src/pages/settings/ApiKeysPage.tsx` - UI (create, edit, revoke, permissions)
- `app/frontend/src/routes/settingsRoutes.tsx` - Settings route
- `app/frontend/src/components/AppSidebar.tsx` - Menu item
- `app/frontend/src/locales/en/settings.json` - English translations
- `app/frontend/src/locales/de/settings.json` - German translations

## Key Technical Details

**Security & Storage:**
- Generation: `secrets.token_urlsafe(32)` for cryptographic randomness
- Storage: Only bcrypt hash and 8-char prefix persisted; full key shown once at creation
- Validation: Hash comparison + expiration check + permission verification
- Revocation: Soft delete (deleted_time flag; 401 on access)

**Authentication:**
- Header: `X-API-Key: <key>`
- Dual-auth: JWT or API key via `get_current_user_or_api_key` dependency
- Last-used tracking: Updated on successful auth for auditing

**Multi-tenancy:**
- All queries strictly filter by organization_id
- No cross-tenant access possible

**Permissions:**
Required in seed data: `api_keys:read`, `api_keys:write`, `api_keys:delete` (underscore format; pattern: `^[a-z_]+:[a-z_]+$`)

## Usage

**Create (Frontend):** Settings > API Keys > Create > Name + Expiration + Permissions > Copy key immediately (never shown again)

**Use (External):**
```bash
curl -H "X-API-Key: your-api-key-here" https://api.example.com/api/endpoint
```

**Manage:** View keys (prefix, expiration, last-used, permissions) | Edit name/expiration | Revoke (soft delete) | Assign permissions

## Configuration & Testing

**Backend:** Automatic after migrations; no env vars needed.

**Tests:**
```bash
cd app/backend && make test              # All tests
npm run test                              # Frontend (from app/frontend)
curl -H "X-API-Key: <key>" http://localhost:8000/api/v1/users/me  # Manual E2E
```

**Test files:** `tests/crud/test_api_key_crud.py`, `tests/api/test_api_key_endpoints.py`, `tests/api/test_api_key_auth.py`

## Notes

- Full key never stored; prefix (8 chars) identifies key in UI/logs
- Soft deletes maintain audit trail
- Future: rate limiting per key, webhook signing
- Last-used timestamp enables security auditing
