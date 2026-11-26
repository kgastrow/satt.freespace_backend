# Permission Grant Flow Guide

This guide documents the patterns for granting, revoking, and testing permissions in the codebase. For a conceptual overview, see [Permissions Context](../context/permissions.md).

## How Permissions Work

### Architecture Overview

The permission system uses a hierarchical model:

```
User
  |
  +-- UserRole (org-scoped) ---> Role (global) ---> RolePermission ---> Permission (global)
  |
  +-- UserUserType (org-scoped) --> UserType (global) --> UserTypePermission --> Permission (global)
```

**Key Concepts:**
- **Permissions** are global and follow the `resource:action` format (e.g., `users:read`, `roles:write`)
- **Roles** are global but assigned to users within an organization context via `UserRole`
- **User Types** provide an alternative permission source (requires approved onboarding)
- **Super Admins** (`is_admin=True`) bypass all permission checks

### Permission Resolution Flow

When checking if a user has a permission:

1. **Super Admin Check**: If `user.is_admin == True`, return `True` (bypasses all checks)
2. **Cache Check**: Look for cached permissions at `user_perms:{org_id}:{user_id}`
3. **Role Permissions**: Query `UserRole -> Role -> RolePermission -> Permission`
4. **User Type Permissions**: Query `UserUserType -> UserType -> UserTypePermission -> Permission` (only if approved and not expired)
5. **Union Results**: Combine permissions from both sources
6. **Cache Result**: Store in Redis for future requests

**Reference:** `src/crud/role_permission.py::get_user_permissions()`

## How to Grant Permissions

### Method 1: Assign a Role (Recommended)

The standard way to grant permissions is by assigning a role that has the desired permissions.

```python
from src.crud.user_role import assign_role

# Assign role to user
await assign_role(
    session=session,
    request={"user_id": user_id, "role_id": role_id},
    assigned_by_user_id=current_user.id,
    organization_id=organization_id,
)
```

**API Endpoint:** `POST /api/v1/user-roles/assign`

```json
{
  "user_id": "uuid-of-user",
  "role_id": "uuid-of-role"
}
```

**Required Permission:** `user_roles:assign`

**Reference:** `src/api/user_role.py`, `src/crud/user_role.py`

### Method 2: Grant Permission to a Role (Admin Only)

Super admins can grant individual permissions to roles.

```python
from src.crud.role_permission import grant_permission_to_role

# Grant permission to role
await grant_permission_to_role(
    session=session,
    role_id=str(role.id),
    permission_id=str(permission.id),
    granted_by_user_id=str(current_user.id),
)
```

**API Endpoint:** `POST /api/v1/admin/role-permissions/assign`

```json
{
  "role_id": "uuid-of-role",
  "permission_id": "uuid-of-permission"
}
```

**Required Access:** Super admin only (`is_admin=True`)

**Reference:** `src/api/admin.py`, `src/crud/role_permission.py`

### Method 3: Grant Permission via User Type (Admin Only)

Super admins can grant permissions through user types.

```python
from src.crud.user_type_permission import grant_permission_to_user_type

# Grant permission to user type
await grant_permission_to_user_type(
    session=session,
    user_type_id=str(user_type.id),
    permission_id=str(permission.id),
    granted_by_user_id=str(current_user.id),
)
```

**API Endpoint:** `POST /api/v1/admin/user-type-permissions/assign`

**Note:** User must have an approved `UserUserType` assignment to receive these permissions.

## How to Revoke Permissions

### Revoke Role from User

```python
from src.crud.user_role import revoke_role

# Revoke role (soft delete)
await revoke_role(
    session=session,
    request={"user_id": user_id, "role_id": role_id},
    organization_id=organization_id,
)
```

**API Endpoint:** `POST /api/v1/user-roles/revoke`

**Required Permission:** `user_roles:revoke`

**Important:** Cannot revoke the last `owner` role from an organization.

### Revoke Permission from Role (Admin Only)

```python
from src.crud.role_permission import revoke_permission_from_role

# Revoke permission (soft delete)
await revoke_permission_from_role(
    session=session,
    role_id=str(role.id),
    permission_id=str(permission.id),
)
```

**API Endpoint:** `POST /api/v1/admin/role-permissions/revoke`

**Required Access:** Super admin only

## How to Check Permissions in API Endpoints

### Single Permission Check

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission

@router.get("/endpoint")
async def protected_endpoint(
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    # User has users:read permission (or is super admin)
    ...
```

### Multiple Permissions (OR Logic)

```python
from src.api.deps import require_any_permission

@router.get("/endpoint")
async def multi_permission_endpoint(
    current_user: Annotated[CurrentUser, Depends(require_any_permission("reports:read", "reports:write"))],
):
    # User has at least one of the specified permissions
    ...
```

### Role-Based Check (Uses Cached JWT Claims)

```python
from src.api.deps import require_role

@router.get("/manager-only")
async def manager_endpoint(
    current_user: Annotated[CurrentUser, Depends(require_role("manager"))],
):
    # User has the "manager" role (or is super admin)
    ...
```

### Super Admin Only

```python
from src.api.deps import get_current_super_admin

@router.get("/super-admin-only")
async def super_admin_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
):
    # User is a super admin (is_admin=True)
    ...
