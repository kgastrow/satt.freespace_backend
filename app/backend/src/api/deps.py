"""
FastAPI dependencies for authentication and database sessions.
Uses async patterns with AsyncSession.
"""

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import jwt_decode_options
from src.crud.organization import get_organization_by_id
from src.crud.user import get_user_by_id
from src.database import get_async_session
from src.services.cache import cache_service


# Alias for convenience
get_session = get_async_session


class ApiKeyContext:
    """API key authentication context"""

    def __init__(
        self,
        api_key_id: str,
        organization_id: str,
        permissions: list[str],
        prefix: str,
        user_id: str,
    ):
        self.api_key_id = api_key_id
        self.organization_id = organization_id
        self.permissions = permissions
        self.prefix = prefix
        # user_id is the API key's associated user (api_key.created_by).
        # Writes made via this key are attributed to this user for audit purposes.
        self.user_id = user_id

    def has_permission(self, permission_code: str) -> bool:
        """Check if API key has a specific permission"""
        return permission_code in self.permissions


class CurrentUser:
    """Current authenticated user context"""

    def __init__(
        self,
        id: str,
        email: str,
        organization_id: str,
        is_admin: bool,
        email_verified: bool,
        roles: Optional[list[str]] = None,
        org_is_active: bool = True,
        org_name: Optional[str] = None,
        is_impersonating: bool = False,
        impersonator_id: Optional[str] = None,
        impersonation_session_id: Optional[str] = None,
    ):
        self.id = id
        self.email = email
        self.organization_id = organization_id
        self.is_admin = is_admin
        self.email_verified = email_verified
        self.roles = roles or []
        self.org_is_active = org_is_active
        self.org_name = org_name
        self.is_impersonating = is_impersonating
        self.impersonator_id = impersonator_id
        self.impersonation_session_id = impersonation_session_id

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role (admins have all roles)"""
        return self.is_admin or role_name in self.roles


class UnifiedAuthContext:
    """Unified authentication context supporting both JWT and API key auth"""

    def __init__(
        self,
        organization_id: str,
        is_api_key: bool = False,
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None,
        permissions: Optional[list[str]] = None,
        is_admin: bool = False,
    ):
        self.organization_id = organization_id
        self.is_api_key = is_api_key
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.permissions = permissions or []
        self.is_admin = is_admin

    def has_permission(self, permission_code: str) -> bool:
        """Check if the auth context has a specific permission"""
        if self.is_admin:
            return True
        return permission_code in self.permissions

    @classmethod
    def from_user(cls, user: CurrentUser) -> "UnifiedAuthContext":
        """Create from JWT user context"""
        return cls(
            organization_id=user.organization_id,
            is_api_key=False,
            user_id=user.id,
            is_admin=user.is_admin,
        )

    @classmethod
    def from_api_key(cls, api_key: ApiKeyContext) -> "UnifiedAuthContext":
        """Create from API key context.

        user_id is set to the API key's associated user so writes are
        traceable to a human actor in audit logs.
        """
        return cls(
            organization_id=api_key.organization_id,
            is_api_key=True,
            user_id=api_key.user_id,
            api_key_id=api_key.api_key_id,
            permissions=api_key.permissions,
            is_admin=False,
        )


def get_token_from_header(authorization: Optional[str] = Header(None)) -> str:
    """Extract and validate Bearer token from Authorization header"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is missing"
        )

    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
            )
        return token
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )


