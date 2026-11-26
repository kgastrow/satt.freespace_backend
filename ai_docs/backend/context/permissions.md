# Permissions System

## Overview

Fine-grained access control via:
- **Global Permissions**: `resource:action` format (lowercase/underscores: `^[a-z_]+:[a-z_]+$`)
- **Global Roles**: System-wide roles shared across all organizations
- **UserRole**: Org-scoped assignment linking users to global roles
- **UserType Permissions**: Alternative permission source via user types (approved onboarding status required)

## Authorization Hierarchy

1. **Super Admin** (`is_admin=True`) - Bypasses all permission checks
2. **Role-based** - User's roles grant specific permissions
3. **User Type-based** - User's approved user types grant additional permissions
4. **No defaults** - All permissions must be explicitly granted

## Data Models

| Model | Scope | Key Fields |
|-------|-------|------------|
| Role | Global | `name` (unique), `description`, `is_default_on_registration` |
| Permission | Global | `code` (unique), `name`, `resource`, `action`, `display_order` |
| RolePermission | Global | `role_id`, `permission_id`, `granted_by`, `granted_time` |
| UserRole | Org-scoped | `organization_id`, `user_id`, `role_id`, `assigned_by` |
| UserTypePermission | Global | `user_type_id`, `permission_id`, `granted_by` |

**Default Roles**: Roles with `is_default_on_registration=True` are automatically assigned to new users on registration. Use `get_default_registration_roles()` in `src/crud/role.py`.

## Protecting Endpoints

```python
from src.api.deps import require_permission, require_any_permission, require_role
from src.api.deps import get_current_super_admin, get_current_user_admin
from typing import Annotated
from fastapi import Depends

# Single permission
@router.get("/users")
async def list_users(
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)]
): ...

# Multiple permissions (OR logic)
@router.get("/reports")
async def view_reports(
    current_user: Annotated[CurrentUser, Depends(require_any_permission("reports:read", "reports:write"))]
): ...

# Role-based (faster - uses cached JWT claims)
@router.get("/manager-only")
async def manager_endpoint(
    current_user: Annotated[CurrentUser, Depends(require_role("manager"))]
): ...

# Super admin only
@router.get("/super-admin-only")
async def super_admin_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)]
): ...

# Org admin (owner/admin role or super admin)
@router.get("/org-admin-only")
async def org_admin_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user_admin)]
): ...
```

## Checking Permissions in Code

```python
from src.crud.role_permission import user_has_permission, get_user_permissions

has_perm = await user_has_permission(session, user_id, org_id, "users:write")
permissions = await get_user_permissions(session, user_id, org_id)  # Returns list of codes
```

## Caching

**Cache Keys:**
- `user_perms:{org_id}:{user_id}` - User permissions (TTL: configurable)
- `user_roles:{org_id}:{user_id}` - User roles (TTL: configurable)
- `jwt:{hash(token)}` - JWT claims (TTL: token expiry)

**Cross-Tenant Cache Invalidation:**
Roles and permissions are global entities. When a role's permissions change, **all users with that role across ALL organizations** have their cache invalidated.

```python
# In src/crud/role_permission.py
async def _invalidate_role_users_cache(session, role_id):
    # Gets ALL UserRole assignments for this role (no org filter)
    # Invalidates user_perms cache for each user in their respective org
```

This means granting/revoking a permission to a global role (e.g., "manager") triggers cache invalidation for every user with that role in every organization. Plan accordingly for high-traffic systems.

## API Key Permissions

API keys have their own permission system separate from user roles:

**Model**: `ApiKeyPermission` links API keys to global permissions (org-scoped junction table)

**Key Concepts:**
- API keys are org-scoped (`ApiKey.organization_id`)
- Permissions assigned directly to API key (not via roles)
- Use `assign_permissions()` / `remove_permissions()` in `src/crud/api_key.py`
- Validated via `get_current_api_key` dependency in `src/api/deps.py`

**Usage:**
```python
from src.api.deps import get_current_user_or_api_key, UnifiedAuthContext

# Endpoint supporting both user and API key auth
@router.get("/data")
async def get_data(
    auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
):
    if auth.is_api_key:
        # Check auth.permissions for API key permissions
        ...
```

