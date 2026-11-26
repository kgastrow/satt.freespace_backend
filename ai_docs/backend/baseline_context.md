# Backend Architecture Overview

FastAPI backend with async SQLAlchemy, Redis caching, ARQ background jobs, and row-level multi-tenancy.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 with AsyncSession |
| Validation | Pydantic v2 |
| Cache/Queue | Redis + ARQ |
| Database | PostgreSQL + PgBouncer |

## Multi-Tenancy (CRITICAL)

Row-level multi-tenancy: multiple organizations share the same database with data isolation at application layer.

**Rules**:
- Every user belongs to one organization
- Tenant-scoped models include `organization_id` FK
- **ALL queries MUST filter by `organization_id`**
- Use `current_user.organization_id` from JWT (never trust user input)
- Super admins (`is_admin=True`) bypass organization restrictions

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `src/api/` | FastAPI routers, `deps.py` for auth dependencies |
| `src/api/v1/` | API v1 router aggregation (register new routers here) |
| `src/core/` | `config.py`, `security.py` |
| `src/crud/` | Async database operations |
| `src/models/` | SQLAlchemy models |
| `src/database.py` | Base class, async engine, session factory |
| `src/serialisers/` | Pydantic request/response DTOs |
| `src/services/` | Business logic, cache, email |
| `src/workers/` | ARQ background workers |
| `tests/` | Test suite |
| `alembic/` | Database migrations |

## Core Patterns

### Models (`src/models/`)
- Inherit from `Base` (from `src/database.py`)
- UUID primary keys, `created_time`, `updated_time` timestamps
- Soft deletes via `deleted_time` (never hard delete)
- Tenant-scoped models include `organization_id` FK

### Serializers (`src/serialisers/`)
- Pydantic v2 models with `ConfigDict(extra="forbid")` for requests
- Naming: `{Operation}{Entity}Request/Response`

### CRUD (`src/crud/`)
- Async functions with `AsyncSession` as first param
- **MUST** filter by `organization_id` for tenant-scoped models
- Use `select()` with `await session.execute()`

### API Endpoints (`src/api/`)
- All endpoints under `/api/v1/` prefix
- Use `CurrentUser` dependency for auth context
- Extract `organization_id` from `current_user.organization_id`

### Example Pattern
```python
@router.get("")
async def list_items(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    items, total = await get_items(
        session=session,
        organization_id=current_user.organization_id  # ALWAYS pass from JWT
    )
    return {"items": items, "total": total}
```

## Authentication

| Dependency | Purpose |
|------------|---------|
| `get_current_user` | Validates JWT, returns `CurrentUser` |
| `get_current_super_admin` | Requires `is_admin=True` |
| `get_current_user_admin` | Requires `owner`/`admin` role OR super admin |
| `require_role(name)` | Factory: requires specific role |
| `require_permission(code)` | Factory: requires permission code (format: `resource:action`) |
| `require_any_permission(*codes)` | Factory: requires ANY of listed permissions |
| `require_feature_flag(key)` | Factory: requires feature flag enabled for org |

`CurrentUser` provides: `id`, `email`, `organization_id`, `is_admin`, `email_verified`, `roles`, `org_is_active`, `org_name`, `is_impersonating`, `impersonator_id`

**Roles vs User Types:** Roles control permission levels (viewer → member → manager → admin → owner). User Types define fundamentally different user categories with distinct workflows and optional onboarding (e.g., field workers vs back-office staff). See `context/user_types.md` for when to create new user types vs roles.

## Configuration

Settings via `config.json` loaded by `src/core/config.py`. See `config.json.example` for all options.

## Best Practices

| Rule | Description |
|------|-------------|
| Soft deletes | Never hard delete, use `deleted_time` |
| Validate early | Pydantic for all input |
| Thin controllers | API endpoints handle HTTP only |
| Pure CRUD | No business logic in data access |
| Async everywhere | All I/O uses async/await |
| Type hints | Use throughout for IDE support |
| Tenant isolation | Always filter by `organization_id`, always test isolation |

## Specialized Context Files

| File | Topic |
|------|-------|
| `context/api.md` | FastAPI router patterns |
| `context/auth.md` | Authentication/authorization |
| `context/crud.md` | Async CRUD patterns |
| `context/models.md` | SQLAlchemy conventions |
| `context/serializers.md` | Pydantic schemas |
| `context/multitenancy.md` | Multi-tenancy details |
| `context/testing.md` | Async pytest patterns |
| `context/caching.md` | Redis caching |
| `context/background_jobs.md` | ARQ workers |
| `context/cron_scheduler.md` | Database-driven cron jobs |
| `context/permissions.md` | Permission system |
| `context/user_types.md` | User types, roles & onboarding |
| `context/notifications.md` | Notification system |
| `context/files.md` | File management |
| `context/async_database.md` | PgBouncer/async patterns |
| `context/audit_logging.md` | Audit log system |
| `context/two_factor.md` | 2FA implementation |
| `context/sso.md` | SSO integration |
| `context/security.md` | CORS, cookies, CSP headers |
| `context/feature_flags.md` | Feature flag system |
| `context/websockets.md` | WebSocket connections |
| `context/payments.md` | Payment integration |
| `context/metrics.md` | Prometheus metrics |

## Pattern Guides

| File | Topic |
|------|-------|
| `patterns/exception_handling.md` | Exception handling standards |
| `patterns/soft_delete_checklist.md` | Soft delete implementation |
| `patterns/permission_grant_guide.md` | Adding new permissions |
