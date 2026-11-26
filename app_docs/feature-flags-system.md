# Feature Flags System

**ADW ID:** 20260115152330-a2bc90c7 | **Date:** 2026-01-15 | **Spec:** specs/multi-phase/issue-149-adw-20260115152330-a2bc90c7-multi-phase.md

## Overview

Super admin-controlled feature flags for organization-level rollout without deployments. Two-tier system: global flag definitions with per-organization overrides, Redis caching (60s TTL), and dual enforcement (FastAPI dependency + React hook).

## Implementation

### Backend Files

- `app/backend/src/models/feature_flag.py`: Global flag model (unique key)
- `app/backend/src/models/feature_flag_override.py`: Per-org override model
- `app/backend/src/crud/feature_flag.py`: CRUD + flag resolution logic
- `app/backend/src/services/feature_flag_cache.py`: Redis cache with graceful degradation
- `app/backend/src/api/feature_flag.py`: Admin + org API endpoints
- `app/backend/src/api/deps.py`: `require_feature_flag()` dependency
- `app/backend/src/serialisers/feature_flag.py`: Pydantic models
- `app/backend/alembic/versions/8036cf91426a_add_feature_flag_and_override_models.py`: Migration
- `app/backend/tests/unit_tests/test_feature_flag.py`: 1000+ line test suite

### Frontend Files

- `app/frontend/src/features/featureFlags/featureFlagsApi.ts`: RTK Query integration
- `app/frontend/src/features/featureFlags/featureFlagsSlice.ts`: Redux state
- `app/frontend/src/hooks/useFeatureFlag.ts`: Component-level hook
- `app/frontend/src/pages/admin/FeatureFlagsPage.tsx`: Admin UI
- `app/frontend/src/components/feature-flags/FeatureFlagForm.tsx`: Create/edit form
- `app/frontend/src/components/feature-flags/FeatureFlagOverrideDialog.tsx`: Override dialog
- `app/frontend/src/locales/{en,de,xh,zu,nso}/admin.json`: i18n translations

## Architecture

- **Global vs Tenant-Scoped**: FeatureFlag (global, no org_id) + FeatureFlagOverride (org-scoped) enables system-wide definitions with per-org customization
- **Soft Deletes**: Both models use deleted_time for audit trail
- **Cache Strategy**: Individual org cache invalidated on override; all orgs invalidated on flag changes
- **Graceful Degradation**: Falls back to DB if Redis unavailable
- **Dual Enforcement**: Backend via `require_feature_flag()`, frontend via `useFeatureFlag()` hook

## Usage

### Backend Endpoint Protection
```python
from src.api.deps import require_feature_flag

@router.get("/advanced-feature")
async def feature(_: None = Depends(require_feature_flag("advanced_analytics"))):
    return {"data": "analytics"}
```

### Frontend Conditional Rendering
```typescript
import { useFeatureFlag } from '@/hooks'

function MyComponent() {
  const enabled = useFeatureFlag('advanced_analytics')
  return enabled && <AnalyticsPanel />
}
```

### Flag Resolution
- **Backend**: `GET /api/v1/feature-flags/` (authenticated)
- **Frontend**: `useFeatureFlag()` reads from Redux (auto-fetched on init)

## Configuration

- **Cache TTL**: 60 seconds (edit `FeatureFlagCache.FEATURE_FLAG_TTL`)
- **Cache Key**: `feature_flags:{organization_id}`
- **No new env vars** - uses existing Redis

## Testing

```bash
cd app/backend && make test  # CRUD, cache, permissions, org isolation
cd app/frontend && npm run test  # Hook tests
```

## Performance & Limitations

- **~95% query reduction** via Redis caching
- **Eventually consistent**: 60s propagation window
- **Unique flag keys** required across system
- **No gradual rollouts** (future enhancement)

## Future Enhancements

- Percentage-based rollouts
- Scheduled flag changes
- Usage analytics
- Bulk override operations