```

### Programmatic Check in Code

```python
from src.crud.role_permission import user_has_permission, get_user_permissions

# Check single permission
has_perm = await user_has_permission(
    session, user_id, organization_id, "users:write"
)

# Get all permissions
permissions = await get_user_permissions(session, user_id, organization_id)
if "users:write" in permissions:
    # User can write users
    ...
```

## How to Test Permission-Related Features

### Test Fixtures Setup

```python
import pytest
from unittest.mock import AsyncMock, patch

from src.models.role import Role
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.models.user_role import UserRole
from src.crud.permission import create_permission
from src.crud.role import create_role
from src.crud.role_permission import grant_permission_to_role

@pytest.fixture
async def test_permission(async_session):
    """Create a test permission."""
    permission = await create_permission(
        async_session,
        code="test:read",
        name="Test Read Permission",
    )
    return permission

@pytest.fixture
async def test_role(async_session):
    """Create a test role."""
    role = await create_role(
        async_session,
        {"name": "test_role", "description": "Test role"},
    )
    return role

@pytest.fixture
async def user_with_permission(async_session, test_organization, test_role, test_permission, test_user):
    """Create a user with a specific permission via role."""
    # Mock cache to prevent cache operations
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # Grant permission to role
        await grant_permission_to_role(
            async_session,
            str(test_role.id),
            str(test_permission.id),
            str(test_user.id),
        )

    # Assign role to user
    user_role = UserRole(
        user_id=test_user.id,
        role_id=test_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()

    return test_user
```

**Reference:** `tests/conftest.py`

### Testing Permission Enforcement

```python
@pytest.mark.asyncio
async def test_endpoint_requires_permission(
    client: AsyncClient,
    test_jwt_token,  # Regular user without permission
    test_admin_token,  # Super admin
):
    """Test that endpoint enforces permission check."""
    # Regular user without permission - should fail
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code == 403
    assert "Permission" in response.json().get("detail", "")

    # Super admin - should succeed (bypasses permission check)
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": test_admin_token},
    )
    assert response.status_code == 200
```

### Testing with Mocked Permissions

```python
@pytest.mark.asyncio
async def test_user_with_permission_can_access(
    client: AsyncClient,
    user_with_permission,
    user_with_permission_token,
):
    """Test that user with correct permission can access endpoint."""
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["users:read"])

        response = await client.get(
            "/api/v1/users",
            headers={"Authorization": user_with_permission_token},
        )

    assert response.status_code == 200
```

### Testing Permission Grant/Revoke

```python
@pytest.mark.asyncio
async def test_grant_permission_to_role(async_session, test_user):
    """Test granting a permission to a role."""
    from src.crud.role_permission import grant_permission_to_role
    from src.crud.permission import create_permission
    from src.crud.role import create_role

    # Create role and permission
    role = await create_role(
        async_session,
        {"name": "test_role", "description": "Test"},
    )
    permission = await create_permission(
        async_session,
        code="users:read",
        name="Read Users",
    )

    # Mock cache service
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        role_permission = await grant_permission_to_role(
            async_session,
            str(role.id),
            str(permission.id),
            str(test_user.id),
        )

    assert role_permission.role_id == role.id
    assert role_permission.permission_id == permission.id
    assert role_permission.deleted_time is None
```

### Testing Permission Isolation Between Organizations

```python
@pytest.mark.asyncio
async def test_permissions_isolated_by_organization(
    async_session, test_organization, second_organization, test_user, second_org_user
):
    """Test that permissions are isolated by organization context."""
    # Create a role and grant permission
    role = await create_role(async_session, {"name": "shared_role", "description": "Shared"})
    perm = await create_permission(async_session, code="users:read", name="Read Users")

    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=None)
        mock_cache.set_user_permissions = AsyncMock()
        mock_cache.invalidate_role_permissions = AsyncMock()
        mock_cache.invalidate_user_permissions = AsyncMock()

        # Grant permission to role
        await grant_permission_to_role(async_session, str(role.id), str(perm.id), str(test_user.id))

        # Assign role to user in org 1 only
        user_role = UserRole(
            user_id=test_user.id,
            role_id=role.id,
            organization_id=test_organization.id,
        )
        async_session.add(user_role)
        await async_session.commit()

        # User in org 1 should have permission
        perms_org1 = await get_user_permissions(async_session, str(test_user.id), str(test_organization.id))
        assert "users:read" in perms_org1

        # User in org 2 should NOT have permission
        perms_org2 = await get_user_permissions(async_session, str(second_org_user.id), str(second_organization.id))
        assert "users:read" not in perms_org2
