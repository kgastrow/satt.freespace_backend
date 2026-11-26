# Redis Caching

Cache service at `src/services/cache.py` reduces database queries with graceful degradation when Redis is unavailable.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `REDIS_POOL_SIZE` | `20` | Max connections (`config.json` -> `redis.pool_size`) |
| `CACHE_ENABLED` | `True` | Enable/disable caching |
| `CACHE_JWT_TTL` | 3600s | JWT claims TTL (1 hour max) |
| `CACHE_USER_TTL` | 300s | User data TTL |
| `CACHE_ORG_TTL` | 300s | Organization data TTL |
| `CACHE_ROLES_TTL` | 60s | Roles/permissions TTL |

## Cache Keys

| Type | Key Pattern | TTL |
|------|-------------|-----|
| JWT Claims | `jwt:{sha256(token)[:32]}` | min(token_expiry, CACHE_JWT_TTL) |
| JWT Tracking | `inv:user:{user_id}` | (Redis Set for bulk invalidation) |
| User | `user:{user_id}` | CACHE_USER_TTL |
| Organization | `org:{org_id}` | CACHE_ORG_TTL |
| Roles | `user_roles:{org_id}:{user_id}` | CACHE_ROLES_TTL |
| Permissions | `user_perms:{org_id}:{user_id}` | CACHE_ROLES_TTL |
| Feature Flags | `feature_flags:{org_id}` | 60s |
| Config | `config:request_logging` | 60s |

## API Usage

```python
from src.services.cache import cache_service

# JWT (token is hashed internally via SHA256[:32])
claims = await cache_service.get_jwt_claims(token)
await cache_service.set_jwt_claims(token, claims_dict, token_expiry_timestamp)
await cache_service.invalidate_jwt_for_user(user_id)

# User (invalidate_user also invalidates JWT)
await cache_service.get_user(user_id)
await cache_service.set_user(user_id, user_data)
await cache_service.invalidate_user(user_id)

# Organization
await cache_service.get_organization(org_id)
await cache_service.set_organization(org_id, org_data)
await cache_service.invalidate_organization(org_id)

# Roles/Permissions (org-scoped, invalidation also clears JWT)
await cache_service.get_user_roles(org_id, user_id)
await cache_service.set_user_roles(org_id, user_id, roles_list)
await cache_service.invalidate_user_roles(org_id, user_id)
await cache_service.invalidate_user_permissions(org_id, user_id)
```

## Invalidation Triggers

| Event | Invalidation |
|-------|--------------|
| Logout / Password change | `invalidate_jwt_for_user(user_id)` |
| Role assign/revoke | `invalidate_user_roles()` + `invalidate_user_permissions()` |
| User update/delete | `invalidate_user(user_id)` (cascades to JWT) |
| Organization deactivate | `invalidate_organization(org_id)` + affected users |
| Role permission change | `_invalidate_role_users_cache()` in `src/crud/role_permission.py` |

## Security: Role Permission Cache Invalidation

When a role's permissions change (grant/revoke), `_invalidate_role_users_cache()` in `src/crud/role_permission.py`:
1. Queries all `UserRole` assignments for the role across all organizations
2. Invalidates `user_perms:{org_id}:{user_id}` for each affected user
3. Cascades to JWT invalidation via `invalidate_user_permissions()`

This ensures permission changes take effect immediately rather than waiting for cache expiry.

## Graceful Degradation

All cache methods check `_is_available()` before Redis operations. On failure:
- Returns `None` for gets (falls back to DB query)
- Logs warning and records error metric
- Application continues to function normally

## Prometheus Metrics

From `src/middleware/cache_metrics.py`:

| Metric | Type | Labels |
|--------|------|--------|
| `cache_operations_total` | Counter | operation, cache_type, result (hit/miss/error/success) |
| `cache_operation_duration_seconds` | Histogram | operation, cache_type |
| `cache_memory_bytes` | Gauge | - |
| `cache_connected` | Gauge | - (1=connected, 0=disconnected) |

## Feature Flag Cache

Separate service at `src/services/feature_flag_cache.py`:

```python
from src.services.feature_flag_cache import feature_flag_cache

flags = await feature_flag_cache.get_org_feature_flags(org_id)
await feature_flag_cache.set_org_feature_flags(org_id, flags_dict)  # 60s TTL
await feature_flag_cache.invalidate_org_feature_flags(org_id)
await feature_flag_cache.invalidate_all_feature_flags()  # Uses SCAN for safety
```

## Testing

```python
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_cache():
    with patch('src.services.cache.cache_service') as mock:
        mock.get_jwt_claims = AsyncMock(return_value=None)
        mock.set_jwt_claims = AsyncMock()
        yield mock
```

## Related Files

- `src/services/cache.py` - Main cache service
- `src/services/feature_flag_cache.py` - Feature flag cache
- `src/services/config_cache.py` - Dynamic config cache
- `src/middleware/cache_metrics.py` - Prometheus metrics
- `src/crud/role_permission.py` - Role permission invalidation
