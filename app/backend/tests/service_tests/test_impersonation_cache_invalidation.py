"""
Security tests for impersonation JWT-cache invalidation.

Regression tests for the vulnerability where ending an impersonation session
did not evict the cached JWT claims for the impersonated target user. Because
get_current_user's cached path does not re-check the impersonation session
state, stale cached claims would keep the ended impersonation token alive until
the cache TTL expired.

The impersonation service must call cache_service.invalidate_jwt_for_user for
the target user both on explicit end and on the auto-end of an orphaned session
during start.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.services.impersonation import ImpersonationService


@pytest.mark.asyncio
async def test_end_impersonation_invalidates_target_jwt_cache(
    async_session: AsyncSession,
    test_admin_user: User,
    test_user: User,
    monkeypatch,
):
    """Ending an impersonation session must evict the target user's JWT cache."""
    invalidated: list[str] = []

    async def _spy_invalidate(user_id: str) -> int:
        invalidated.append(user_id)
        return 0

    # Patch the singleton used by the impersonation service.
    from src.services import impersonation as impersonation_module

    monkeypatch.setattr(
        impersonation_module.cache_service,
        "invalidate_jwt_for_user",
        _spy_invalidate,
    )

    _, imp_session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )

    # Starting a fresh session (no prior orphan) should not invalidate anyone.
    assert invalidated == []

    await ImpersonationService.end_impersonation(
        session=async_session,
        impersonation_session_id=str(imp_session.id),
    )

    # The impersonated target's cached claims must be evicted on end.
    assert str(test_user.id) in invalidated


@pytest.mark.asyncio
async def test_auto_end_orphaned_session_invalidates_previous_target(
    async_session: AsyncSession,
    test_admin_user: User,
    test_user: User,
    second_org_user: User,
    monkeypatch,
):
    """Auto-ending an orphaned session during start must evict its target's cache."""
    invalidated: list[str] = []

    async def _spy_invalidate(user_id: str) -> int:
        invalidated.append(user_id)
        return 0

    from src.services import impersonation as impersonation_module

    monkeypatch.setattr(
        impersonation_module.cache_service,
        "invalidate_jwt_for_user",
        _spy_invalidate,
    )

    # First session against test_user.
    await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )
    assert invalidated == []

    # Starting a second session auto-ends the first (orphaned) one and must
    # invalidate the previous target's cached JWT claims.
    await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(second_org_user.id),
    )

    assert str(test_user.id) in invalidated


@pytest.mark.asyncio
async def test_ended_impersonation_token_no_longer_authenticates(
    client,
    test_super_admin_token,
    test_organization,
    async_session,
):
    """
    After ending impersonation, a fresh request with the impersonation token is
    rejected (401) because get_current_user re-validates the session state.
    """
    from src.core.security import hash_password
    from src.models.user import User as UserModel

    # Create a target user to impersonate in the admin's organization.
    target = UserModel(
        email="imp-target@test.com",
        password=hash_password("Target123!"),
        email_verified=True,
        is_admin=False,
        organization_id=test_organization.id,
    )
    async_session.add(target)
    await async_session.commit()
    await async_session.refresh(target)

    # Start impersonation to obtain a valid impersonation token.
    start_resp = await client.post(
        f"/api/v1/admin/impersonate/{target.id}",
        headers={"Authorization": test_super_admin_token},
    )
    assert start_resp.status_code == 200
    imp_token = start_resp.json()["impersonation_token"]

    # The impersonation token authenticates while the session is active.
    ok_resp = await client.get(
        "/api/v1/user/me",
        headers={"Authorization": f"Bearer {imp_token}"},
    )
    assert ok_resp.status_code == 200

    # End the impersonation session using the impersonation token.
    end_resp = await client.post(
        "/api/v1/admin/impersonate/end",
        headers={"Authorization": f"Bearer {imp_token}"},
    )
    assert end_resp.status_code == 200

    # A fresh request with the same impersonation token must now be rejected.
    after_resp = await client.get(
        "/api/v1/user/me",
        headers={"Authorization": f"Bearer {imp_token}"},
    )
    assert after_resp.status_code == 401