```

**Reference:** `tests/unit_tests/test_role_permission_crud.py`

### Testing Owner Role Protection

```python
@pytest.mark.asyncio
async def test_cannot_revoke_last_owner_role(
    client: AsyncClient,
    async_session,
    test_organization,
    test_admin_token,
    owner_role,
):
    """Test that the last owner's role cannot be revoked."""
    from src.crud.user import create_user
    from src.models.user_role import UserRole

    # Create a user and assign owner role
    owner_user = await create_user(
        async_session,
        {"email": "owner@test.com", "password": "Password123!", "email_verified": True},
        str(test_organization.id),
    )

    user_role = UserRole(
        user_id=owner_user.id,
        role_id=owner_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Try to revoke - should fail
    response = await client.post(
        "/api/v1/user-roles/revoke",
        json={"user_id": str(owner_user.id), "role_id": str(owner_role.id)},
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 400
    assert "at least one owner" in response.json()["detail"].lower()
```

**Reference:** `tests/api_tests/test_user_role_api.py`

## Common Permission Patterns

### Pattern 1: Read/Write/Delete Trio

Most resources follow the `resource:read`, `resource:write`, `resource:delete` pattern:

```python
# List and get operations
@router.get("/items")
async def list_items(
    current_user: Annotated[CurrentUser, Depends(require_permission("items:read"))],
): ...

# Create and update operations
@router.post("/items")
async def create_item(
    current_user: Annotated[CurrentUser, Depends(require_permission("items:write"))],
): ...

# Delete operations
@router.delete("/items/{id}")
async def delete_item(
    current_user: Annotated[CurrentUser, Depends(require_permission("items:delete"))],
): ...
```

### Pattern 2: Admin-Level Operations

Some operations require admin-level permissions with additional restrictions:

```python
@router.put("/items/{id}")
async def update_item(
    current_user: Annotated[CurrentUser, Depends(require_permission("items:admin"))],
): ...
```

### Pattern 3: Self-Operation Check

Allow users to perform operations on their own resources:

```python
@router.get("/users/{user_id}/profile")
async def get_user_profile(
    user_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    # Allow self-access or users with users:read permission
    if user_id == current_user.id:
        # User accessing their own profile
        pass
    elif await user_has_permission(session, current_user.id, current_user.organization_id, "users:read"):
        # User has permission to read other users
        pass
    else:
        raise HTTPException(status_code=403, detail="Access denied")
```

### Pattern 4: Hierarchy Validation

Validate role hierarchy before assignment:

```python
from src.crud.user_role import get_user_role_names, validate_role_hierarchy

# Get current user's roles
current_user_roles = await get_user_role_names(session, str(current_user.id), organization_id)

# Validate hierarchy
if not validate_role_hierarchy(current_user_roles, target_role.name):
    raise HTTPException(
        status_code=403,
        detail="Cannot assign a role with higher privileges than your own",
    )
```

**Role Hierarchy (lowest to highest):**
```python
ROLE_HIERARCHY = {
    "viewer": 1,
    "member": 2,
    "manager": 3,
    "admin": 4,
    "owner": 5,
}
```

## Cache Invalidation

When permissions change, caches must be invalidated:

```python
from src.services.cache import cache_service

# Invalidate single user's permissions
await cache_service.invalidate_user_permissions(organization_id, user_id)

# Invalidate user's roles
await cache_service.invalidate_user_roles(organization_id, user_id)

# Invalidate all users with a role (cross-organization)
await cache_service.invalidate_role_permissions(role_id)
```

**Important:** When a role's permissions change, ALL users with that role across ALL organizations have their cache invalidated. This is by design since roles are global entities.

**Reference:** `src/services/cache.py`, `src/crud/role_permission.py::_invalidate_role_users_cache()`

## Standard Roles and Their Permissions

Defined in `scripts/seed_data/role_permissions.yaml`:

| Role | Key Permissions |
|------|-----------------|
| **owner** | All permissions |
| **admin** | Most permissions except `roles:delete`, `file_settings:write`, `organization:write`, `reports:delete` |
| **viewer** | Read-only: `users:read`, `roles:read`, `notifications:read`, `files:read`, `organization:read`, `sso:read`, `reports:read` |
| **member** | Basic: `feedback:submit`, `about:read` |
| **tester** | Testing: `feature_flags:bypass` + read permissions |

## Security Checklist

When implementing permission-protected features:

- [ ] Use appropriate dependency: `require_permission()`, `require_role()`, or `require_any_permission()`
- [ ] Test unauthenticated access (should return 401/403)
- [ ] Test user without permission (should return 403)
- [ ] Test user with correct permission (should succeed)
- [ ] Test super admin bypass (should succeed)
- [ ] Verify cache invalidation when permissions change
- [ ] Check role hierarchy validation for role assignment
- [ ] Prevent self-assignment of roles (except for super admins)
- [ ] Protect the last owner role from revocation

## Related Documentation

- [Permissions Context](../context/permissions.md) - Conceptual overview and API reference
- [Testing Guide](../context/testing.md) - General testing patterns
- [Multitenancy](../context/multitenancy.md) - Organization isolation patterns
- [Caching](../context/caching.md) - Cache invalidation strategies
