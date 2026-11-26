"""
Test cases for API key authentication middleware integration.
Tests dual-auth scenarios with both JWT and API key authentication.
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import UnifiedAuthContext, get_current_user_or_api_key
from src.core.security import get_api_key_identifier
from src.crud.api_key import assign_permissions, create_api_key


# ============================================================================
# DUAL AUTH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unified_auth_with_jwt(
    client: AsyncClient, test_user, test_jwt_token, async_session
):
    """Test get_current_user_or_api_key accepts JWT token."""
    # Create a test endpoint that uses dual auth
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-dual-auth")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {
            "organization_id": auth.organization_id,
            "is_api_key": auth.is_api_key,
            "user_id": auth.user_id,
        }

    # Add router to app
    from main import app

    app.include_router(router, prefix="/api/v1")

    # Call endpoint with JWT token
    response = await client.get(
        "/api/v1/test-dual-auth", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["organization_id"] == str(test_user.organization_id)
    assert data["is_api_key"] is False
    assert data["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_unified_auth_with_api_key(
    client: AsyncClient, test_user, async_session: AsyncSession, standard_permissions
):
    """Test get_current_user_or_api_key accepts API key."""
    # Create API key
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Test Auth Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    # Assign permissions
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_user.organization_id),
        permissions=["users:read"],
    )

    # Create test endpoint
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-dual-auth-2")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {
            "organization_id": auth.organization_id,
            "is_api_key": auth.is_api_key,
            "api_key_id": auth.api_key_id,
            "permissions": auth.permissions,
        }

    from main import app

    app.include_router(router, prefix="/api/v1")

    # Call endpoint with API key
    response = await client.get(
        "/api/v1/test-dual-auth-2", headers={"X-API-Key": full_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["organization_id"] == str(test_user.organization_id)
    assert data["is_api_key"] is True
    assert data["api_key_id"] == str(api_key.id)
    assert "users:read" in data["permissions"]


@pytest.mark.asyncio
async def test_unified_auth_no_credentials(client: AsyncClient):
    """Test get_current_user_or_api_key rejects request with no auth."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-dual-auth-3")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {"organization_id": auth.organization_id}

    from main import app

    app.include_router(router, prefix="/api/v1")

    # Call without credentials
    response = await client.get("/api/v1/test-dual-auth-3")

    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_api_key_priority_over_jwt(
    client: AsyncClient,
    test_user,
    test_jwt_token,
    async_session: AsyncSession,
    standard_permissions,
):
    """Test that X-API-Key takes precedence over Authorization header."""
    # Create API key
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Priority Test Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_user.organization_id),
        permissions=["test:permission"],
    )

    # Create test endpoint
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-dual-auth-4")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {"is_api_key": auth.is_api_key, "api_key_id": auth.api_key_id}

    from main import app

    app.include_router(router, prefix="/api/v1")

    # Call with both API key and JWT - API key should win
    response = await client.get(
        "/api/v1/test-dual-auth-4",
        headers={"X-API-Key": full_key, "Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_api_key"] is True
    assert data["api_key_id"] == str(api_key.id)


# ============================================================================
# PERMISSION CHECKING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_api_key_permission_check(
    client: AsyncClient, test_user, async_session: AsyncSession, standard_permissions
):
    """Test that API key permissions are checked correctly."""
    # Create API key with specific permissions
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Limited Permissions Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_user.organization_id),
        permissions=["users:read"],
    )

    # Test has_permission method
    from src.api.deps import get_current_api_key

    api_key_context = await get_current_api_key(full_key, async_session)

    assert api_key_context.has_permission("users:read") is True
    assert api_key_context.has_permission("users:write") is False
    assert api_key_context.has_permission("admin:all") is False


@pytest.mark.asyncio
async def test_unified_auth_permission_check(
    client: AsyncClient, test_user, async_session: AsyncSession, standard_permissions
):
    """Test UnifiedAuthContext permission checking for API keys."""
    # Create API key
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Permission Test Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_user.organization_id),
        permissions=["users:read", "users:write"],
    )

    # Get unified auth context
    from src.api.deps import UnifiedAuthContext, get_current_api_key

    api_key_context = await get_current_api_key(full_key, async_session)
    unified_context = UnifiedAuthContext.from_api_key(api_key_context)

    assert unified_context.has_permission("users:read") is True
    assert unified_context.has_permission("users:write") is True
    assert unified_context.has_permission("admin:all") is False
    assert unified_context.is_api_key is True


