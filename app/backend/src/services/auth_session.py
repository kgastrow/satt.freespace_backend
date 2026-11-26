"""The single gate every path that mints a signed-in session must pass through.

Before this module existed the token-minting sites were independent and each
carried its own (or no) set of checks:

* ``POST /auth/login`` blocked suspended accounts and challenged 2FA.
* ``POST /auth/verify-2fa`` blocked suspended accounts.
* ``GET /sso/{provider}/callback`` checked **nothing** but ``organization.is_active``
  -- no suspension check and no second factor. "Sign in with Google" was
  therefore a working password-less bypass of both account suspension and the
  organization's 2FA policy: a suspended employee simply logged back in.
* ``POST /auth/sso/link`` minted a full session with the same gaps.
* ``POST /user-otp/verify-email`` checked **nothing at all** and minted a full
  session with a refresh cookie. Combined with the unauthenticated
  ``POST /user-otp/send-verification-email`` (which mails a 6-digit code to any
  account, verified or not, suspended or not) that was a complete
  password-less, second-factor-less login for anyone who could read the
  mailbox.

Every endpoint that turns "we have decided who this user is" into "here is a
session" now routes through :func:`issue_session_for_user`. The complete list,
which is exactly what ``tests/unit_tests/test_session_mint_call_sites.py``
enforces:

* ``POST /auth/login``                  -- :mod:`src.api.auth`
* ``POST /auth/verify-2fa``             -- :mod:`src.api.auth`
  (``two_factor_satisfied=True``; it checked the factor itself)
* ``GET  /sso/{provider}/callback``     -- :mod:`src.api.sso`
* ``POST /auth/sso/link``               -- :mod:`src.api.account_linking`
* ``POST /user-otp/verify-email``       -- :mod:`src.api.user_otp`
  (``allow_two_factor_challenge=False``: no challenge is presentable on this
  path, so an enrolled user is refused rather than let past the second factor)

**Adding a new endpoint that signs a user in? It goes through this helper and
into the list above.** Do not call ``create_access_token`` /
``create_refresh_token_with_metadata`` / ``set_refresh_cookie`` from
``src/api/`` -- ``test_session_mint_call_sites.py`` fails on any such call that
is not on its small, reasoned allowlist. That guard exists because the SSO
hardening pass rewrote every login path it knew about and still left
``verify-email`` behind: an unenumerated hole survives a review, an enumerated
one does not.

Two endpoints legitimately mint an access token WITHOUT this helper, and both
are on that allowlist with their reasons:

* ``POST /auth/refresh`` -- re-mints an access token from a refresh token that
  was itself issued through this gate; it re-checks organization-active and
  suspension inline and issues no new refresh token.
* ``POST /admin/impersonate/end`` -- restores the admin's pre-impersonation
  access token (no refresh token, no cookie); it re-checks super-admin,
  organization-active and suspension inline. The second factor was satisfied
  when that admin originally logged in.

A gate added here is therefore a gate on every login path, and a fork that adds
a new login path cannot silently skip one.

Gates applied, in order (the order matters -- suspension must be reported ahead
of the second factor so 2FA is never reachable by a suspended account):

1. organization active     -> 403 ``auth.organization_not_active``
2. account not suspended   -> 403 ``user.suspended``
3. email verified          -> 403 ``auth.email_not_verified`` (opt-in)
4. user enrolled in 2FA    -> 2FA challenge, NOT a session
                              (or 403 ``auth.2fa_required`` on a path that
                              cannot present a challenge)
5. org mandatory-2FA policy -> reported on the grant (see :class:`SessionGrant`)

Callers keep their own path-specific concerns (brute-force counters, identity
creation, audit logging); this helper owns only the gate and the mint.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response, status
import jwt

from src.core.config import settings
from src.core.cookies import set_refresh_cookie
from src.core.exceptions import create_http_exception
from src.core.security import create_access_token
from src.crud.refresh_token import create_refresh_token_with_metadata
from src.models.organization import Organization
from src.models.user import SuspensionStatus, User
from src.services.audit import get_client_ip, get_user_agent


# Purpose claim on the short-lived token handed back when a second factor is
# still outstanding. Consumed by ``POST /auth/verify-2fa``.
TWO_FACTOR_CHALLENGE_PURPOSE = "2fa_verification"
TWO_FACTOR_CHALLENGE_EXPIRE_MINUTES = 5

# SSO + 2FA is wired end to end.
#
# The SSO callback hands back the same ``LoginResponseWith2FA`` shape
# (``{"requires_2fa": true, "two_factor_token": "<jwt>"}``) that ``/auth/login``
# returns, and the challenge is completed by the same ``POST /auth/verify-2fa``
# round-trip. On the frontend the pieces are:
#
# * ``types/sso.ts``            -- ``SSOCallback2FARequiredResponse`` in the
#                                 ``SSOCallbackResponse`` union plus the
#                                 ``isSSOTwoFactorRequired`` guard.
# * ``pages/OAuthCallback.tsx`` -- checks that guard BEFORE the ``access_token``
#                                 branch, dispatches ``set2FARequired`` and
#                                 navigates to ``/login``.
# * ``features/auth/authSlice.ts`` -- the ``handleSSOCallback`` matcher tells the
#                                 three fulfilled outcomes apart (session /
#                                 challenge / linking required).
# * ``/login`` renders the shared ``TwoFactorVerification`` screen off
#   ``state.auth.twoFactor``.
#
# A fork that replaces the OAuth callback page MUST keep all of that working:
# a ``requires_2fa`` response carries NO access token, so a page that assumes a
# session and stores ``result.access_token`` will sign the user straight back
# out. For an SSO-ONLY account (no password) there is no fallback login path, so
# that mistake is an unrecoverable lockout -- which is why this constant existed
# in the first place. Do not turn it off to "fix" such a page: turning it off
# silently lets a 2FA-enrolled user sign in through SSO with no second factor.
SSO_TWO_FACTOR_CHALLENGE_ENABLED = True


@dataclass(frozen=True)
class SessionGrant:
    """What a login path got back from the gate.

    Exactly one of ``access_token`` / ``two_factor_token`` is set.
    """

    access_token: Optional[str] = None
    two_factor_token: Optional[str] = None
    requires_2fa: bool = False
    # True when the org mandates 2FA, the grace period has run out and this user
    # has still not enrolled. The session is issued anyway -- refusing it would
    # leave the user unable to reach the very endpoints that let them comply --
    # and the caller surfaces the flag so the frontend can force the setup
    # screen.
    two_factor_setup_required: bool = False
    # True when the org's mandatory policy applies to this user at all (in grace
    # or past it) -- drives the frontend's warn-vs-block banner.
    enforcement_active: bool = False


def _mint_two_factor_challenge(user_id: str, organization_id: str) -> str:
    """Mint the short-lived interstitial token consumed by /auth/verify-2fa."""
    return jwt.encode(
        {
            "user_id": user_id,
            "organization_id": organization_id,
            "purpose": TWO_FACTOR_CHALLENGE_PURPOSE,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=TWO_FACTOR_CHALLENGE_EXPIRE_MINUTES),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


async def evaluate_two_factor_requirement(
    session, user_id: str, organization_id: str
) -> tuple[bool, bool, bool]:
    """Resolve the 2FA position for a user about to be signed in.

    Returns ``(user_enrolled, enforcement_active, setup_required)`` where:

    - ``user_enrolled``      -- the user has an enabled 2FA record.
    - ``enforcement_active`` -- the org policy is ``mandatory`` (and 2FA is
      allowed), so this user is expected to enrol.
    - ``setup_required``     -- enforcement is active, the user has not enrolled
      and the grace period that started at ``enforcement_start_time`` has run
      out.
    """
    from src.crud import organization_two_factor_settings as org_2fa_crud
    from src.crud.user_two_factor import get_by_user_id
    from src.models.organization_two_factor_settings import TwoFactorPolicy

    user_2fa = await get_by_user_id(session, user_id, organization_id)
    if user_2fa and user_2fa.is_enabled:
        return True, False, False

    org_settings = await org_2fa_crud.get_by_organization_id(session, organization_id)
    if not org_settings or not org_settings.two_factor_allowed:
        return False, False, False
    if org_settings.two_factor_policy != TwoFactorPolicy.MANDATORY.value:
        return False, False, False

    start = org_settings.enforcement_start_time
    if start is None:
        # Mandatory but never switched on: the grace clock has not started, so
        # there is nothing to block on yet.
        return False, True, False

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    deadline = start + timedelta(days=org_settings.grace_period_days)
    return False, True, datetime.now(timezone.utc) >= deadline


async def issue_session_for_user(
    session,
    *,
    user: User,
    organization: Organization,
    request: Request,
    response: Optional[Response] = None,
    auth_provider: str = "email",
    require_email_verified: bool = False,
    allow_two_factor_challenge: bool = True,
    enforce_two_factor: bool = True,
    two_factor_satisfied: bool = False,
) -> SessionGrant:
    """Apply every login gate, then mint the session (or the 2FA challenge).

    Args:
        session: Database session.
        user: The already-authenticated user (the caller proved identity).
        organization: The org the session is scoped to.
        request: Used for the session's IP / user-agent metadata.
        response: When given and a full session is minted, the refresh cookie is
            set on it. Omit only if the caller sets the cookie itself.
        auth_provider: Recorded on the refresh token ("email", "google", ...).
        require_email_verified: Off by default because ``get_current_user``
            already refuses unverified accounts on every protected endpoint;
            turn it on for a path that wants the refusal at login time.
        allow_two_factor_challenge: Off for paths that cannot present a TOTP
            challenge to the user. Such a path REFUSES an enrolled user
            (``auth.2fa_required``) rather than skipping their second factor.
        enforce_two_factor: Escape hatch for a path that cannot yet challenge
            AND must not refuse (see ``SSO_TWO_FACTOR_CHALLENGE_ENABLED``).
            Setting this False knowingly skips the second factor -- never set it
            on a new path.
        two_factor_satisfied: On only for callers that have already verified the
            second factor themselves (``/auth/verify-2fa``), or that were handed
            an existing fully-gated session as proof.

    Raises:
        HTTPException: on any failed gate, with the same ``detail_code`` the
            frontend already handles from ``/auth/login``.
    """
    organization_id = str(organization.id)
    user_id = str(user.id)

    if not organization.is_active:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is not active",
            detail_code="auth.organization_not_active",
        )

    if user.suspension_status == SuspensionStatus.SUSPENDED:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended. Please contact your administrator.",
            detail_code="user.suspended",
        )

    if require_email_verified and not user.email_verified:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before signing in.",
            detail_code="auth.email_not_verified",
        )

    user_enrolled, enforcement_active, setup_required = (
        await evaluate_two_factor_requirement(session, user_id, organization_id)
    )

    if user_enrolled and not two_factor_satisfied and enforce_two_factor:
        if not allow_two_factor_challenge:
            # No way to collect the code on this path, so the only safe answer
            # is "finish signing in where the challenge can be presented".
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "This account uses two-factor authentication. "
                    "Please sign in with your password to continue."
                ),
                detail_code="auth.2fa_required",
            )
        return SessionGrant(
            two_factor_token=_mint_two_factor_challenge(user_id, organization_id),
            requires_2fa=True,
        )

    access_token = create_access_token(
        user_id=user_id,
        organization_id=organization_id,
    )
    refresh_token = await create_refresh_token_with_metadata(
        session=session,
        user_id=user_id,
        organization_id=organization_id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        auth_provider=auth_provider,
    )
    if response is not None:
        set_refresh_cookie(response, refresh_token)

    return SessionGrant(
        access_token=access_token,
        two_factor_setup_required=setup_required,
        enforcement_active=enforcement_active,
    )
