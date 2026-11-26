"""Security tests for the account gates on ``POST /admin/impersonate/end``.

Ending an impersonation session hands the admin a working access token for
their own account. The endpoint re-validated ``is_admin`` but nothing else, and
``get_current_user`` cannot cover the gap: on an impersonation token it
validates the TARGET user and the TARGET organization, never the admin's.

An impersonation session can stay open for a long time. The two gates that can
flip while it is open -- the admin being suspended, and the admin's own
organization being deactivated -- are now applied before the token is minted,
with the same detail codes ``issue_session_for_user`` uses.
"""

from httpx import AsyncClient
import pytest

from src.core.security import hash_password
from src.models.organization import Organization
from src.models.user import SuspensionStatus, User


@pytest.fixture
async def impersonation_target(async_session, test_organization):
    user = User(
        email="impersonation_gate_target@test.com",
        password=hash_password("TargetUser123!"),
        email_verified=True,
        organization_id=test_organization.id,
        is_admin=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _start(client: AsyncClient, admin_token: str, target_user) -> str:
    response = await client.post(
        f"/api/v1/admin/impersonate/{target_user.id}",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200, response.text
    return response.json()["impersonation_token"]


async def _end(client: AsyncClient, impersonation_token: str):
    return await client.post(
        "/api/v1/admin/impersonate/end",
        headers={"Authorization": f"Bearer {impersonation_token}"},
    )


def _detail_code(response) -> str:
    return response.json().get("detail_code", "")


@pytest.mark.asyncio
async def test_end_impersonation_rejects_suspended_admin(
    client: AsyncClient,
    async_session,
    test_super_admin_token,
    test_admin_user,
    impersonation_target,
):
    """An admin suspended mid-impersonation must not get their session back."""
    token = await _start(client, test_super_admin_token, impersonation_target)

    test_admin_user.suspension_status = SuspensionStatus.SUSPENDED
    await async_session.commit()

    response = await _end(client, token)

    assert response.status_code == 403, response.text
    assert _detail_code(response) == "user.suspended"
    assert "access_token" not in response.json()


@pytest.mark.asyncio
async def test_end_impersonation_rejects_admin_with_inactive_org(
    client: AsyncClient,
    async_session,
    test_super_admin_token,
    test_organization,
    impersonation_target,
):
    """A deactivated organization must not hand a session back either.

    Here the admin and the target share an organization, so ``get_current_user``
    rejects the impersonation token first; the assertion is on the outcome (no
    token), not on which layer refused. The admin-specific org gate is pinned
    separately by
    ``test_end_impersonation_checks_the_admins_own_organization``.
    """
    token = await _start(client, test_super_admin_token, impersonation_target)

    test_organization.is_active = False
    await async_session.commit()

    response = await _end(client, token)

    assert response.status_code == 403, response.text
    assert "access_token" not in response.json()


@pytest.mark.asyncio
async def test_end_impersonation_rejects_demoted_admin(
    client: AsyncClient,
    async_session,
    test_super_admin_token,
    test_admin_user,
    impersonation_target,
):
    """Control for the pre-existing super-admin re-validation."""
    token = await _start(client, test_super_admin_token, impersonation_target)

    test_admin_user.is_admin = False
    await async_session.commit()

    response = await _end(client, token)

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_end_impersonation_still_works_for_an_active_admin(
    client: AsyncClient,
    async_session,
    test_super_admin_token,
    test_admin_user,
    impersonation_target,
):
    """Happy path: the gates must not break the ordinary end-impersonation flow.

    The token handed back is a plain access token for the admin, with no
    impersonation claims and no refresh cookie -- this endpoint restores an
    already-gated session, it does not create new persistent credentials.
    """
    import jwt

    from src.core.config import settings

    token = await _start(client, test_super_admin_token, impersonation_target)

    response = await _end(client, token)

    assert response.status_code == 200, response.text
    admin_token = response.json()["access_token"]
    decoded = jwt.decode(admin_token, settings.JWT_SECRET, algorithms=["HS256"])
    assert decoded["user_id"] == str(test_admin_user.id)
    assert "impersonator_id" not in decoded
    assert "refresh_token" not in response.cookies


@pytest.mark.asyncio
async def test_end_impersonation_checks_the_admins_own_organization(
    client: AsyncClient,
    async_session,
    test_super_admin_token,
    test_admin_user,
    test_organization,
    impersonation_target,
):
    """The org gate must read the ADMIN's org, not the impersonated user's.

    Move the admin into a second, deactivated organization while the target
    stays in the active one. ``get_current_user`` sees only the target's
    (active) org on an impersonation token, so nothing but this endpoint's own
    check can catch it.
    """
    dormant = Organization(
        name="Dormant Admin Org", slug="dormant-admin-org", is_active=False
    )
    async_session.add(dormant)
    await async_session.commit()

    token = await _start(client, test_super_admin_token, impersonation_target)

    test_admin_user.organization_id = dormant.id
    await async_session.commit()

    response = await _end(client, token)

    assert response.status_code == 403, response.text
    assert _detail_code(response) == "auth.organization_not_active"
    # The target's own organization is untouched and still active.
    await async_session.refresh(test_organization)
    assert test_organization.is_active is True