# ============================================================================
# EXPIRATION & REVOCATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_expired_api_key_rejected(
    client: AsyncClient, test_user, async_session: AsyncSession
):
    """Test that expired API keys are rejected with 401."""
    # Create API key that expires immediately
    expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Expired Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
        expires_at=expires_at,
    )

    # Try to authenticate with expired key
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-expired")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {"status": "ok"}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get("/api/v1/test-expired", headers={"X-API-Key": full_key})

    assert response.status_code == 401
    assert "Invalid or expired API key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_revoked_api_key_rejected(
    client: AsyncClient, test_user, async_session: AsyncSession
):
    """Test that revoked API keys are rejected with 401."""
    # Create and then revoke API key
    api_key, full_key = await create_api_key(
        session=async_session,
        name="To Be Revoked Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    # Revoke the key (soft delete)
    from src.crud.api_key import delete_api_key

    await delete_api_key(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_user.organization_id),
    )

    # Try to authenticate with revoked key
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-revoked")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {"status": "ok"}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get("/api/v1/test-revoked", headers={"X-API-Key": full_key})

    assert response.status_code == 401
    assert "Invalid or expired API key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_last_used_timestamp_updated(
    client: AsyncClient, test_user, async_session: AsyncSession
):
    """Test that last_used_at is updated on successful authentication."""
    # Create API key
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Usage Tracking Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    # Check initial last_used_at is None
    assert api_key.last_used_at is None

    # Authenticate with the key
    from src.crud.api_key import validate_api_key

    validated_key = await validate_api_key(async_session, full_key)

    assert validated_key is not None
    assert validated_key.last_used_at is not None

    # Store first timestamp
    first_used = validated_key.last_used_at

    # Wait a moment and authenticate again
    import asyncio

    await asyncio.sleep(0.1)

    validated_key_2 = await validate_api_key(async_session, full_key)

    assert validated_key_2 is not None
    assert validated_key_2.last_used_at is not None
    assert validated_key_2.last_used_at > first_used


# ============================================================================
# RATE LIMITING HELPER TESTS
# ============================================================================


def test_api_key_identifier_generation():
    """Test rate limiting identifier generation."""
    api_key_id = "550e8400-e29b-41d4-a716-446655440000"
    org_id = "660e8400-e29b-41d4-a716-446655440000"

    identifier = get_api_key_identifier(api_key_id, org_id)

    assert identifier == f"api_key:{org_id}:{api_key_id}"
    assert identifier.startswith("api_key:")
    assert org_id in identifier
    assert api_key_id in identifier


def test_api_key_identifier_uniqueness():
    """Test that different keys get different identifiers."""
    org_id = "660e8400-e29b-41d4-a716-446655440000"
    key_id_1 = "550e8400-e29b-41d4-a716-446655440000"
    key_id_2 = "550e8400-e29b-41d4-a716-446655440001"

    id1 = get_api_key_identifier(key_id_1, org_id)
    id2 = get_api_key_identifier(key_id_2, org_id)

    assert id1 != id2


