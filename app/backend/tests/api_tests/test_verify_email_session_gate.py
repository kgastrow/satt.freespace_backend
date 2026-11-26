"""Security tests for the ``POST /user-otp/verify-email`` login gate.

``verify-email`` is a login path: it returns an access token and sets the
refresh cookie. It used to mint both by hand -- ``create_access_token`` +
``create_refresh_token_with_metadata`` + ``set_refresh_cookie`` -- with no
organization check, no suspension check and no second factor.

Reachable end to end without any authentication:

1. ``POST /user-otp/send-verification-email {email, organization_slug}`` mails a
   6-digit OTP to ANY user in the org, verified or not, suspended or not.
2. ``POST /user-otp/verify-email {email, otp_code, organization_slug}`` returned
   ``200 {access_token}`` plus the refresh cookie.

So a suspended employee signed straight back in, and a 2FA-enrolled account was
fully compromised by read access to the mailbox alone -- the two exact holes the
SSO work closed on the SSO path and left open here. The endpoint now routes
through ``src.services.auth_session.issue_session_for_user`` like every other
login path.
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
import pytest

from src.core.security import hash_password
from src.models.organization import Organization
from src.models.user import SuspensionStatus, User
from src.models.user_otp import UserOTP
from src.models.user_two_factor import UserTwoFactor


OTP_CODE = "135790"


async def _issue_otp(async_session, user, code: str = OTP_CODE) -> None:
    """Give ``user`` a live, unused OTP."""
    async_session.add(
        UserOTP(
            user_id=user.id,
            organization_id=user.organization_id,
            otp_code=code,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=False,
        )
    )
    await async_session.commit()


async def _verify_email(
    client: AsyncClient, email: str, org_slug: str, code: str = OTP_CODE
):
    return await client.post(
        "/api/v1/user-otp/verify-email",
        json={
            "email": email,
            "otp_code": code,
            "organization_slug": org_slug,
        },
    )


def _detail_code(response) -> str:
    body = response.json()
    return body.get("detail_code", "")


# ============================================================================
# 1. Suspension
# ============================================================================


@pytest.mark.asyncio
async def test_verify_email_rejects_suspended_user(
    client: AsyncClient, async_session, test_organization
):
    """A suspended account must not get a session out of email verification."""
    user = User(
        email="suspended_verify@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
        suspension_status=SuspensionStatus.SUSPENDED,
    )
    async_session.add(user)
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, test_organization.slug)

    assert response.status_code == 403, response.text
    assert _detail_code(response) == "user.suspended"
    assert "access_token" not in response.json()
    assert "refresh_token" not in response.cookies


@pytest.mark.asyncio
async def test_verify_email_still_marks_suspended_user_verified(
    client: AsyncClient, async_session, test_organization
):
    """Refusing the session must not un-verify the address.

    The OTP was correct, so the address really is proven. Withholding the
    session is the security decision; throwing away the proof would just make
    the user re-run the flow after being unsuspended.
    """
    user = User(
        email="suspended_verified@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
        suspension_status=SuspensionStatus.SUSPENDED,
    )
    async_session.add(user)
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, test_organization.slug)
    assert response.status_code == 403

    await async_session.refresh(user)
    assert user.email_verified is True


# ============================================================================
# 2. Inactive organization
# ============================================================================


@pytest.mark.asyncio
async def test_verify_email_rejects_inactive_organization(
    client: AsyncClient, async_session
):
    """A deactivated organization must not hand out sessions."""
    org = Organization(name="Dormant Org", slug="dormant-org", is_active=False)
    async_session.add(org)
    await async_session.commit()

    user = User(
        email="inactive_org@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=org.id,
    )
    async_session.add(user)
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, org.slug)

    assert response.status_code == 403, response.text
    assert _detail_code(response) == "auth.organization_not_active"
    assert "access_token" not in response.json()


# ============================================================================
# 3. Second factor
# ============================================================================


@pytest.mark.asyncio
async def test_verify_email_refuses_2fa_enrolled_user(
    client: AsyncClient, async_session, test_organization
):
    """A 2FA-enrolled user must NOT be signed in by mailbox access alone.

    This endpoint cannot present a TOTP challenge (bare AccessTokenResponse,
    and the frontend caller stores ``access_token`` unconditionally), so the
    enrolled user is refused and sent to the normal login flow. What must never
    happen is a bare session: that would make the second factor worthless for
    anyone who can read the user's email.
    """
    user = User(
        email="enrolled_verify@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    async_session.add(
        UserTwoFactor(
            user_id=user.id,
            organization_id=test_organization.id,
            secret="JBSWY3DPEHPK3PXP",
            is_enabled=True,
            verified_at=datetime.now(timezone.utc),
        )
    )
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, test_organization.slug)

    assert response.status_code == 403, response.text
    assert _detail_code(response) == "auth.2fa_required"
    body = response.json()
    assert "access_token" not in body
    # Not a challenge either -- there is nowhere on this path to complete one.
    assert "two_factor_token" not in body
    assert "refresh_token" not in response.cookies


@pytest.mark.asyncio
async def test_verify_email_allows_user_with_disabled_2fa_record(
    client: AsyncClient, async_session, test_organization
):
    """Control: a half-finished 2FA setup is not enrolment and must not block."""
    user = User(
        email="unenrolled_verify@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()

    async_session.add(
        UserTwoFactor(
            user_id=user.id,
            organization_id=test_organization.id,
            secret="JBSWY3DPEHPK3PXP",
            is_enabled=False,
        )
    )
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, test_organization.slug)

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


# ============================================================================
# 4. Happy path (must not regress)
# ============================================================================


@pytest.mark.asyncio
async def test_verify_email_happy_path_still_signs_in(
    client: AsyncClient, async_session, test_organization
):
    """An ordinary unverified user still verifies and is logged in."""
    user = User(
        email="normal_verify@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, test_organization.slug)

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    # The refresh cookie is still set -- the gate mints it, we just do not.
    assert "refresh_token" in response.cookies

    await async_session.refresh(user)
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_verify_email_gate_runs_after_the_address_is_verified(
    client: AsyncClient, async_session, test_organization
):
    """The email-verified gate must not reject the user it just verified.

    ``issue_session_for_user`` is called with ``require_email_verified=True``,
    which is only safe because the update lands and commits first. If that
    ordering is ever swapped, this test fails with
    ``auth.email_not_verified``.
    """
    user = User(
        email="ordering_verify@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await _issue_otp(async_session, user)

    response = await _verify_email(client, user.email, test_organization.slug)

    assert _detail_code(response) != "auth.email_not_verified"
    assert response.status_code == 200, response.text


# ============================================================================
# 5. Tenant isolation
# ============================================================================


@pytest.mark.asyncio
async def test_verify_email_is_tenant_scoped(
    client: AsyncClient, async_session, test_organization, second_organization
):
    """An OTP issued in one org must not verify a same-email user in another.

    Both organizations hold a user with the same address; only the OTP holder's
    org may be used to complete the flow.
    """
    email = "shared_address@test.com"

    org_a_user = User(
        email=email,
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    org_b_user = User(
        email=email,
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=second_organization.id,
    )
    async_session.add_all([org_a_user, org_b_user])
    await async_session.commit()

    # Only org A's user gets an OTP.
    await _issue_otp(async_session, org_a_user)

    # Presenting it against org B must fail and must not verify org B's user.
    cross = await _verify_email(client, email, second_organization.slug)
    assert cross.status_code == 400, cross.text
    assert _detail_code(cross) == "otp.invalid"

    await async_session.refresh(org_b_user)
    assert org_b_user.email_verified is False

    # Org A's own user is unaffected and still completes normally.
    same = await _verify_email(client, email, test_organization.slug)
    assert same.status_code == 200, same.text

    await async_session.refresh(org_a_user)
    assert org_a_user.email_verified is True
    await async_session.refresh(org_b_user)
    assert org_b_user.email_verified is False


@pytest.mark.asyncio
async def test_verify_email_suspension_is_checked_per_tenant(
    client: AsyncClient, async_session, test_organization, second_organization
):
    """The suspension gate must read the row in the org being signed into."""
    email = "suspended_in_one@test.com"

    suspended_here = User(
        email=email,
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
        suspension_status=SuspensionStatus.SUSPENDED,
    )
    active_there = User(
        email=email,
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=second_organization.id,
    )
    async_session.add_all([suspended_here, active_there])
    await async_session.commit()

    await _issue_otp(async_session, suspended_here)
    await _issue_otp(async_session, active_there)

    blocked = await _verify_email(client, email, test_organization.slug)
    assert blocked.status_code == 403
    assert _detail_code(blocked) == "user.suspended"

    allowed = await _verify_email(client, email, second_organization.slug)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["access_token"]
