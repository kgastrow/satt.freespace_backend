# API Endpoint Patterns

FastAPI routers in `app/backend/src/api/`, served under `/api/v1/` prefix.

## API Versioning

- **URL-based**: All endpoints use `/api/v1/` prefix
- **Structure**: `src/api/v1/__init__.py` aggregates routers into `v1_router`
- **Health endpoints**: `/health` and `/health/detailed` remain at root (unversioned)

Adding new version: Create `src/api/v2/__init__.py`, mount in `main.py` with `/api/v2`.

## Available Routers

**Note**: The canonical router list is in `src/api/v1/__init__.py`.

### Authentication & Sessions
| File | Path | Description |
|------|------|-------------|
| `auth.py` | `/auth/*` | Login, logout, refresh |
| `sessions.py` | `/sessions/*` | Session management |
| `sso.py` | `/sso/*` | SSO authentication |
| `account_linking.py` | `/auth/sso/*` | SSO account linking |
| `organization_sso_settings.py` | `/organization-sso-settings/*` | Per-org SSO config |
| `two_factor.py` | `/two-factor/*` | 2FA setup/verification |
| `organization_two_factor_settings.py` | `/organization-two-factor-settings/*` | Org 2FA policies |
| `api_key.py` | `/api-keys/*` | API key management |
| `api_key_rate_limit.py` | `/admin/api-key-rate-limits/*` | Rate limit config (super admin) |

### User Management
| File | Path | Description |
|------|------|-------------|
| `user.py` | `/user/*` | Self-service profile, registration |
| `users.py` | `/users/*` | Admin user CRUD (requires permission) |
| `user_otp.py` | `/user-otp/*` | OTP generation/verification |
| `user_role.py` | `/user-roles/*` | Role assignment |
| `user_data.py` | `/users/me/*` | GDPR data export/deletion |
| `email_change.py` | `/users/me/email/*` | User email change |
| `user_identities.py` | `/user/me/identities/*` | Connected account management |
| `phone_verification.py` | `/user/me/phone/*` | Phone verification |
| `user_type.py` | `/user-types/*`, `/admin/user-types/*` | User type management (no prefix, inline paths) |

### Organization & Admin
| File | Path | Description |
|------|------|-------------|
| `organization.py` | `/organizations/*` | Organization management (super admin) |
| `role.py` | `/roles/*` | Role management (super admin) |
| `admin.py` | `/admin/*` | Super admin operations |
| `impersonation.py` | `/admin/impersonate/*`, `/impersonate/*` | Admin impersonation (two routers) |
| `system_config.py` | `/admin/system-config/*` | System configuration (super admin) |
| `cron_jobs.py` | `/cron-jobs/*` | Cron job management (super admin) |
| `background_jobs.py` | `/background-jobs/*` | Background job management (super admin) |
| `request_log.py` | `/admin/request-logs/*` | Request logging (super admin) |
| `maintenance.py` | `/maintenance/*` | Maintenance mode |

### Notifications & Announcements
| File | Path | Description |
|------|------|-------------|
| `user_notification.py` | `/notifications/in-app/*` | User in-app notifications |
| `notification.py` | `/notifications/*` | Send, templates, preferences |
| `announcement.py` | `/announcements/*` | System announcements |
| `email_settings.py` | `/email-settings/*` | Email configuration |
| `webhooks_notifications.py` | `/webhooks/notifications/*` | Notification webhooks |

### Files
| File | Path | Description |
|------|------|-------------|
| `file.py` | `/files/*` | File upload/download |
| `file_serve.py` | `/files/serve/*` | Local file serving |

### Onboarding
| File | Path | Description |
|------|------|-------------|
| `onboarding.py` | `/onboarding/*` | User onboarding workflow |
| `onboarding_step.py` | `/admin/onboarding-steps/*` | Onboarding config (super admin) |
| `onboarding_review.py` | `/onboarding/review/*` | Onboarding review (org admin) |

### Feature Flags & Feedback
| File | Path | Description |
|------|------|-------------|
| `feature_flag.py` | `/feature-flags/*`, `/admin/feature-flags/*` | Feature flags (combines two sub-routers) |
| `feedback.py` | `/feedback/*` | User feedback system |

### Payments
| File | Path | Description |
|------|------|-------------|
| `payments.py` | `/payments/*` | Payment processing |
| `payment_settings.py` | `/payment-settings/*` | Payment configuration |
| `payment_methods.py` | `/payment-methods/*` | Payment methods |
| `webhooks_payments.py` | `/webhooks/payments/*` | Payment webhooks |