async def get_current_user(
    token: Annotated[str, Depends(get_token_from_header)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    """
    Dependency to get current authenticated user.
    Validates JWT token, email verification, and organization context.
    Uses Redis caching to reduce database queries.
    """
    try:
        # SECURITY: Decode and enforce the token type BEFORE any JWT-claims
        # cache read/write. A non-access token (e.g. the pre-2FA interstitial
        # token, or refresh/file-access/unsubscribe/link tokens) must never
        # authenticate a protected endpoint, and must never be served from or
        # admitted to the claims cache. Only genuine access tokens and
        # impersonation tokens (which legitimately authenticate as the target
        # user) may pass. Tokens minted before this deploy may lack the "type"
        # claim; a missing/unknown type is rejected (forces re-login).
        data = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options=jwt_decode_options(),
        )
        if data.get("type") not in ("access", "impersonation"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )

        # Try cache first (safe: only validated access/impersonation tokens
        # can ever have been admitted to this cache).
        cached_claims = await cache_service.get_jwt_claims(token)
        if cached_claims:
            # Validate cached data is still valid
            if not cached_claims.get("org_is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Organization is not active",
                )
            if not cached_claims.get("email_verified", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Email verification required",
                )
            return CurrentUser(
                id=cached_claims["user_id"],
                email=cached_claims["email"],
                organization_id=cached_claims["organization_id"],
                is_admin=cached_claims.get("is_admin", False),
                email_verified=cached_claims.get("email_verified", False),
                roles=cached_claims.get("roles", []),
                org_is_active=cached_claims.get("org_is_active", True),
                org_name=cached_claims.get("org_name"),
                is_impersonating=cached_claims.get("is_impersonating", False),
                impersonator_id=cached_claims.get("impersonator_id"),
                impersonation_session_id=cached_claims.get("impersonation_session_id"),
            )

        # Cache miss - use the already-decoded token and query database
        user_id = data.get("user_id")
        organization_id = data.get("organization_id")
        token_exp = data.get("exp", 0)

        # Check for impersonation context in token
        impersonator_id = data.get("impersonator_id")
        impersonation_session_id = data.get("impersonation_session_id")
        is_impersonating = bool(impersonator_id and impersonation_session_id)

        # Server-side validation for impersonation tokens
        # Ensures session hasn't been ended since token was issued
        if is_impersonating and impersonation_session_id:
            from src.crud.impersonation_session import get_session_by_id

            active_session = await get_session_by_id(session, impersonation_session_id)
            if not active_session or active_session.ended_time is not None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Impersonation session has ended",
                )

        if not organization_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token - missing organization",
            )

        # Validate organization exists and is active
        organization = await get_organization_by_id(session, organization_id)
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organization not found"
            )

        if not organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization is not active",
            )

        # Get user and validate they belong to the organization
        user = await get_user_by_id(session, user_id, organization_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access"
            )

        if not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required",
            )

        # Get user roles
        from src.crud.user_role import get_user_roles

        user_roles, _ = await get_user_roles(
            session, str(user.id), str(organization_id)
        )
        role_names = [ur.role.name for ur in user_roles if ur.role]

        # Build claims for caching
        claims = {
            "user_id": str(user.id),
            "email": user.email,
            "organization_id": str(organization_id),
            "is_admin": user.is_admin or False,
            "email_verified": user.email_verified,
            "roles": role_names,
            "org_is_active": organization.is_active,
            "org_name": organization.name,
            "is_impersonating": is_impersonating,
            "impersonator_id": impersonator_id,
            "impersonation_session_id": impersonation_session_id,
        }

        # Cache for future requests
        await cache_service.set_jwt_claims(token, claims, token_exp)

        return CurrentUser(
            id=str(user.id),
            email=user.email,
            organization_id=str(organization_id),
            is_admin=user.is_admin or False,
            email_verified=user.email_verified,
            roles=role_names,
            org_is_active=organization.is_active,
            org_name=organization.name,
            is_impersonating=is_impersonating,
            impersonator_id=impersonator_id,
            impersonation_session_id=impersonation_session_id,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed"
        )


async def resolve_current_user(token: str, session: AsyncSession) -> CurrentUser:
    """Resolve a bearer token to a :class:`CurrentUser` outside the DI graph.

    ``get_current_user`` is a FastAPI dependency, but some endpoints need to ask
    "is this request ALSO carrying a valid session?" for a request that is not
    itself authenticated -- ``POST /auth/sso/link`` accepts either an existing
    session or the account password as proof, so it cannot declare the
    dependency. This is the supported way to do that: it applies exactly the
    same token-type, organization and user checks, and raises the same
    ``HTTPException`` on failure.

    Args:
        token: The raw bearer token (see :func:`get_token_from_header`).
        session: Database session.

    Returns:
        The authenticated user context.

    Raises:
        HTTPException: 401/403 exactly as ``get_current_user`` would.
    """
    return await get_current_user(token, session)


