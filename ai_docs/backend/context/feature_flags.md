# Feature Flags

Organization-level feature toggles with global definitions and per-org overrides. Super admin controlled, Redis cached (60s TTL), with dual enforcement (backend + frontend).

## Architecture

| Model | Scope | Key Fields |
|-------|-------|------------|
| `FeatureFlag` | Global | `key` (unique), `name`, `description`, `default_enabled` |
| `FeatureFlagOverride` | Org-scoped | `organization_id`, `feature_flag_id`, `enabled` |

**Resolution Logic**: Override takes precedence over `default_enabled`. If no override exists for an org, the flag's `default_enabled` value is used.

## Creating a New Feature Flag

### 1. Define the Flag (via API or seed script)

**API** (super admin only):
```bash
POST /api/v1/admin/feature-flags
{
  "key": "my_new_feature",
  "name": "My New Feature",
  "description": "Enables the new feature for organizations",
  "default_enabled": false
}
```

**Seed Script** (`app/backend/scripts/seed_first_tenant.py`):
```python
await create_feature_flag(session, {
    "key": "my_new_feature",
    "name": "My New Feature",
    "description": "Enables the new feature",
    "default_enabled": False,
})
```

### 2. Protect Backend Endpoints

```python
from src.api.deps import require_feature_flag
from typing import Annotated
from fastapi import Depends

@router.get("/my-feature")
async def my_feature_endpoint(
    current_user: Annotated[CurrentUser, Depends(require_feature_flag("my_new_feature"))],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    # Returns 403 if flag is disabled for user's organization
    return {"data": "feature content"}
```

### 3. Protect Frontend Components

```typescript
import { useFeatureFlag } from '@/hooks'

function MyFeatureComponent() {
  const isEnabled = useFeatureFlag('my_new_feature')

  if (!isEnabled) return null
  return <MyFeatureUI />
}
```

## Checking Feature Flags in Code

### Backend

**Endpoint Protection** (preferred):
```python
from src.api.deps import require_feature_flag

@router.get("/endpoint")
async def endpoint(
    _: Annotated[CurrentUser, Depends(require_feature_flag("flag_key"))]
): ...
```

**Direct Check** (for conditional logic within endpoints):
```python
from src.crud.feature_flag import get_resolved_flags_for_organization

resolved = await get_resolved_flags_for_organization(session, organization_id)
if resolved.get("my_feature", False):
    # Feature is enabled
```

### Frontend

```typescript
import { useFeatureFlag } from '@/hooks'

// In component
const isEnabled = useFeatureFlag('my_feature')

// Conditional rendering
return isEnabled ? <FeatureComponent /> : null

// Conditional logic
if (isEnabled) {
  // Feature-specific code
}
```

## Enabling/Disabling Flags

### For All Organizations (Change Default)

**API**:
```bash
PUT /api/v1/admin/feature-flags/{flag_id}
{
  "default_enabled": true
}
```

This changes the default for all organizations that don't have an override.

### For Specific Organization (Create Override)

**API**:
```bash
POST /api/v1/admin/feature-flags/{flag_id}/overrides
{
  "organization_id": "uuid-here",
  "enabled": true
}
```

**Programmatically**:
```python
from src.crud.feature_flag import create_override

await create_override(session, flag_id, organization_id, enabled=True)
```

### Remove Override (Revert to Default)

```bash
DELETE /api/v1/admin/feature-flags/{flag_id}/overrides/{organization_id}
```

## Naming Conventions

| Convention | Example | Description |
|------------|---------|-------------|
| Snake case | `user_onboarding` | All lowercase with underscores |
| Feature-descriptive | `advanced_analytics` | Describes the feature being controlled |
| Module prefix (optional) | `billing_v2` | Prefix for related flags |

**Standard Flags** (defined in seed script):
- `api_keys` - API key management feature
- `changelog_enabled` - Changelog viewing feature
- `feedback_widget` - In-app feedback widget
- `user_onboarding` - User onboarding wizard

## Bypass Mechanisms

