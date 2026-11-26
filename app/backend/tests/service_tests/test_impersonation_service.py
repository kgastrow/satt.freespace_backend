"""
Tests for the impersonation service.
"""

from fastapi import HTTPException
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.organization import Organization
from src.models.user import User
from src.services.impersonation import ImpersonationService


@pytest.mark.asyncio
async def test_start_impersonation_success(
    async_session: AsyncSession, test_admin_user: User, test_user: User
):
    """Test successful impersonation start"""
    token, session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
        ip_address="127.0.0.1",
        user_agent="Test Agent",
    )

    assert token is not None
    assert session.impersonator_id == test_admin_user.id
    assert session.target_user_id == test_user.id
    assert session.target_organization_id == test_user.organization_id
    assert session.ended_time is None
    assert session.ip_address == "127.0.0.1"
    assert session.user_agent == "Test Agent"


@pytest.mark.asyncio
async def test_start_impersonation_not_super_admin(
    async_session: AsyncSession, test_user: User, test_organization: Organization
):
    """Test that non-super admin cannot start impersonation"""
    # Create another regular user to impersonate
    target_user = User(
        email="target@test.com",
        password=hash_password("Password123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(target_user)
    await async_session.commit()
    await async_session.refresh(target_user)

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_user.id),
            target_user_id=str(target_user.id),
        )

    assert exc_info.value.status_code == 403
    assert "Only super admins" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_impersonation_self(
    async_session: AsyncSession, test_admin_user: User
):
    """Test that user cannot impersonate themselves"""
    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_admin_user.id),
        )

    assert exc_info.value.status_code == 400
    assert "Cannot impersonate yourself" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_impersonation_another_super_admin(
    async_session: AsyncSession, test_admin_user: User, test_organization: Organization
):
    """Test that super admin cannot impersonate another super admin"""
    # Create another super admin
    another_admin = User(
        email="admin2@test.com",
        password=hash_password("Password123!"),
        email_verified=True,
        is_admin=True,
        organization_id=test_organization.id,
    )
    async_session.add(another_admin)
    await async_session.commit()
    await async_session.refresh(another_admin)

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(another_admin.id),
        )

    assert exc_info.value.status_code == 400
    assert "Cannot impersonate another super admin" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_impersonation_unverified_email(
    async_session: AsyncSession, test_admin_user: User, test_organization: Organization
):
    """Test that cannot impersonate user with unverified email"""
    # Create user with unverified email
    unverified_user = User(
        email="unverified@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(unverified_user)
    await async_session.commit()
    await async_session.refresh(unverified_user)

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(unverified_user.id),
        )

    assert exc_info.value.status_code == 400
    assert "unverified email" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_impersonation_deleted_user(
    async_session: AsyncSession, test_admin_user: User, test_user: User
):
    """Test that cannot impersonate deleted user"""
    from datetime import datetime, timezone

    # Soft delete the user
    test_user.deleted_time = datetime.now(timezone.utc)
    await async_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(test_user.id),
        )

    assert exc_info.value.status_code == 400
    assert "deleted user" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_impersonation_inactive_organization(
    async_session: AsyncSession, test_admin_user: User, test_organization: Organization
):
    """Test that cannot impersonate user in inactive organization"""
    # Create user in the test organization
    target_user = User(
        email="target@test.com",
        password=hash_password("Password123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(target_user)
    await async_session.commit()

    # Deactivate the organization
    test_organization.is_active = False
    await async_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(target_user.id),
        )

    assert exc_info.value.status_code == 400
    assert "inactive organization" in exc_info.value.detail


@pytest.mark.asyncio
async def test_start_impersonation_auto_ends_existing_session(
    async_session: AsyncSession, test_admin_user: User, test_user: User
):
    """Test that starting a new impersonation session auto-ends any existing session"""
    from src.crud.impersonation_session import get_active_session_by_impersonator

    # Start first impersonation session
    _, first_session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )

    # Start second session - should auto-end the first
    _, second_session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )

    # First session should be ended
    await async_session.refresh(first_session)
    assert first_session.ended_time is not None

    # Second session should be active
    assert second_session.ended_time is None

    # Only one active session should exist
    active_session = await get_active_session_by_impersonator(
        async_session, str(test_admin_user.id)
    )
    assert active_session is not None
    assert active_session.id == second_session.id


@pytest.mark.asyncio
async def test_end_impersonation_success(
    async_session: AsyncSession, test_admin_user: User, test_user: User
):
    """Test successful impersonation end"""
    # Start impersonation
    _, session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )

    # End impersonation
    ended_session = await ImpersonationService.end_impersonation(
        session=async_session,
        impersonation_session_id=str(session.id),
    )

    assert ended_session is not None
    assert ended_session.id == session.id
    assert ended_session.ended_time is not None


@pytest.mark.asyncio
async def test_end_impersonation_not_found(async_session: AsyncSession):
    """Test ending non-existent impersonation session"""
    import uuid

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.end_impersonation(
            session=async_session,
            impersonation_session_id=str(uuid.uuid4()),
        )

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_active_session(
    async_session: AsyncSession, test_admin_user: User, test_user: User
):
    """Test getting active impersonation session"""
    # No active session initially
    active = await ImpersonationService.get_active_session(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
    )
    assert active is None

    # Start impersonation
    _, session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )

    # Get active session
    active = await ImpersonationService.get_active_session(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
    )
    assert active is not None
    assert active.id == session.id

    # End impersonation
    await ImpersonationService.end_impersonation(
        session=async_session,
        impersonation_session_id=str(session.id),
    )

    # No active session after ending
    active = await ImpersonationService.get_active_session(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
    )
    assert active is None


@pytest.mark.asyncio
async def test_impersonation_token_structure(
    async_session: AsyncSession, test_admin_user: User, test_user: User
):
    """Test that impersonation token contains correct claims"""
    import jwt

    from src.core.config import settings

    token, session = await ImpersonationService.start_impersonation(
        session=async_session,
        impersonator_id=str(test_admin_user.id),
        target_user_id=str(test_user.id),
    )

    # Decode token
    decoded = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])

    # Verify claims
    assert decoded["user_id"] == str(test_user.id)
    assert decoded["organization_id"] == str(test_user.organization_id)
    assert decoded["impersonator_id"] == str(test_admin_user.id)
    assert decoded["impersonation_session_id"] == str(session.id)
    assert "exp" in decoded


@pytest.mark.asyncio
async def test_target_user_not_found(
    async_session: AsyncSession, test_admin_user: User
):
    """Test impersonating non-existent user"""
    import uuid

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(test_admin_user.id),
            target_user_id=str(uuid.uuid4()),
        )

    assert exc_info.value.status_code == 404
    assert "Target user not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_impersonator_not_found(async_session: AsyncSession, test_user: User):
    """Test impersonation with non-existent impersonator"""
    import uuid

    with pytest.raises(HTTPException) as exc_info:
        await ImpersonationService.start_impersonation(
            session=async_session,
            impersonator_id=str(uuid.uuid4()),
            target_user_id=str(test_user.id),
        )

    assert exc_info.value.status_code == 404
    assert "Impersonator not found" in exc_info.value.detail
