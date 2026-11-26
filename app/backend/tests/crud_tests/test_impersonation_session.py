"""
Unit tests for impersonation session CRUD operations.
Tests the creation, retrieval, and management of impersonation sessions.
"""

from datetime import datetime

import pytest

from src.crud.impersonation_session import (
    create_session,
    end_session,
    get_active_session_by_impersonator,
    get_active_sessions_for_target,
    get_session_history,
)
from src.crud.user import create_user


@pytest.mark.asyncio
async def test_create_session(async_session, test_organization):
    """Test creating an impersonation session."""
    org_id = str(test_organization.id)

    # Create super admin (impersonator) and target user
    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create impersonation session
    session = await create_session(
        async_session,
        str(admin.id),
        str(target_user.id),
        org_id,
        ip_address="127.0.0.1",
        user_agent="Test Agent",
    )

    assert session.impersonator_id == admin.id
    assert session.target_user_id == target_user.id
    assert session.target_organization_id == test_organization.id
    assert session.ended_time is None
    assert session.ip_address == "127.0.0.1"
    assert session.user_agent == "Test Agent"
    assert session.created_time is not None


@pytest.mark.asyncio
async def test_get_active_session_by_impersonator(async_session, test_organization):
    """Test getting the active session for an impersonator."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # No active session initially
    active = await get_active_session_by_impersonator(async_session, str(admin.id))
    assert active is None

    # Create session
    session = await create_session(
        async_session, str(admin.id), str(target_user.id), org_id
    )

    # Should find active session
    active = await get_active_session_by_impersonator(async_session, str(admin.id))
    assert active is not None
    assert active.id == session.id


@pytest.mark.asyncio
async def test_get_active_sessions_for_target(async_session, test_organization):
    """Test getting all active sessions for a target user."""
    org_id = str(test_organization.id)

    admin1 = await create_user(
        async_session,
        {"email": "admin1@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    admin2 = await create_user(
        async_session,
        {"email": "admin2@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create multiple sessions for same target
    await create_session(async_session, str(admin1.id), str(target_user.id), org_id)
    await create_session(async_session, str(admin2.id), str(target_user.id), org_id)

    # Get all active sessions
    sessions = await get_active_sessions_for_target(async_session, str(target_user.id))

    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_end_session(async_session, test_organization):
    """Test ending an active impersonation session."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create session
    session = await create_session(
        async_session, str(admin.id), str(target_user.id), org_id
    )
    assert session.ended_time is None

    # End session
    ended_session = await end_session(async_session, str(session.id))

    assert ended_session is not None
    assert ended_session.id == session.id
    assert ended_session.ended_time is not None
    assert isinstance(ended_session.ended_time, datetime)

    # Verify no longer active
    active = await get_active_session_by_impersonator(async_session, str(admin.id))
    assert active is None


@pytest.mark.asyncio
async def test_end_nonexistent_session(async_session, test_organization):
    """Test ending a session that doesn't exist returns None."""
    from uuid import uuid4

    result = await end_session(async_session, str(uuid4()))
    assert result is None


@pytest.mark.asyncio
async def test_get_session_history_no_filters(async_session, test_organization):
    """Test getting session history without filters."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create multiple sessions
    session1 = await create_session(
        async_session, str(admin.id), str(target_user.id), org_id
    )
    await create_session(async_session, str(admin.id), str(target_user.id), org_id)
    await end_session(async_session, str(session1.id))

    # Get all history
    sessions, total = await get_session_history(async_session)

    assert total >= 2
    assert len(sessions) >= 2


@pytest.mark.asyncio
async def test_get_session_history_by_impersonator(async_session, test_organization):
    """Test getting session history filtered by impersonator."""
    org_id = str(test_organization.id)

    admin1 = await create_user(
        async_session,
        {"email": "admin1@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    admin2 = await create_user(
        async_session,
        {"email": "admin2@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create sessions with different impersonators
    await create_session(async_session, str(admin1.id), str(target_user.id), org_id)
    await create_session(async_session, str(admin2.id), str(target_user.id), org_id)

    # Get history for admin1 only
    sessions, total = await get_session_history(
        async_session, impersonator_id=str(admin1.id)
    )

    assert total == 1
    assert len(sessions) == 1
    assert sessions[0].impersonator_id == admin1.id


@pytest.mark.asyncio
async def test_get_session_history_by_target_user(async_session, test_organization):
    """Test getting session history filtered by target user."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target1 = await create_user(
        async_session, {"email": "target1@test.com", "password": "Password123!"}, org_id
    )
    target2 = await create_user(
        async_session, {"email": "target2@test.com", "password": "Password123!"}, org_id
    )

    # Create sessions with different targets
    await create_session(async_session, str(admin.id), str(target1.id), org_id)
    await create_session(async_session, str(admin.id), str(target2.id), org_id)

    # Get history for target1 only
    sessions, total = await get_session_history(
        async_session, target_user_id=str(target1.id)
    )

    assert total == 1
    assert len(sessions) == 1
    assert sessions[0].target_user_id == target1.id


@pytest.mark.asyncio
async def test_get_session_history_by_organization(async_session, test_organization):
    """Test getting session history filtered by organization."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create session
    await create_session(async_session, str(admin.id), str(target_user.id), org_id)

    # Get history for this organization
    sessions, total = await get_session_history(
        async_session, target_organization_id=org_id
    )

    assert total >= 1
    assert all(s.target_organization_id == test_organization.id for s in sessions)


@pytest.mark.asyncio
async def test_get_session_history_pagination(async_session, test_organization):
    """Test session history pagination."""
    org_id = str(test_organization.id)

    admin = await create_user(
        async_session,
        {"email": "admin@test.com", "password": "Password123!", "is_admin": True},
        org_id,
    )
    target_user = await create_user(
        async_session, {"email": "target@test.com", "password": "Password123!"}, org_id
    )

    # Create 5 sessions
    for _ in range(5):
        await create_session(async_session, str(admin.id), str(target_user.id), org_id)

    # Get first page
    sessions_page1, total = await get_session_history(
        async_session, impersonator_id=str(admin.id), limit=2, offset=0
    )

    assert total == 5
    assert len(sessions_page1) == 2

    # Get second page
    sessions_page2, total = await get_session_history(
        async_session, impersonator_id=str(admin.id), limit=2, offset=2
    )

    assert total == 5
    assert len(sessions_page2) == 2

    # Ensure different sessions
    page1_ids = {s.id for s in sessions_page1}
    page2_ids = {s.id for s in sessions_page2}
    assert page1_ids.isdisjoint(page2_ids)