# ============================================================================
# INVALID INPUT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_api_key_format(client: AsyncClient):
    """Test that malformed API keys are rejected."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    router = APIRouter()

    @router.get("/test-invalid-key")
    async def test_endpoint(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)]
    ):
        return {"status": "ok"}

    from main import app

    app.include_router(router, prefix="/api/v1")

    # Try with invalid key format (too short)
    response = await client.get(
        "/api/v1/test-invalid-key", headers={"X-API-Key": "short"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_organization_api_key(
    client: AsyncClient, test_user, async_session: AsyncSession
):
    """Test that API keys are isolated by organization."""
    # Create API key for test user's org
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Org Isolation Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )

    # The key is valid, but should only work for its own organization
    # This is enforced at the model level - validate_api_key returns the key
    # with its correct organization_id
    from src.crud.api_key import validate_api_key

    validated = await validate_api_key(async_session, full_key)

    assert validated is not None
    assert str(validated.organization_id) == str(test_user.organization_id)


# ============================================================================
# UNIFIED AUTH CONTEXT TESTS
# ============================================================================


def test_unified_auth_from_user():
    """Test creating UnifiedAuthContext from CurrentUser."""
    from src.api.deps import CurrentUser

    user = CurrentUser(
        id="user-123",
        email="test@example.com",
        organization_id="org-456",
        is_admin=True,
        email_verified=True,
    )

    context = UnifiedAuthContext.from_user(user)

    assert context.organization_id == "org-456"
    assert context.is_api_key is False
    assert context.user_id == "user-123"
    assert context.api_key_id is None
    assert context.is_admin is True


def test_unified_auth_from_api_key():
    """Test creating UnifiedAuthContext from ApiKeyContext."""
    from src.api.deps import ApiKeyContext

    api_key = ApiKeyContext(
        api_key_id="key-123",
        organization_id="org-456",
        permissions=["users:read", "users:write"],
        prefix="abcd1234",
        user_id="user-789",
    )

    context = UnifiedAuthContext.from_api_key(api_key)

    assert context.organization_id == "org-456"
    assert context.is_api_key is True
    assert context.api_key_id == "key-123"
    # API keys surface their creator's user_id so writes are auditable.
    assert context.user_id == "user-789"
    assert context.is_admin is False
    assert "users:read" in context.permissions
    assert "users:write" in context.permissions


def test_unified_auth_permission_with_admin():
    """Test that admin flag bypasses permission checks."""
    from src.api.deps import CurrentUser

    admin_user = CurrentUser(
        id="admin-123",
        email="admin@example.com",
        organization_id="org-456",
        is_admin=True,
        email_verified=True,
    )

    context = UnifiedAuthContext.from_user(admin_user)

    # Admin should have all permissions
    assert context.has_permission("users:read") is True
    assert context.has_permission("users:write") is True
    assert context.has_permission("admin:all") is True
    assert context.has_permission("anything:everything") is True


# ============================================================================
# UNIFIED require_permission GATE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_require_permission_unified_jwt_with_permission(
    client: AsyncClient,
    user_with_permission,
    user_with_permission_token,
):
    """JWT user holding the required permission via a role -> 200."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    from src.api.deps import require_permission_unified

    router = APIRouter()

    @router.get("/test-unified-jwt-pass")
    async def endpoint(
        auth: Annotated[
            UnifiedAuthContext,
            Depends(require_permission_unified("users:read")),
        ],
    ):
        return {"user_id": auth.user_id, "is_api_key": auth.is_api_key}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get(
        "/api/v1/test-unified-jwt-pass",
        headers={"Authorization": user_with_permission_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_api_key"] is False
    assert data["user_id"] == str(user_with_permission.id)


@pytest.mark.asyncio
async def test_require_permission_unified_jwt_admin_bypass(
    client: AsyncClient, test_admin_user, test_organization
):
    """Super admin (is_admin=True) bypasses permission checks on JWT path."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    from src.api.deps import require_permission_unified
    from src.core.security import create_access_token

    admin_token = "Bearer " + create_access_token(
        user_id=str(test_admin_user.id),
        organization_id=str(test_organization.id),
    )

    router = APIRouter()

    @router.get("/test-unified-jwt-admin")
    async def endpoint(
        auth: Annotated[
            UnifiedAuthContext,
            Depends(require_permission_unified("nonexistent:permission")),
        ],
    ):
        return {"is_admin": auth.is_admin}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get(
        "/api/v1/test-unified-jwt-admin", headers={"Authorization": admin_token}
    )

    assert response.status_code == 200
    assert response.json()["is_admin"] is True


@pytest.mark.asyncio
async def test_require_permission_unified_jwt_denied(
    client: AsyncClient, test_user, test_jwt_token, standard_permissions
):
    """JWT user without the required permission -> 403."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    from src.api.deps import require_permission_unified

    router = APIRouter()

    @router.get("/test-unified-jwt-deny")
    async def endpoint(
        auth: Annotated[
            UnifiedAuthContext,
            Depends(require_permission_unified("users:read")),
        ],
    ):
        return {"ok": True}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get(
        "/api/v1/test-unified-jwt-deny", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_require_permission_unified_api_key_pass(
    client: AsyncClient,
    user_with_permission,
    async_session: AsyncSession,
):
    """API key with the permission AND associated user holding it -> 200,
    and auth.user_id is the key's creator (audit-traceable)."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    from src.api.deps import require_permission_unified

    api_key, full_key = await create_api_key(
        session=async_session,
        name="Unified Pass Key",
        organization_id=str(user_with_permission.organization_id),
        created_by=str(user_with_permission.id),
    )
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(user_with_permission.organization_id),
        permissions=["users:read"],
    )

    router = APIRouter()

    @router.get("/test-unified-apikey-pass")
    async def endpoint(
        auth: Annotated[
            UnifiedAuthContext,
            Depends(require_permission_unified("users:read")),
        ],
    ):
        return {
            "is_api_key": auth.is_api_key,
            "user_id": auth.user_id,
            "api_key_id": auth.api_key_id,
        }

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get(
        "/api/v1/test-unified-apikey-pass", headers={"X-API-Key": full_key}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_api_key"] is True
    assert data["user_id"] == str(user_with_permission.id)
    assert data["api_key_id"] == str(api_key.id)


@pytest.mark.asyncio
async def test_require_permission_unified_api_key_lacks_permission(
    client: AsyncClient,
    user_with_permission,
    files_read_permission,
    async_session: AsyncSession,
):
    """API key whose creator has the perm but the key itself doesn't -> 403."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    from src.api.deps import require_permission_unified

    api_key, full_key = await create_api_key(
        session=async_session,
        name="Unified KeyLacks Key",
        organization_id=str(user_with_permission.organization_id),
        created_by=str(user_with_permission.id),
    )
    # Key only gets a different permission, not users:read
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(user_with_permission.organization_id),
        permissions=["files:read"],
    )

    router = APIRouter()

    @router.get("/test-unified-apikey-lacks")
    async def endpoint(
        auth: Annotated[
            UnifiedAuthContext,
            Depends(require_permission_unified("users:read")),
        ],
    ):
        return {"ok": True}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get(
        "/api/v1/test-unified-apikey-lacks", headers={"X-API-Key": full_key}
    )

    assert response.status_code == 403
    assert "API key lacks permission" in response.json()["detail"]


@pytest.mark.asyncio
async def test_require_permission_unified_user_no_longer_has_permission(
    client: AsyncClient,
    test_user,
    async_session: AsyncSession,
    standard_permissions,
):
    """API key has the perm but the associated user does NOT (e.g. role
    removed) -> 403. This proves the intersection at request time prevents
    stale keys from outliving their creator's perms."""
    from typing import Annotated

    from fastapi import APIRouter, Depends

    from src.api.deps import require_permission_unified

    # test_user has no roles -> no permissions. Create a key with users:read
    # anyway (simulating a key created when the user had the role and then
    # had it removed).
    api_key, full_key = await create_api_key(
        session=async_session,
        name="Stale User Perm Key",
        organization_id=str(test_user.organization_id),
        created_by=str(test_user.id),
    )
    await assign_permissions(
        session=async_session,
        api_key_id=str(api_key.id),
        organization_id=str(test_user.organization_id),
        permissions=["users:read"],
    )

    router = APIRouter()

    @router.get("/test-unified-apikey-stale")
    async def endpoint(
        auth: Annotated[
            UnifiedAuthContext,
            Depends(require_permission_unified("users:read")),
        ],
    ):
        return {"ok": True}

    from main import app

    app.include_router(router, prefix="/api/v1")

    response = await client.get(
        "/api/v1/test-unified-apikey-stale", headers={"X-API-Key": full_key}
    )

    assert response.status_code == 403
    assert "associated user no longer has permission" in response.json()["detail"]
