# API Versioning

**ADW ID:** 20260109234325-fe63cdc2 | **Date:** 2026-01-10

Implements API versioning with `/api/v1/` prefix pattern and versioned router architecture for multi-version coexistence and backward compatibility.

## Architecture

**Files Modified:**
- `app/backend/src/api/v1/__init__.py` (NEW): Aggregates 14 routers (auth, user, users, organization, role, user_role, user_otp, audit_log, metrics, file, admin, notification, sso, organization_sso_settings) into v1_router
- `app/backend/main.py`: Includes v1_router with `/api/v1` prefix
- `app/frontend/src/store/api.ts`: RTK Query baseUrl from `/api` → `/api/v1`
- `app/backend/tests/unit_tests/test_api_v1_router.py` (NEW): Validates router structure
- 17 API test files: Updated to `/api/v1/` paths

**Key Implementation:**
- APIRouter composition pattern—no individual router modifications needed
- Health endpoints (`/health`, `/health/detailed`) remain root-level (infrastructure)
- Single RTK Query config change ensures all frontend calls use v1 prefix

## Usage

**Backend:**
- All endpoints at `/api/v1/*` (e.g., `POST /api/v1/auth/login`, `GET /api/v1/users/me`)
- Register new routers in `app/backend/src/api/v1/__init__.py`
- API docs at `/docs` reflect versioned routes

**Frontend:**
- RTK Query baseUrl: `http://localhost:8000/api/v1`
- Override with `VITE_API_URL` environment variable (must include `/api/v1` suffix)

**Testing:**
```bash
# All backend tests
cd app/backend && make test

# Router validation
cd app/backend && uv run pytest tests/unit_tests/test_api_v1_router.py -v

# All API tests
cd app/backend && uv run pytest tests/api_tests/ -v
```

## Design Decisions

- **URL-based versioning** (`/api/v1/`): Clearer than header-based for client compatibility
- **Router organization**: `v1/` subdirectory within `src/api/` for version-specific code
- **Health endpoints unversioned**: Infrastructure endpoints used by monitoring systems
- **Clean migration**: Removed legacy `/api` routes to avoid maintenance burden

## Future Scaling

- **v2+**: Create `src/api/v{n}/__init__.py`, include modified routers, mount with prefix `/api/v{n}` in main.py
- **Version coexistence**: Multiple versions run simultaneously for gradual client migration
- **Deprecation**: Add response warnings, set sunset dates before removal