async def get_current_super_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> CurrentUser:
    """
    Dependency to verify user is a super admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required"
        )
    return current_user


async def get_current_user_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)]
) -> CurrentUser:
    """
    Dependency to verify user has admin privileges or is super admin.
    Accepts: owner or admin roles.
    Uses cached roles from CurrentUser - no additional database query needed.
    """
    # Super admins automatically have admin access
    if current_user.is_admin:
        return current_user

    # Check if user has any admin role (uses cached roles)
    if not (current_user.has_role("owner") or current_user.has_role("admin")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )

    return current_user


def require_role(role_name: str):
    """
    Dependency factory to check if user has a specific role.
    Uses cached roles from CurrentUser - no additional database query needed.

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            current_user: Annotated[CurrentUser, Depends(require_role("manager"))]
        ):
            ...
    """

    async def check_role(
        current_user: Annotated[CurrentUser, Depends(get_current_user)]
    ) -> CurrentUser:
        # Super admins bypass all role checks, or user has the required role
        if not current_user.has_role(role_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' required",
            )

        return current_user

    return check_role


def require_permission(permission_code: str):
    """
    Dependency factory to check if user has a specific permission.
    Super admins (is_admin=True) bypass all permission checks.

    Permission codes follow the format 'resource:action' (e.g., 'users:read', 'roles:write').

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))]
        ):
            ...
    """

    async def check_permission(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> CurrentUser:
        # Super admins bypass all permission checks
        if current_user.is_admin:
            return current_user

        # Check if user has the required permission
        from src.crud.role_permission import user_has_permission

        has_perm = await user_has_permission(
            session, current_user.id, current_user.organization_id, permission_code
        )

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission_code}' required",
            )

        return current_user

    return check_permission


def require_any_permission(*permission_codes: str):
    """
    Dependency factory to check if user has ANY of the specified permissions.
    Super admins (is_admin=True) bypass all permission checks.

    Permission codes follow the format 'resource:action' (e.g., 'users:read', 'roles:write').

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            current_user: Annotated[CurrentUser, Depends(require_any_permission("users:read", "users:write"))]
        ):
            ...
    """

    async def check_any_permission(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> CurrentUser:
        # Super admins bypass all permission checks
        if current_user.is_admin:
            return current_user

        # Get all user permissions and check if any match
        from src.crud.role_permission import get_user_permissions

        user_permissions = await get_user_permissions(
            session, current_user.id, current_user.organization_id
        )

        # Check if user has any of the required permissions
        for perm_code in permission_codes:
            if perm_code in user_permissions:
                return current_user

        # None of the permissions matched
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of the following permissions required: {', '.join(permission_codes)}",
        )

    return check_any_permission


def get_api_key_from_header(x_api_key: Optional[str] = Header(None)) -> str:
    """Extract API key from X-API-Key header"""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="API key is missing"
        )
    return x_api_key


async def get_current_api_key(
    api_key: Annotated[str, Depends(get_api_key_from_header)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyContext:
    """
    Dependency to validate API key authentication.
    Validates the key, checks expiration, enforces rate limits, and returns API key context with permissions.
    """
    try:
        from src.core.api_key_rate_limit import enforce_api_key_rate_limit
        from src.crud.api_key import get_api_key_permissions, validate_api_key
        from src.crud.api_key_rate_limit import get_rate_limit_by_permission
        from src.middleware.security_metrics import record_api_key_failure

        # Validate the API key
        validated_key = await validate_api_key(session, api_key)

        if not validated_key:
            record_api_key_failure("unknown", "invalid_key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
            )

        # Get permissions for this API key
        permissions = await get_api_key_permissions(
            session, str(validated_key.id), str(validated_key.organization_id)
        )

        # Load rate limits for all permissions (cache in dict)
        rate_limits_cache = {}
        for permission_code in permissions:
            rate_limit = await get_rate_limit_by_permission(session, permission_code)
            if rate_limit:
                rate_limits_cache[permission_code] = (
                    rate_limit.requests_per_minute,
                    rate_limit.burst_limit,
                )

        # Enforce rate limits (may raise HTTPException with 429)
        try:
            await enforce_api_key_rate_limit(
                api_key_id=str(validated_key.id),
                api_key_permissions=permissions,
                rate_limits_cache=rate_limits_cache,
                is_admin=False,
            )
        except HTTPException as rate_limit_exc:
            if rate_limit_exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                record_api_key_failure(
                    str(validated_key.organization_id), "rate_limited"
                )
            raise

        return ApiKeyContext(
            api_key_id=str(validated_key.id),
            organization_id=str(validated_key.organization_id),
            permissions=permissions,
            prefix=validated_key.prefix,
            user_id=str(validated_key.created_by),
        )

    except HTTPException:
        # Re-raise HTTP exceptions (including 429 rate limits)
        raise
    except Exception as e:
        # Log unexpected errors
        from src.logger.logger import Logger as logger

        logger.error(f"API key authentication failed: {e}")
        record_api_key_failure("unknown", "authentication_error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication failed",
        )


async def get_current_user_or_api_key(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
) -> UnifiedAuthContext:
    """
    Dependency to accept either JWT or API key authentication.

    Returns a unified auth context with is_api_key flag.
    Checks assigned permissions for API keys against required permissions.
    Updates last-used timestamp on successful API key auth.
    Rejects expired or revoked keys with 401.

    Priority: X-API-Key header takes precedence over Authorization header.
    """
    # Try API key first if present
    if x_api_key:
        try:
            api_key_context = await get_current_api_key(x_api_key, session)
            return UnifiedAuthContext.from_api_key(api_key_context)
        except HTTPException:
            raise

    # Fall back to JWT token
    if authorization:
        try:
            token = get_token_from_header(authorization)
            user = await get_current_user(token, session)
            return UnifiedAuthContext.from_user(user)
        except HTTPException:
            raise

    # Neither auth method provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (JWT or API key)",
    )


def require_permission_unified(permission_code: str):
    """
    Dependency factory enforcing a permission for either JWT or API key auth.

    JWT path:
        - super admins (is_admin=True) bypass the check (existing behavior).
        - otherwise require the permission via user_has_permission().

    API key path:
        - the permission must be assigned to the key, AND
        - the key's associated user (api_key.created_by) must currently hold
          the permission via their roles/user types.
        This intersection means a demoted user's old keys lose access
        automatically without needing manual revocation. Super-admin bypass
        does NOT apply when authenticating via API key — keys are always
        least-privilege.

    Returns the UnifiedAuthContext so endpoints can read actor user_id /
    api_key_id / is_api_key directly.

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            auth: Annotated[
                UnifiedAuthContext,
                Depends(require_permission_unified("users:read")),
            ],
        ):
            ...
    """

    async def check_permission(
        auth: Annotated[UnifiedAuthContext, Depends(get_current_user_or_api_key)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> UnifiedAuthContext:
        from src.crud.role_permission import user_has_permission

        if not auth.is_api_key:
            if auth.is_admin:
                return auth
            has_perm = await user_has_permission(
                session, auth.user_id, auth.organization_id, permission_code
            )
            if not has_perm:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{permission_code}' required",
                )
            return auth

        # API key path: key must have permission AND the associated user
        # must still hold it via current roles.
        if permission_code not in auth.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks permission '{permission_code}'",
            )
        if not auth.user_id:
            # Defensive: every API key has a created_by, but if it ever
            # arrives without one, refuse rather than silently allow.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key has no associated user",
            )
        user_has_it = await user_has_permission(
            session, auth.user_id, auth.organization_id, permission_code
        )
        if not user_has_it:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"API key's associated user no longer has permission "
                    f"'{permission_code}'"
                ),
            )
        return auth

    return check_permission


def require_feature_flag(flag_key: str):
    """
    Dependency factory to check if a feature flag is enabled for the user's organization.
    Returns 403 if the flag is disabled for the organization.
    Super admins bypass feature flag checks.

    Usage:
        @router.get("/endpoint")
        async def endpoint(
            current_user: Annotated[CurrentUser, Depends(require_feature_flag("my_feature"))]
        ):
            ...
    """

    async def check_feature_flag(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> CurrentUser:
        # Super admins bypass all feature flag checks
        if current_user.is_admin:
            return current_user

        # Check if user has feature_flags:bypass permission
        from src.crud.role_permission import user_has_permission

        has_bypass = await user_has_permission(
            session,
            current_user.id,
            current_user.organization_id,
            "feature_flags:bypass",
        )
        if has_bypass:
            return current_user

        # Check if feature flag is enabled for organization
        from src.crud.feature_flag import get_resolved_flags_for_organization

        flags = await get_resolved_flags_for_organization(
            session, current_user.organization_id
        )

        if not flags.get(flag_key, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature '{flag_key}' is not enabled for your organization",
            )

        return current_user

    return check_feature_flag