### Other
| File | Path | Description |
|------|------|-------------|
| `audit_log.py` | `/audit-logs/*` | Audit log viewing |
| `metrics.py` | `/metrics/*` | Prometheus metrics |
| `help_center.py` | `/help/*` | Help center content |
| `about.py` | `/about/*` | About page (public read, admin write) |
| `changelog.py` | `/changelogs/*` | Changelog management |
| `report.py` | `/reports/*` | Report generation |
| `report_schedule.py` | `/report-schedules/*` | Scheduled reports |
| `websocket.py` | (no prefix) | WebSocket connections |

## Core Principles

1. Use `APIRouter` for organization
2. Dependency injection for auth and sessions
3. Pydantic models for all request bodies (not `dict`)
4. Handle HTTP concerns only - delegate business logic to CRUD/services
5. **Multi-tenancy**: Extract `organization_id` from `CurrentUser`, pass to CRUD
6. **Localized responses**: Use `create_http_exception()` with `detail_code`

## Endpoint Pattern

```python
import traceback
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_session, get_current_user, CurrentUser
from src.serialisers.user import CreateUserRequest, UserResponse
from src.core.exceptions import create_http_exception
from src.logger.logger import Logger as logger

router = APIRouter(prefix="/users", tags=["users"])

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    request: CreateUserRequest,
    http_request: Request,  # Required for error traceback capture
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    organization_id = current_user.organization_id  # CRITICAL: always pass to CRUD
    try:
        user = await create_user(session, request.model_dump(), organization_id)
        return UserResponse(id=str(user.id), email=user.email)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        error_tb = traceback.format_exc()
        logger.error(f"Error creating user: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
```

## Error Handling Pattern

**CRITICAL**: All endpoints must follow this exception handling pattern:

1. **`ValueError`**: Business logic errors -> 400 with `create_http_exception()`
2. **`HTTPException`**: Re-raise as-is (don't wrap)
3. **`Exception`**: Log with traceback, store in `request.state.error_traceback`, return 500

**Why `request.state.error_traceback`?** The request logging middleware captures stack traces for failed requests. Without it, 500 errors have no traceback in logs.

### Exception Types: When to Use What

| Exception Type | Use Case | Example |
|---------------|----------|---------|
| `create_http_exception()` | Client-facing errors needing i18n | Not found, validation errors, 500s |
| Bare `HTTPException` | Authorization/permission denials | 403 Forbidden (not localizable) |

**Rule of thumb**: Use `create_http_exception()` for anything the user sees. Bare `HTTPException` is acceptable for simple authorization denials where `detail_code` doesn't add value.

```python
# Use create_http_exception for user-facing errors (preferred)
raise create_http_exception(
    status_code=404, detail="User not found", detail_code="user.not_found"
)

# Bare HTTPException acceptable for permission denials
raise HTTPException(status_code=403, detail="Only super admins can grant super admin privileges")
```

## Authentication Dependencies

### Cookie-Based Refresh Tokens

Refresh tokens are delivered via httpOnly cookies. Access tokens remain in JSON responses (15-minute TTL).

- **Cookie name**: `refresh_token`
- **Attributes**: `HttpOnly`, `Secure` (configurable), `SameSite=Lax`, `Path=/api/v1/auth`
- **Functions** from `src/core/cookies`:
  - `set_refresh_cookie(response, token)`
  - `get_refresh_token_from_cookie(request)`
  - `clear_refresh_cookie(response)`

### JWT-Based Authentication

| Dependency | Purpose |
|-----------|---------|
| `get_current_user` | Basic auth required |
| `get_current_super_admin` | Super admin only |
| `get_current_user_admin` | User admin role (owner/admin) |
| `require_role("manager")` | Specific role required |
| `require_permission("users:read")` | Permission required (preferred) |
| `require_any_permission("a", "b")` | Any of listed permissions |
| `require_feature_flag("flag_key")` | Feature flag must be enabled |

All from `src.api.deps`. Super admins bypass all permission and feature flag checks.

### API Key Authentication

| Dependency | Purpose |
|-----------|---------|
| `get_current_api_key` | API key auth only |
| `get_current_user_or_api_key` | Accepts either JWT or API key |

**Key Concepts**:
- **Header**: `X-API-Key` (takes precedence over `Authorization: Bearer`)
- **Organization-scoped**: API keys are tied to an organization
- **Permission-based**: Checked via `ApiKeyContext.has_permission()`
- **Rate-limited**: Configurable per-permission via `/admin/api-key-rate-limits/*`

**Context Classes** from `src/api/deps`:
- `ApiKeyContext`: `api_key_id`, `organization_id`, `permissions`, `prefix`
- `UnifiedAuthContext`: Unified context with `is_api_key` flag

```python
from src.api.deps import get_current_user_or_api_key, UnifiedAuthContext

@router.get("/data")
async def get_data(
    auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    organization_id = auth.organization_id  # Works for both JWT and API key
    if auth.is_api_key and not auth.has_permission("data:read"):
        raise HTTPException(status_code=403, detail="Permission denied")
```

## HTTP Status Codes

| Code | Usage |
|------|-------|
| `200` | Success (GET, PUT, DELETE) |
| `201` | Created (POST) |
| `202` | Accepted (async operations) |
| `400` | Bad Request (validation errors) |
| `401` | Unauthorized (not authenticated) |
| `403` | Forbidden (not authorized) |
| `404` | Not Found |
| `409` | Conflict (unique constraint violations) |
| `500` | Internal Server Error |

## Router Registration

In `src/api/v1/__init__.py`:
```python
from fastapi import APIRouter
from src.api import auth, users, ...

v1_router = APIRouter()
v1_router.include_router(auth.router)
v1_router.include_router(users.router)
```

**Important**: Router include order matters. More specific routes must come before generic ones (e.g., `user_notification.router` before `notification.router`).

## API Response Format Standards

This section documents when to use structured responses with `message`/`message_code` vs returning models directly.

### Response Types by Operation

| Operation | Response Format | Status Code | Example |
|-----------|-----------------|-------------|---------|
| **Create** | Structured with message | `201` | `CreateUserApiResponse` |
| **Update** | Structured with message | `200` | `AdminUpdateUserResponse` |
| **Delete** | Structured with message OR 204 | `200` or `204` | `DeleteUserApiResponse` or `None` |
| **Get (single)** | Model directly | `200` | `UserDetailResponse` |
| **List** | List response with pagination | `200` | `UserEnhancedListResponse` |
| **Action** | Structured with message | `200` | `SuspendUserResponse` |

### Mutation Responses (Create/Update/Delete/Actions)

State-changing operations return a structured response with i18n support:

```python
from pydantic import BaseModel, Field
from src.core.response_codes import get_response_code

# Define response serializer (in src/serialisers/)
class CreateResourceResponse(BaseModel):
    """Response for resource creation."""
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    resource: ResourceResponse  # The created resource data


# In endpoint (in src/api/)
@router.post("", response_model=CreateResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource_endpoint(...):
    # ... create resource ...

    return CreateResourceResponse(
        message="Resource created successfully",
        message_code=get_response_code("resource.created"),
        resource=ResourceResponse.model_validate(new_resource),
    )
```

**Key points**:
- Use `get_response_code()` to map message keys to translation codes
- Include the created/updated resource data in the response
- Message codes follow `domain.action` pattern (e.g., `user.created`, `role.updated`)

### Update Response Example

```python
class UpdateResourceResponse(BaseModel):
    """Response for resource update."""
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    resource: ResourceResponse


@router.put("/{resource_id}", response_model=UpdateResourceResponse)
async def update_resource_endpoint(...):
    # ... update resource ...

    return UpdateResourceResponse(
        message="Resource updated successfully",
        message_code=get_response_code("resource.updated"),
        resource=ResourceResponse.model_validate(updated_resource),
    )
```

### Delete Response Options

**Option 1: Structured response (preferred when confirmation needed)**
```python
class DeleteResourceResponse(BaseModel):
    """Response for resource deletion."""
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    resource_id: str  # ID of deleted resource


@router.delete("/{resource_id}", response_model=DeleteResourceResponse)
async def delete_resource_endpoint(...):
    # ... soft delete resource ...

    return DeleteResourceResponse(
        message="Resource deleted successfully",
        message_code=get_response_code("resource.deleted"),
        resource_id=str(deleted_resource.id),
    )
```

**Option 2: No content (for simple deletions)**
```python
@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource_endpoint(...):
    # ... soft delete resource ...
    return None
```

### Read Responses (Get/List)

Read operations return models directly without message wrapper:

**Single resource (GET)**:
```python
@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource_endpoint(...):
    resource = await get_resource_by_id(session, resource_id, organization_id)
    if not resource:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
            detail_code="resource.not_found",
        )
    return ResourceResponse.model_validate(resource)
```

**List resources (GET)**:
```python
@router.get("", response_model=ResourceListResponse)
async def list_resources_endpoint(...):
    resources, total = await get_resources(session, organization_id, limit, offset)
    return ResourceListResponse(
        items=[ResourceResponse.model_validate(r) for r in resources],
        total=total,
        limit=limit,
        offset=offset,
    )
```

### When to Use Each Pattern

| Pattern | Use When |
|---------|----------|
| **Structured with message** | User needs confirmation of action (create, update, delete, suspend, assign) |
| **Model directly** | Fetching data for display (get single, list) |
| **204 No Content** | Simple deletion where no confirmation needed, or deleting system resources |

### Adding New Response Codes

1. Add code to `src/core/response_codes.py`:
   ```python
   RESPONSE_CODES = {
       # ... existing codes ...
       "resource.created": "resource.created",
       "resource.updated": "resource.updated",
       "resource.deleted": "resource.deleted",
   }
   ```

2. Add translations to every frontend locale file
   (`frontend/src/locales/{lang}/backend.json` - currently `en` only)

**This is not optional bookkeeping.** `create_http_exception()` and
`create_success_response()` call `get_response_code()` *before* building their
result, and `get_response_code()` raises `KeyError` on an unregistered key. An
unregistered `detail_code=` therefore never produces the intended 4xx: the
`KeyError` escapes into the surrounding `except Exception` handler and the caller
gets a **500 `common.internal_error`** instead. That silently mis-statused 68
call sites before it was caught.

`tests/unit_tests/test_response_code_registry.py` now AST-scans `src/` and fails
CI on any unregistered literal, and on any registered code shipped without
English copy.

## Audit Logging

For state-changing operations (POST, PUT, DELETE), use the audit service.

**Import**:
```python
from src.services.audit import audit_service, get_client_ip, get_user_agent
```

### Method Signatures

```python
# CREATE - Log new resource creation
await audit_service.log_create(
    session=session,
    organization_id=organization_id,
    resource_type="User",
    resource_id=str(new_user.id),
    actor_id=current_user.id,
    ip_address=get_client_ip(http_request),
    user_agent=get_user_agent(http_request),
    resource_data={"email": new_user.email, "first_name": new_user.first_name},  # Passwords auto-redacted
    # Optional: impersonated_by=str, resource_context=dict
)

# UPDATE - Log changes with old/new values
await audit_service.log_update(
    session=session,
    organization_id=organization_id,
    resource_type="User",
    resource_id=str(user.id),
    old_values={"email": "old@example.com", "first_name": "Old"},
    new_values={"email": "new@example.com", "first_name": "New"},
    actor_id=current_user.id,
    ip_address=get_client_ip(http_request),
    user_agent=get_user_agent(http_request),
    # Optional: impersonated_by=str, resource_context=dict
)

# DELETE - Log resource deletion
await audit_service.log_delete(
    session=session,
    organization_id=organization_id,
    resource_type="User",
    resource_id=str(user.id),
    actor_id=current_user.id,
    ip_address=get_client_ip(http_request),
    user_agent=get_user_agent(http_request),
    resource_data={"email": user.email},  # Data before deletion
    # Optional: impersonated_by=str, resource_context=dict
)
```

**Notes**:
- `resource_name` is auto-extracted from `resource_data`/`new_values` based on resource type
- Passwords in `resource_data` are automatically redacted to `[REDACTED]`
- `log_update` skips logging if `old_values` and `new_values` are identical

## Localized Responses

Codes defined in `src/core/response_codes.py`.

**Errors**: Use `create_http_exception()`:
```python
from src.core.exceptions import create_http_exception
raise create_http_exception(status_code=404, detail="User not found", detail_code="user.not_found")
```

**Adding codes**: Update `response_codes.py` **and** `frontend/src/locales/en/backend.json` (plus any other locale directory that exists - currently `en` only). An unregistered code becomes a 500, not the status you asked for; see "Adding New Response Codes" above.

## Best Practices

**DO**:
- Extract `organization_id` from `CurrentUser`, pass to all CRUD calls
- Import serializers from `src/serialisers/`
- Use `require_permission()` over `require_role()`
- Add audit logging for state-changing operations
- Use `create_http_exception()` with `detail_code` for client-facing errors
- Include `http_request: Request` parameter for error traceback capture
- Follow the 3-tier exception pattern: `ValueError` -> `HTTPException` -> `Exception`

**DON'T**:
- Put business logic in API endpoints
- Trust `organization_id` from request body
- Expose internal error details (`detail=str(e)` in 500s)
- Use bare `except Exception:` without logging and traceback storage

## Query DSL for List Endpoints

**ALL list endpoints MUST use the standard DSL pattern.**

| Concern | Format | Example |
|---------|--------|---------|
| Filter | `filter[field]=value` | `filter[status]=pending` |
| Operator | `filter[field][op]=value` | `filter[created_at][gte]=2024-01-01` |
| Sort | `sort=field:dir` | `sort=created_at:desc` |
| Pagination | `limit=N&offset=N` | `limit=20&offset=0` |
| Cursor Pagination | `limit=N&cursor=X` | `limit=50&cursor=abc123` |
| Search | `q=term` | `q=john` |
| Fields | `fields=a,b,c` | `fields=id,email,name` |

**Operators**: `eq` (default), `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`, `is_null`

### Filter Implementation: Two Approaches

**1. Dynamic Parsing (flexible, less OpenAPI visibility)**:
```python
from src.core.query_params import parse_filters, parse_sort, get_pagination_params

ALLOWED_FILTERS = {"status", "user_type_id"}
ALLOWED_SORTS = {"name", "created_at"}

@router.get("")
async def list_items(request: Request):
    filters = parse_filters(request, allowed_fields=ALLOWED_FILTERS)
    sorts = parse_sort(request.query_params.get("sort"), allowed_fields=ALLOWED_SORTS)
    limit, offset = get_pagination_params(request)
    # Pass filters to CRUD which uses apply_filters()
```

**2. Explicit Query Params (better OpenAPI docs, type safety)**:
```python
@router.get("")
async def list_items(
    request: Request,
    filter_status: str | None = Query(default=None, alias="filter[status]"),
    filter_user_type_id: str | None = Query(default=None, alias="filter[user_type_id]"),
    sort: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    # Pass filter values directly to CRUD function
    items = await get_items(
        session, org_id,
        filter_status=filter_status,
        filter_user_type_id=filter_user_type_id,
        sort=sort, limit=limit, offset=offset
    )
```

**When to use which**:
- **Explicit params**: When filters are well-defined and you want auto-generated OpenAPI docs
- **Dynamic parsing**: When filter fields vary or you need maximum flexibility

**Utilities** (for dynamic approach):
- `src/core/query_params.py`: `parse_filters()`, `parse_sort()`, `get_pagination_params()`
- `src/core/query_builder.py`: `apply_filters()`, `apply_sort()`, `apply_pagination()`, `apply_search()`

### Pagination Modes

| Mode | Best For | Performance |
|------|----------|-------------|
| Offset | Admin tables, page jumping | O(offset) - degrades at scale |
| Cursor | Logs, infinite scroll, large datasets | O(1) - constant |

**DSL Serializers** in `src/serialisers/query.py`:

| Class | Purpose |
|-------|---------|
| `ListResponseBase` | Base for offset-paginated responses |
| `CursorListResponseBase` | Base for cursor-paginated responses |
| `create_list_response_model()` | Factory for offset-paginated list responses |
| `create_cursor_list_response_model()` | Factory for cursor-paginated list responses |
| `PaginationParams` | Input params for offset pagination |
| `CursorPaginationParams` | Input params for cursor pagination |

**Reference implementations**:
- Offset: `src/api/users.py`
- Cursor: `src/api/request_log.py`

### Sparse Fieldsets

**Use for list endpoints with expensive computed fields or JOINs.**

```python
@router.get("", response_model=ItemListResponse)
async def list_items(
    fields: str | None = Query(default=None, description="Fields to include"),
):
    field_list = fields.split(",") if fields else None

    # Skip expensive operations if field not requested
    needs_storage = field_list is None or "storage_used" in field_list
    needs_last_login = field_list is None or "last_login" in field_list

    items, total, ... = await get_items(
        session, org_id,
        needs_storage=needs_storage,
        needs_last_login=needs_last_login,
    )

    # Build response conditionally
    for item in items:
        response_item = ItemResponse(id=str(item.id))
        if field_list is None or "email" in field_list:
            response_item.email = item.email
        if needs_storage:
            response_item.storage_used = storage_map.get(str(item.id))
        # ... etc
```

**Pattern**: Pass `needs_*` flags to CRUD, conditionally populate response fields.

**Field Mapping**: Map API field names to model attributes:
```python
field_mapping = {"user_type": "user_type_id"}
query = apply_filters(query, Item, filters, field_mapping=field_mapping)
```

## Impersonation

Super admins can impersonate users via the impersonation router.

**Endpoints**:
- `POST /admin/impersonate/{user_id}` - Start impersonation (super admin)
- `POST /impersonate/stop` - Stop impersonation

**Token Context**: `CurrentUser` exposes:
- `is_impersonating: bool`
- `impersonator_id: Optional[str]`
- `impersonation_session_id: Optional[str]`

**Session Validation**: Impersonation sessions are validated server-side on each request. Ended sessions result in 401.
