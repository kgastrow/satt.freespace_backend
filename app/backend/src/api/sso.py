"""
SSO API endpoints for OAuth flow.

Handles SSO authorization initiation and callback processing with proper
account linking flows.
"""

from datetime import datetime, timedelta, timezone
import secrets
import traceback
from typing import Annotated, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.security import jwt_decode_options
from src.crud.organization import get_organization_by_slug
from src.crud.organization_sso_settings import get_organization_sso_settings
from src.crud.role import get_default_registration_roles
from src.crud.user import create_user, get_user_by_email, get_user_by_id
from src.crud.user_identity import (
    create as create_user_identity,
)
from src.crud.user_identity import (
    get_by_provider_user_id,
)
from src.crud.user_role import assign_role
from src.logger.logger import Logger
from src.models.user import CreatedVia
from src.serialisers.auth import (
    AccessTokenResponse,
    LoginResponseWith2FA,
    SSOLinkingRequiredResponse,
)
from src.services.auth_session import (
    SSO_TWO_FACTOR_CHALLENGE_ENABLED,
    issue_session_for_user,
)
from src.services.cache import cache_service
from src.services.sso.factory import SSOProviderFactory


# Allowlist of supported SSO providers for input validation
SUPPORTED_PROVIDERS = {"google"}

# Map provider names to CreatedVia enum values
PROVIDER_TO_CREATED_VIA = {
    "google": CreatedVia.GOOGLE,
}

router = APIRouter(prefix="/sso", tags=["sso"])


async def _consume_state_nonce(state_nonce: str, org_id: str) -> None:
    """Burn the single-use OAuth ``state`` nonce, failing CLOSED.

    This guard used to sit behind ``if cache_service._redis:`` inside a broad
    ``except Exception: Logger.warning(...)``. With Redis absent or erroring the
    replay protection silently vanished and a captured ``state`` stayed
    replayable for its full 10-minute JWT lifetime - i.e. CSRF protection
    evaporated in exactly the situation (an incident, a failover) where it
    matters most.

    The state nonce is the only thing tying this callback to a login the user
    actually started. If we cannot prove it is being spent for the first time we
    refuse and the user retries the SSO flow; the alternative is unlimited
    reuse.
    """
    redis = cache_service._redis
    if redis is None:
        Logger.error("SSO state nonce check unavailable: no Redis connection")
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable. Please try again.",
            detail_code="sso.state_verification_unavailable",
        )

    try:
        stored_org_id = await redis.getdel(f"sso_state:{state_nonce}")
    except Exception as exc:  # pragma: no cover - transport failure
        Logger.error(f"SSO state nonce check failed: {exc}")
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable. Please try again.",
            detail_code="sso.state_verification_unavailable",
        )

    if not stored_org_id:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State parameter already used or expired",
            detail_code="sso.state_replay",
        )

    if isinstance(stored_org_id, bytes):
        stored_org_id = stored_org_id.decode()
    if stored_org_id != org_id:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
            detail_code="sso.state_invalid",
        )