**CRUD Operations:**
```python
from src.crud.api_key import assign_permissions, remove_permissions, get_api_key_permissions

await assign_permissions(session, api_key_id, org_id, ["users:read", "reports:read"])
await remove_permissions(session, api_key_id, org_id, ["users:read"])
perms = await get_api_key_permissions(session, api_key_id, org_id)
```

## API Endpoints

### Roles (`/api/v1/roles`)
| Method | Endpoint | Access |
|--------|----------|--------|
| POST | `/` | Super admin |
| GET | `/` | `roles:read` |
| GET | `/{role_id}` | `roles:read` |
| PUT | `/{role_id}` | Super admin |
| DELETE | `/{role_id}` | Super admin |

### User Roles (`/api/v1/user-roles`)
| Method | Endpoint | Permission |
|--------|----------|------------|
| POST | `/assign` | `user_roles:assign` |
| POST | `/revoke` | `user_roles:revoke` |
| GET | `/users/{user_id}/roles` | `user_roles:read` |
| GET | `/users/{user_id}/roles/history` | `user_roles:read` |

### Permissions & Role Permissions (`/api/v1/admin`)
All super admin only:
- `GET/POST/PUT/DELETE /permissions`
- `GET /permissions/matrix` - Returns all permissions and roles with their assigned permission IDs
- `GET /permissions/matrix/extended` - Includes user types in the matrix
- `POST /role-permissions/assign`
- `POST /role-permissions/revoke`
- `POST /user-type-permissions/assign`
- `POST /user-type-permissions/revoke`

## Security Gotchas

1. **Self-assignment prevention**: Non-super admins cannot assign roles to themselves
2. **Role hierarchy validation**: Non-super admins can only assign roles at or below their privilege level (super admins bypass this check)
3. **UserType permissions require approved onboarding**: Only `OnboardingStatus.APPROVED` and non-expired `UserUserType` entries grant permissions
4. **Cache invalidation is cross-tenant**: Role permission changes affect users across ALL organizations - this is by design since roles are global
5. **Protected system roles**: `admin`, `owner`, `super_admin` cannot be modified or deleted

**Role Hierarchy** (defined in `src/crud/user_role.py`):
```python
ROLE_HIERARCHY = {
    "viewer": 1,
    "member": 2,
    "manager": 3,
    "admin": 4,
    "owner": 5,
}
```

## Standard Permissions

Defined in `scripts/seed_data/permissions.yaml`:

| Resource | Permissions |
|----------|-------------|
| Users | `users:read`, `users:write`, `users:delete` |
| Roles | `roles:read`, `roles:write`, `roles:delete` |
| User Roles | `user_roles:read`, `user_roles:assign`, `user_roles:revoke` |
| Audit Logs | `audit_logs:read` |
| Notifications | `notifications:read`, `notifications:write`, `notifications:send` |
| Templates | `notification_templates:read/write/delete` |
| Notification Settings | `notification_settings:read/write` |
| Notification Categories | `notification_categories:read/write/delete` |
| Files | `files:read`, `files:write`, `files:delete`, `files:admin` |
| File Settings | `file_settings:read/write` |
| Metrics | `metrics:read` |
| Organization | `organization:read`, `organization:write` |
| SSO | `sso:read`, `sso:write` |
| API Keys | `api_keys:read`, `api_keys:write`, `api_keys:delete` |
| Feedback | `feedback:submit`, `feedback:view`, `feedback:respond`, `feedback:delete` |
| Payments | `payments:read`, `payments:create`, `payments:refund` |
| Payment Settings | `payment_settings:read/write` |
| Payment Methods | `payment_methods:read/write/delete` |
| Reports | `reports:read`, `reports:write`, `reports:delete`, `reports:schedule` |
| About | `about:read`, `about:write` |
| Feature Flags | `feature_flags:bypass` |

## Related Files

- **Models**: `src/models/{role,permission,role_permission,user_role,user_type_permission,api_key_permission}.py`
- **CRUD**: `src/crud/{role,permission,role_permission,user_role,user_type_permission,api_key}.py`
- **API**: `src/api/{role,user_role,admin,api_key}.py`
- **Dependencies**: `src/api/deps.py`
- **Cache**: `src/services/cache.py`
- **Seed Data**: `scripts/seed_data/permissions.yaml`, `scripts/seed_data/role_permissions.yaml`
