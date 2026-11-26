# Audit Logging Context

Tracks CRUD operations on tenant-scoped resources for compliance, security, debugging, and accountability.

## Key Files

| File | Purpose |
|------|---------|
| `app/backend/src/models/audit_log.py` | AuditLog model and AuditAction enum |
| `app/backend/src/crud/audit_log.py` | CRUD operations, `compute_changes()` |
| `app/backend/src/services/audit.py` | AuditService helper class |
| `app/backend/src/api/audit_log.py` | API endpoints |

## Model

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | Primary key |
| `created_time` | DateTime | When action occurred |
| `organization_id` | UUID | Multi-tenancy isolation |
| `actor_id` | UUID | Who performed (null for system) |
| `impersonated_by` | UUID | Super admin impersonating (null if not) |
| `action` | str | CREATE, UPDATE, DELETE, IMPERSONATE_START, IMPERSONATE_END |
| `resource_type` | str | e.g., "User", "Role", "Organization" |
| `resource_id` | UUID | ID of affected resource |
| `resource_name` | str | Human-readable identifier (stored at audit time) |
| `resource_context` | JSON | Additional context (optional) |
| `changes` | JSON | `{field: {old: x, new: y}}` |
| `ip_address` | str | Request IP (supports IPv6) |
| `user_agent` | str | Request user agent |

## Using the Audit Service

```python
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.models.audit_log import AuditAction

# Log create
await audit_service.log_create(
    session=session,
    organization_id=current_user.organization_id,
    resource_type="User",
    resource_id=str(new_user.id),
    actor_id=current_user.id,
    ip_address=get_client_ip(request),
    user_agent=get_user_agent(request),
    resource_data={"email": new_user.email},  # Optional
    impersonated_by=impersonated_by,  # Optional
)

# Log update (only logs if changes exist)
await audit_service.log_update(
    session=session,
    organization_id=current_user.organization_id,
    resource_type="User",
    resource_id=str(user.id),
    old_values={"email": old_email},
    new_values={"email": new_email},
    actor_id=current_user.id,
    ip_address=get_client_ip(request),
    impersonated_by=impersonated_by,  # Optional
)

# Log delete
await audit_service.log_delete(
    session=session,
    organization_id=current_user.organization_id,
    resource_type="User",
    resource_id=str(user.id),
    actor_id=current_user.id,
    ip_address=get_client_ip(request),
    resource_data={"email": user.email},  # Optional, captures deleted state
    impersonated_by=impersonated_by,  # Optional
)
```

## Security

| Rule | Detail |
|------|--------|
| Sensitive field redaction | Auto-redacted: password, secret, token, api_key, ssn, card, cvv, pin, private_key, auth_code, access_key |
| Multi-tenancy | All queries MUST filter by `organization_id` |
| Immutability | No UPDATE/DELETE on audit logs, no `deleted_time` field |
| Failure handling | Audit logging silently fails (doesn't break main operation) |
| Impersonation tracking | When super admin impersonates, `impersonated_by` is recorded |

## API Endpoints

Require `audit_logs:read` permission. Path prefix: `/api/v1/audit-logs`

| Endpoint | Purpose |
|----------|---------|
| `GET /` | List with DSL filtering (`filter[resource_type]=User`, `filter[created_time][gte]=...`), sorting (`sort=created_time:desc`), search (`q=term`) |
| `GET /{id}` | Get single log |
| `GET /resource/{resource_type}/{resource_id}` | Resource history |

## Gotchas

- **Capture old values BEFORE updates** - Required for accurate change tracking
- **Add audit logging in API endpoints, not CRUD layer** - Ensures request context (IP, user agent) is available
- **resource_name is auto-extracted** - Based on resource_type mapping in `extract_resource_name()`

## What to Log

**Log**: User CRUD, role assignments, permission changes, org settings, security operations (SSO, 2FA)

**Don't log**: Read operations, internal system jobs, ephemeral data
