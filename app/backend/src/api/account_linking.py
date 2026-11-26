"""
Account Linking API endpoints.

Handles SSO account linking confirmation flow.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session, get_token_from_header, resolve_current_user
from src.core.client_ip import get_client_ip
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.security import jwt_decode_options, verify_password
from src.crud.organization import get_organization_by_id
from src.crud.user import get_user_by_id
from src.crud.user_identity import (
    create as create_user_identity,
)
from src.crud.user_identity import (
    get_by_provider_user_id,
)
from src.logger.logger import Logger
from src.models.user import User
from src.serialisers.auth import AccessTokenResponse, ConfirmLinkRequest
from src.services.auth_session import issue_session_for_user
from src.services.brute_force_detector import brute_force_detector
from src.services.cache import cache_service


router = APIRouter(prefix="/auth/sso", tags=["auth", "sso"])


# ── Brute-force limits for the password proof on POST /auth/sso/link ──
#
# ``/auth/login`` pairs RATE_LIMIT_LOGIN with a per-IP block and a per-account
# lockout. This endpoint had neither: only RATE_LIMIT_DEFAULT (100/min) stood
# between an attacker and ``verify_password``, and because the single-use nonce
# is deliberately burned only AFTER the proof succeeds (so a typo does not cost
# the user their link token) a wrong guess was free. That is ~500 guesses per
# 5-minute link token, with a fresh token one OAuth round-trip away.
#
# Two counters, both fed to the shared ``brute_force_detector``:
#
#   * per link token (nonce) - caps guesses against ONE token. The window is
#     longer than the token's own 5-minute TTL so the counter always outlives
#     the thing it guards.
#   * per target account - caps guesses across successive tokens, which is what
#     closes the "just start another OAuth flow" refresh.
#
# ``brute_force_detector`` keys everything by an opaque string (its parameter is
# named ``ip`` because IPs were the first thing it counted); these namespaced
# keys cannot collide with a real address.
LINK_PROOF_TOKEN_MAX_ATTEMPTS = 5
LINK_PROOF_TOKEN_WINDOW_SECONDS = 900  # > the 5-minute link token TTL
LINK_PROOF_ACCOUNT_MAX_ATTEMPTS = 10
LINK_PROOF_ACCOUNT_WINDOW_SECONDS = 900


def _link_token_attempt_key(nonce: str) -> str:
    return f"sso_link_token:{nonce}"


def _link_account_attempt_key(organization_id: str, user_id: str) -> str:
    return f"sso_link_account:{organization_id}:{user_id}"


async def _assert_link_password_attempts_remaining(
    *,
    nonce: str,
    organization_id: str,
    user_id: str,
    client_ip: str,
) -> None:
    """Refuse a password guess once this token, account or IP is over its cap.

    Deliberately scoped to the PASSWORD proof only (see the call site): the
    bearer-session proof is not guessable, and gating it too would hand an
    attacker a denial of service. Anyone who can register a provider account on
    the victim's address can mint link tokens for them and burn the account
    counter; because the counter never touches the session path the victim can
    still sign in normally and link from inside the app, and it never touches
    ``/auth/login`` either - it is a cap on linking, not an account lockout.

    Hitting the cap refuses further attempts rather than destroying anything:
    the link token is not burned, the account is not locked, and the counters
    age out of their sliding window (and are cleared outright by a correct
    password).
    """
    if await brute_force_detector.is_blocked(client_ip):
        Logger.warning("SSO link proof refused: IP blocked")
        raise create_http_exception(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later.",
            detail_code="auth.ip_blocked",
        )

    token_attempts = await brute_force_detector.get_failure_count(
        _link_token_attempt_key(nonce),
        window_seconds=LINK_PROOF_TOKEN_WINDOW_SECONDS,
    )
    account_attempts = await brute_force_detector.get_failure_count(
        _link_account_attempt_key(organization_id, user_id),
        window_seconds=LINK_PROOF_ACCOUNT_WINDOW_SECONDS,
    )

    if (
        token_attempts >= LINK_PROOF_TOKEN_MAX_ATTEMPTS
        or account_attempts >= LINK_PROOF_ACCOUNT_MAX_ATTEMPTS
    ):
        Logger.warning(
            f"SSO link proof refused: too many failed attempts "
            f"(token={token_attempts}, account={account_attempts}, "
            f"user_id={user_id})"
        )
        raise create_http_exception(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many incorrect passwords for this link request. "
                "Please sign in again to start a new one."
            ),
            detail_code="sso.link_attempts_exceeded",
        )


async def _record_link_password_failure(
    *,
    nonce: str,
    organization_id: str,
    user_id: str,
    client_ip: str,
) -> None:
    """Count one rejected password guess against token, account and IP."""
    await brute_force_detector.record_failure(
        _link_token_attempt_key(nonce),
        "sso_link",
        threshold=LINK_PROOF_TOKEN_MAX_ATTEMPTS,
        window_seconds=LINK_PROOF_TOKEN_WINDOW_SECONDS,
    )
    await brute_force_detector.record_failure(
        _link_account_attempt_key(organization_id, user_id),
        "sso_link",
        threshold=LINK_PROOF_ACCOUNT_MAX_ATTEMPTS,
        window_seconds=LINK_PROOF_ACCOUNT_WINDOW_SECONDS,
    )
    # Same IP convention as /auth/login: count, and block the address outright
    # once it trips the shared threshold.
    if await brute_force_detector.record_failure(client_ip, "sso_link"):
        await brute_force_detector.block_ip(client_ip, reason="brute_force_sso_link")


async def _clear_link_password_failures(
    *,
    nonce: str,
    organization_id: str,
    user_id: str,
    client_ip: str,
) -> None:
    """Reset the counters once the password proof succeeds."""
    await brute_force_detector.clear_failures(_link_token_attempt_key(nonce))
    await brute_force_detector.clear_failures(
        _link_account_attempt_key(organization_id, user_id)
    )
    await brute_force_detector.clear_failures(client_ip)


def _assert_link_nonce_store_available() -> None:
    """Refuse before ``verify_password`` runs if the nonce store is missing.

    ``_consume_link_nonce`` already fails closed with a 503, but it runs after
    the proof, so with Redis down the endpoint still answered "wrong password"
    vs "correct password" - an oracle, at the exact moment the throttle backing
    store is also gone. Checking here means a Redis-less deployment refuses the
    request outright instead of grading the guess. The status and detail_code
    are the same ones ``_consume_link_nonce`` would have raised a moment later.
    """
    if cache_service._redis is None:
        Logger.error("SSO link nonce check unavailable: no Redis connection")
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account linking is temporarily unavailable. Please try again.",
            detail_code="sso.link_verification_unavailable",
        )


async def _consume_link_nonce(nonce: str, user_id: str) -> None:
    """Burn the single-use link nonce, failing CLOSED.

    This guard used to sit behind ``if cache_service._redis:`` inside a broad
    ``except Exception: Logger.warning(...)``, so with Redis absent or erroring
    it silently allowed the link token to be replayed for its full 5-minute TTL
    - the exact situation (an incident, a failover) where replay protection
    matters most.

    A link token is a capability to attach a new sign-in method to somebody's
    account. If we cannot prove it is being spent for the first time we refuse
    and the user retries the SSO flow; the alternative is unlimited reuse.
    """
    redis = cache_service._redis
    if redis is None:
        Logger.error("SSO link nonce check unavailable: no Redis connection")
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account linking is temporarily unavailable. Please try again.",
            detail_code="sso.link_verification_unavailable",
        )

    try:
        stored_user_id = await redis.getdel(f"sso_link:{nonce}")
    except Exception as exc:  # pragma: no cover - transport failure
        Logger.error(f"SSO link nonce check failed: {exc}")
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account linking is temporarily unavailable. Please try again.",
            detail_code="sso.link_verification_unavailable",
        )

    if not stored_user_id:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link token already used or expired",
            detail_code="sso.link_token_expired",
        )

    if isinstance(stored_user_id, bytes):
        stored_user_id = stored_user_id.decode()
    if stored_user_id != user_id:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid link token",
            detail_code="sso.link_token_invalid",
        )


async def _assert_link_proof(
    session: AsyncSession,
    *,
    user: User,
    organization_id: str,
    password: Optional[str],
    authorization: Optional[str],
    nonce: str,
    client_ip: str,
) -> bool:
    """Require proof that the caller controls the account being linked.

    The link token alone proved only that somebody completed an OAuth flow for
    an address that happens to match an existing account. Confirmation was a
    frontend click-through, so anyone who could create a provider account on a
    victim's email address got a full session on the victim's account.

    Two proofs are accepted, mirroring the two ways the frontend reaches this
    endpoint:

    1. An authenticated session for the SAME user in the SAME organization
       (they are signed in and adding a provider).
    2. The existing account's password, re-entered (the signed-out SSO callback
       path).

    An SSO-only account has no password, so it cannot satisfy (2) and must
    already be signed in. That is correct - such an account has no existing
    credential the caller could be asked to prove.

    The password branch is brute-force limited (per link token, per account and
    per IP) because it is the only guessable one; see
    ``_assert_link_password_attempts_remaining``.

    Returns:
        True when the proof was an existing authenticated session. That session
        already passed every login gate (including 2FA), so the caller may treat
        the second factor as satisfied.

    Raises:
        HTTPException: 403 ``auth.invalid_password`` when a password was
            supplied and rejected, 401 ``sso.link_proof_required`` when no
            acceptable proof was supplied at all, 429 when the attempt cap for
            this token/account/IP has been reached.
    """
    if authorization:
        try:
            token = get_token_from_header(authorization)
            current_user = await resolve_current_user(token, session)
        except HTTPException:
            current_user = None
        if (
            current_user is not None
            and current_user.id == str(user.id)
            and current_user.organization_id == organization_id
        ):
            return True

    if password and user.password:
        # Everything below grades a guess, so nothing below may run unthrottled
        # or without the store that both the throttle and the replay guard need.
        _assert_link_nonce_store_available()
        await _assert_link_password_attempts_remaining(
            nonce=nonce,
            organization_id=organization_id,
            user_id=str(user.id),
            client_ip=client_ip,
        )

        if verify_password(password, user.password):
            await _clear_link_password_failures(
                nonce=nonce,
                organization_id=organization_id,
                user_id=str(user.id),
                client_ip=client_ip,
            )
            return False

        await _record_link_password_failure(
            nonce=nonce,
            organization_id=organization_id,
            user_id=str(user.id),
            client_ip=client_ip,
        )
        # 403, not 401: `sso.link_proof_required` below is also a 401, so a
        # status-only client could not tell "your proof was rejected" from "you
        # supplied no proof" - which is how the frontend's dead detail_code
        # matching went unnoticed. "Authenticated but refused" is 403's job.
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid password",
            detail_code="auth.invalid_password",
        )

    raise create_http_exception(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Confirm this link by signing in to the existing account, "
            "or re-enter its password."
        ),
        detail_code="sso.link_proof_required",
    )


@router.post("/link", response_model=AccessTokenResponse)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def confirm_account_link(
    request: Request,
    response: Response,
    link_data: ConfirmLinkRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[Optional[str], Header()] = None,
):
    """
    Confirm SSO account linking.

    Called when a user confirms they want to link their existing account to an
    SSO provider identity. Requires proof of the existing account (an
    authenticated session for that same user, or its password) on top of the
    single-use link token from the SSO callback.

    Args:
        link_data: The link_token from the SSO callback, plus an optional
            `password` when the caller is not signed in.
        session: Database session

    Returns:
        AccessTokenResponse with the JWT access token (refresh token in cookie)
    """
    Logger.debug("Account linking confirmation request")

    # Decode and validate the link token
    try:
        payload = jwt.decode(
            link_data.link_token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options=jwt_decode_options(),
        )

        # Validate token purpose
        if payload.get("purpose") != "sso_link":
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid link token",
                detail_code="sso.link_token_invalid",
            )

        user_id = payload.get("user_id")
        provider = payload.get("provider")
        provider_user_id = payload.get("provider_user_id")
        provider_email = payload.get("provider_email")
        org_id = payload.get("org_id")
        nonce = payload.get("nonce")

        if not all([user_id, provider, provider_user_id, org_id, nonce]):
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid link token",
                detail_code="sso.link_token_invalid",
            )

    except jwt.ExpiredSignatureError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link token has expired. Please try signing in again.",
            detail_code="sso.link_token_expired",
        )
    except jwt.InvalidTokenError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid link token",
            detail_code="sso.link_token_invalid",
        )

    # Get the user. Scoped by org_id from the token, so a link token minted for
    # one tenant can never resolve a user in another.
    user = await get_user_by_id(session, user_id, org_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account not found",
            detail_code="user.not_found",
        )

    # Proof of the EXISTING account, before anything is mutated or minted.
    proved_by_session = await _assert_link_proof(
        session,
        user=user,
        organization_id=str(org_id),
        password=link_data.password,
        authorization=authorization,
        nonce=nonce,
        client_ip=get_client_ip(request) or "unknown",
    )

    # SECURITY: single-use token validation (prevents replay attacks). Burned
    # only once the proof above has passed, so a failed password attempt does
    # not consume the user's link token.
    await _consume_link_nonce(nonce, user_id)

    organization = await get_organization_by_id(session, org_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account not found",
            detail_code="user.not_found",
        )

    # Check if identity already exists (race condition check)
    existing_identity = await get_by_provider_user_id(
        session, provider, provider_user_id, org_id
    )
    if existing_identity:
        if str(existing_identity.user_id) != user_id:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This SSO account is already linked to a different user",
                detail_code="sso.authentication_failed",
            )
        # Identity already exists for this user - just proceed with login
        Logger.info(f"Account linking: identity already exists for {user.email}")
    else:
        # Create the identity record
        await create_user_identity(
            session,
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            organization_id=org_id,
            provider_email=provider_email,
        )
        Logger.info(f"Account linked: {user.email} to {provider} in org {org_id}")

    # Same gate as /auth/login: organization active, suspension, 2FA. A password
    # re-auth here is a login, so it must not be a way to skip them.
    grant = await issue_session_for_user(
        session,
        user=user,
        organization=organization,
        request=request,
        response=response,
        auth_provider=provider,
        # This page has no TOTP field, so a 2FA-enrolled account that proved
        # itself with a password is told to sign in through the normal flow
        # instead of being handed a session. A caller who proved itself with an
        # existing session has already cleared 2FA, so it is not asked twice.
        allow_two_factor_challenge=False,
        two_factor_satisfied=proved_by_session,
    )

    assert grant.access_token is not None
    return AccessTokenResponse(access_token=grant.access_token)