@router.get("/{provider}/authorize")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def initiate_sso_login(
    request: Request,
    provider: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    org_slug: str = Query(..., description="Organization slug"),
):
    """
    Initiate SSO login flow by generating OAuth authorization URL.

    Args:
        provider: SSO provider name (e.g., 'google')
        org_slug: Organization slug for tenant context
        session: Database session

    Returns:
        Authorization URL to redirect user to
    """
    Logger.debug(f"SSO authorize request for provider={provider}, org={org_slug}")

    # Get organization
    organization = await get_organization_by_slug(session, org_slug)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    if not organization.is_active:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not active",
            detail_code="auth.organization_not_active",
        )

    # Get SSO settings for the organization
    sso_settings = await get_organization_sso_settings(session, str(organization.id))
    if not sso_settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO not configured for this organization",
            detail_code="sso.provider_not_configured",
        )

    # Validate provider against allowlist before reflecting in error messages
    # SECURITY: Prevents user input from being reflected in responses
    if provider.lower() not in SUPPORTED_PROVIDERS:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or unsupported SSO provider",
            detail_code="sso.provider_not_supported",
        )

    # Check if provider is enabled for this organization
    if provider.lower() == "google":
        if not sso_settings.google_enabled:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Google SSO is not enabled for this organization",
                detail_code="sso.provider_not_configured",
            )

    # Get SSO provider instance
    try:
        sso_provider = SSOProviderFactory.get_provider(provider)
        if not sso_provider:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SSO provider is not configured on the server",
                detail_code="sso.provider_not_configured",
            )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )

    # Generate state parameter for CSRF protection
    # State encodes organization context for the callback
    state_nonce = secrets.token_urlsafe(32)
    state_data = {
        "state": state_nonce,
        "org_id": str(organization.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    encoded_state = jwt.encode(state_data, settings.JWT_SECRET, algorithm="HS256")

    # SECURITY: Store state in Redis for single-use validation (prevents replay attacks)
    # State can only be used once - will be deleted on callback
    try:
        if cache_service._redis:
            await cache_service._redis.setex(
                f"sso_state:{state_nonce}",
                600,  # 10 minutes TTL
                str(organization.id),
            )
    except Exception as e:
        Logger.warning(f"Failed to store SSO state in cache: {e}")

    # Determine redirect URI.
    #
    # The OAuth redirect_uri is where the PROVIDER sends the user's BROWSER, and
    # that lands on the SPA page /oauth/callback (app/frontend/src/router.tsx),
    # which then calls this API's GET /api/v1/sso/{provider}/callback with the
    # code. So the fallback is the FRONTEND origin + /oauth/callback - it is not
    # an API path. The previous fallback, "{PUBLIC_URL}/sso/{provider}/callback",
    # matched no route on either origin.
    #
    # In practice GOOGLE_REDIRECT_URI is still required, because the value must
    # byte-match a URI registered in Google Cloud Console; the fallback only
    # keeps an unconfigured deployment pointing somewhere real.
    redirect_uri = (
        settings.GOOGLE_REDIRECT_URI
        or f"{settings.PUBLIC_URL_FRONTEND.rstrip('/')}/oauth/callback"
    )

    # Get authorization URL
    auth_url = await sso_provider.get_authorization_url(
        state=encoded_state, redirect_uri=redirect_uri
    )

    return {"authorization_url": auth_url}


@router.get(
    "/{provider}/callback",
    response_model=Union[
        AccessTokenResponse, SSOLinkingRequiredResponse, LoginResponseWith2FA
    ],
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def handle_sso_callback(
    request: Request,
    response: Response,
    provider: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    code: str = Query(..., description="Authorization code from OAuth provider"),
    state: str = Query(..., description="State parameter for CSRF protection"),
):
    """
    Handle OAuth callback from SSO provider.

    This endpoint implements proper SSO login with account linking:
    1. Validates the state parameter (CSRF protection)
    2. Exchanges the authorization code for tokens
    3. Retrieves user info from the provider
    4. Checks for existing user identity by provider_user_id
    5. If identity exists: log in that user directly
    6. If no identity:
       - If no user with email exists: create new user + identity
       - If user exists with same provider origin: auto-link (legacy migration)
       - If user exists with different origin: return linking required response

    Args:
        provider: SSO provider name (e.g., 'google')
        code: Authorization code from OAuth provider
        state: CSRF protection state parameter
        session: Database session

    Returns:
        LoginResponse with JWT tokens, or SSOLinkingRequiredResponse if linking needed
    """
    Logger.debug(f"SSO callback for provider={provider}")

    # SECURITY: Validate provider against allowlist early
    provider_lower = provider.lower()
    if provider_lower not in SUPPORTED_PROVIDERS:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or unsupported SSO provider",
            detail_code="sso.provider_not_supported",
        )

    # Decode and validate state
    try:
        state_data = jwt.decode(
            state,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options=jwt_decode_options(),
        )
        org_id = state_data.get("org_id")
        state_nonce = state_data.get("state")
        if not org_id or not state_nonce:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid state parameter",
                detail_code="common.validation_error",
            )

        # SECURITY: Single-use state token validation (prevents replay attacks).
        # Fails CLOSED - see _consume_state_nonce.
        await _consume_state_nonce(state_nonce, org_id)

    except jwt.ExpiredSignatureError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State parameter expired",
            detail_code="auth.token_expired",
        )
    except jwt.InvalidTokenError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
            detail_code="auth.invalid_token",
        )

    # Get organization
    from src.crud.organization import get_organization_by_id

    organization = await get_organization_by_id(session, org_id)
    if not organization or not organization.is_active:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not active",
            detail_code="auth.organization_not_active",
        )

    # Get SSO provider instance
    try:
        sso_provider = SSOProviderFactory.get_provider(provider)
        if not sso_provider:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SSO provider is not configured on the server",
                detail_code="sso.provider_not_configured",
            )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )

    # Determine redirect URI. Must be byte-identical to the one sent at
    # /authorize, hence the same expression. See the comment there.
    redirect_uri = (
        settings.GOOGLE_REDIRECT_URI
        or f"{settings.PUBLIC_URL_FRONTEND.rstrip('/')}/oauth/callback"
    )

    try:
        # Exchange code for tokens
        tokens = await sso_provider.exchange_code_for_tokens(code, redirect_uri)
        access_token = tokens.get("access_token")

        if not access_token:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to obtain access token from provider",
                detail_code="sso.authentication_failed",
            )

        # Get user info from provider
        user_info = await sso_provider.get_user_info(access_token)
        email = user_info.get("email")
        # Google uses 'id' or 'sub' for the unique user ID
        provider_user_id = user_info.get("id") or user_info.get("sub")

        if not email:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by SSO provider",
                detail_code="sso.authentication_failed",
            )

        if not provider_user_id:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not provided by SSO provider",
                detail_code="sso.authentication_failed",
            )

        # Step 1: Check if user_identity exists for this provider + provider_user_id
        existing_identity = await get_by_provider_user_id(
            session, provider_lower, provider_user_id, org_id
        )

        if existing_identity:
            # Identity exists - log in that user directly (skip 2FA for SSO)
            user = await get_user_by_id(session, str(existing_identity.user_id), org_id)
            if not user:
                raise create_http_exception(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User account not found",
                    detail_code="sso.authentication_failed",
                )
            Logger.info(f"SSO login via existing identity: {email} in org {org_id}")
        else:
            # No identity - check if user with this email exists
            existing_user = await get_user_by_email(session, email, org_id)

            if not existing_user:
                # Create new user with created_via=provider and no password
                created_via = PROVIDER_TO_CREATED_VIA.get(
                    provider_lower, CreatedVia.EMAIL
                )
                user_data = {
                    "email": email,
                    "password": None,  # SSO users have no password
                    "email_verified": True,  # SSO providers verify email
                    "created_via": created_via,
                }
                user = await create_user(session, user_data, org_id)

                # Create the identity record
                await create_user_identity(
                    session,
                    user_id=str(user.id),
                    provider=provider_lower,
                    provider_user_id=provider_user_id,
                    organization_id=org_id,
                    provider_email=email,
                )

                # Assign default roles to the new user
                default_roles = await get_default_registration_roles(session)
                for role in default_roles:
                    try:
                        await assign_role(
                            session=session,
                            request={"user_id": str(user.id), "role_id": str(role.id)},
                            assigned_by_user_id=str(user.id),
                            organization_id=org_id,
                        )
                    except ValueError:
                        pass  # Skip if role assignment fails (e.g., already assigned)

                Logger.info(
                    f"SSO registration: created new user {email} in org {org_id}"
                )
            else:
                # User exists - check if we should auto-link or require confirmation
                user = existing_user
                expected_created_via = PROVIDER_TO_CREATED_VIA.get(provider_lower)

                if user.created_via == expected_created_via:
                    # Legacy user created via same provider but no identity record
                    # Auto-link them (migration case)
                    await create_user_identity(
                        session,
                        user_id=str(user.id),
                        provider=provider_lower,
                        provider_user_id=provider_user_id,
                        organization_id=org_id,
                        provider_email=email,
                    )
                    Logger.info(
                        f"SSO login: auto-linked legacy user {email} in org {org_id}"
                    )
                else:
                    # Different origin - require linking confirmation
                    # Check email verification requirements
                    if not user.email_verified:
                        raise create_http_exception(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Verify your email before linking SSO",
                            detail_code="sso.email_not_verified",
                        )

                    # Generate a link token for the frontend to use
                    link_nonce = secrets.token_urlsafe(32)
                    link_token = jwt.encode(
                        {
                            "user_id": str(user.id),
                            "provider": provider_lower,
                            "provider_user_id": provider_user_id,
                            "provider_email": email,
                            "org_id": org_id,
                            "nonce": link_nonce,
                            "purpose": "sso_link",
                            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                        },
                        settings.JWT_SECRET,
                        algorithm="HS256",
                    )

                    # Store nonce in Redis for single-use validation
                    try:
                        if cache_service._redis:
                            await cache_service._redis.setex(
                                f"sso_link:{link_nonce}",
                                300,  # 5 minutes TTL
                                str(user.id),
                            )
                    except Exception as e:
                        Logger.warning(f"Failed to store link token in cache: {e}")

                    Logger.info(f"SSO linking required for {email} in org {org_id}")
                    return SSOLinkingRequiredResponse(
                        requires_linking=True,
                        link_token=link_token,
                        email=email,
                        provider=provider_lower,
                    )

        # SECURITY: the same gate /auth/login uses. Until this existed the SSO
        # callback applied NO suspension check and NO second factor, so "Sign in
        # with Google" was a working password-less bypass of both - a suspended
        # employee simply logged back in.
        grant = await issue_session_for_user(
            session,
            user=user,
            organization=organization,
            request=request,
            response=response,
            auth_provider=provider_lower,
            # See SSO_TWO_FACTOR_CHALLENGE_ENABLED (True): SSO does NOT skip
            # local 2FA. A 2FA-enrolled account signing in through a provider
            # gets the same requires_2fa challenge as /auth/login, and the
            # frontend OAuth callback page handles that response.
            allow_two_factor_challenge=SSO_TWO_FACTOR_CHALLENGE_ENABLED,
            enforce_two_factor=SSO_TWO_FACTOR_CHALLENGE_ENABLED,
        )

        if grant.requires_2fa:
            assert grant.two_factor_token is not None
            Logger.info(f"SSO login requires 2FA: provider={provider}, org={org_id}")
            return LoginResponseWith2FA(
                requires_2fa=True,
                two_factor_token=grant.two_factor_token,
            )

        Logger.info(
            f"SSO Login successful: provider={provider}, org={organization.slug}"
        )

        assert grant.access_token is not None
        return AccessTokenResponse(access_token=grant.access_token)

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"SSO callback error: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO authentication failed. Please try again.",
            detail_code="sso.authentication_failed",
        )