1. **Super Admins** (`is_admin=True`): Always bypass flag checks
2. **Bypass Permission**: Users with `feature_flags:bypass` permission bypass all checks
3. **Tester Role**: The `tester` role has `feature_flags:bypass` by default

This allows QA testers to access unreleased features without enabling them for the entire organization.

## Caching

| Aspect | Value |
|--------|-------|
| Cache Key | `feature_flags:{organization_id}` |
| TTL | 60 seconds |
| Invalidation (override change) | Single org cache invalidated |
| Invalidation (flag change) | All org caches invalidated (uses SCAN) |
| Graceful Degradation | Falls back to DB if Redis unavailable |

```python
from src.services.feature_flag_cache import feature_flag_cache

# Manual operations (usually not needed - handled automatically)
flags = await feature_flag_cache.get_org_feature_flags(org_id)
await feature_flag_cache.set_org_feature_flags(org_id, flags_dict)
await feature_flag_cache.invalidate_org_feature_flags(org_id)
await feature_flag_cache.invalidate_all_feature_flags()
```

## Flag Cleanup Best Practices

1. **Document cleanup date**: Add expected removal date in flag description
2. **Remove stale flags**: After feature is fully rolled out and stable, remove the flag
3. **Cleanup steps**:
   - Remove `require_feature_flag()` dependency from endpoints
   - Remove `useFeatureFlag()` calls from frontend
   - Soft delete the flag via API or direct DB update
4. **Grace period**: Keep flag disabled (not deleted) for 1-2 sprints before hard removal

## API Endpoints

### Admin Endpoints (`/api/v1/admin/feature-flags`) - Super Admin Only

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/` | Create flag |
| GET | `/` | List flags with overrides |
| GET | `/{flag_id}` | Get flag details |
| PUT | `/{flag_id}` | Update flag |
| DELETE | `/{flag_id}` | Soft delete flag |
| POST | `/{flag_id}/overrides` | Create/update org override |
| GET | `/{flag_id}/overrides` | List overrides for flag |
| DELETE | `/{flag_id}/overrides/{org_id}` | Delete org override |

### Organization Endpoint (`/api/v1/feature-flags`) - Authenticated Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Get resolved flags for current org |

## Testing

### Backend
```python
from src.crud.feature_flag import create_feature_flag, create_override

# Create test flag
flag = await create_feature_flag(session, {
    "key": "test_feature",
    "name": "Test",
    "default_enabled": False
})

# Enable for specific org
await create_override(session, str(flag.id), str(org_id), enabled=True)

# Test require_feature_flag dependency
from src.api.deps import require_feature_flag, CurrentUser

dependency = require_feature_flag("test_feature")
result = await dependency(current_user, session)
```

### Frontend
```typescript
// Mock flags in test utils
import { renderHook } from '@testing-library/react'
import { useFeatureFlag } from '@/hooks'

// Configure store with test flags
const store = configureStore({
  featureFlags: {
    flags: { my_feature: true },
    isLoaded: true
  }
})

const { result } = renderHook(() => useFeatureFlag('my_feature'), {
  wrapper: ({ children }) => <Provider store={store}>{children}</Provider>
})
expect(result.current).toBe(true)
```

## Related Files

- **Models**: `src/models/feature_flag.py`, `src/models/feature_flag_override.py`
- **CRUD**: `src/crud/feature_flag.py`
- **API**: `src/api/feature_flag.py`
- **Cache**: `src/services/feature_flag_cache.py`
- **Dependencies**: `src/api/deps.py` (`require_feature_flag`)
- **Serializers**: `src/serialisers/feature_flag.py`
- **Migration**: `alembic/versions/8036cf91426a_add_feature_flag_and_override_models.py`
- **Seed Data**: `scripts/seed_first_tenant.py` (`seed_feature_flags`)
- **Tests**: `tests/unit_tests/test_feature_flag.py`
- **Frontend Hook**: `src/hooks/useFeatureFlag.ts`
- **Frontend State**: `src/features/featureFlags/featureFlagsSlice.ts`
- **Frontend API**: `src/features/featureFlags/featureFlagsApi.ts`
- **Admin UI**: `src/pages/admin/FeatureFlagsPage.tsx`
