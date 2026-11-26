"""
Unit tests for audit log CRUD operations.
"""

import pytest

from src.core.query_params import FilterOperator, FilterSpec
from src.crud.audit_log import (
    compute_changes,
    create_audit_log,
    get_audit_log_by_id,
    get_audit_logs,
    get_resource_history,
)
from src.models.audit_log import AuditAction


@pytest.mark.asyncio
async def test_create_audit_log(async_session, test_organization, test_user):
    """Test creating an audit log entry."""
    audit_log = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
        actor_id=str(test_user.id),
        changes={"email": {"old": None, "new": "test@example.com"}},
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0",
    )

    assert audit_log.id is not None
    assert str(audit_log.organization_id) == str(test_organization.id)
    assert audit_log.action == "CREATE"
    assert audit_log.resource_type == "User"
    assert str(audit_log.resource_id) == str(test_user.id)
    assert str(audit_log.actor_id) == str(test_user.id)
    assert audit_log.changes == {"email": {"old": None, "new": "test@example.com"}}
    assert audit_log.ip_address == "127.0.0.1"
    assert audit_log.user_agent == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_create_audit_log_without_actor(
    async_session, test_organization, test_user
):
    """Test creating audit log for system actions (no actor)."""
    audit_log = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.DELETE,
        resource_type="User",
        resource_id=str(test_user.id),
        actor_id=None,  # System action
    )

    assert audit_log.id is not None
    assert audit_log.actor_id is None


@pytest.mark.asyncio
async def test_get_audit_logs(async_session, test_organization, test_user):
    """Test retrieving audit logs with pagination."""
    # Create multiple audit logs
    for i in range(5):
        await create_audit_log(
            session=async_session,
            organization_id=str(test_organization.id),
            action=AuditAction.UPDATE,
            resource_type="User",
            resource_id=str(test_user.id),
            actor_id=str(test_user.id),
        )

    logs, total = await get_audit_logs(
        session=async_session,
        organization_id=str(test_organization.id),
        limit=3,
        offset=0,
    )

    assert len(logs) == 3
    assert total == 5


@pytest.mark.asyncio
async def test_get_audit_logs_filter_by_resource_type(
    async_session, test_organization, test_user, test_role
):
    """Test filtering audit logs by resource type."""
    # Create logs for different resource types
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="Role",
        resource_id=str(test_role.id),
    )

    user_logs, total = await get_audit_logs(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[
            FilterSpec(field="resource_type", operator=FilterOperator.EQ, value="User")
        ],
    )

    assert total == 1
    assert all(log.resource_type == "User" for log in user_logs)


@pytest.mark.asyncio
async def test_get_audit_logs_filter_by_action(
    async_session, test_organization, test_user
):
    """Test filtering audit logs by action."""
    # Create logs for different actions
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.UPDATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.DELETE,
        resource_type="User",
        resource_id=str(test_user.id),
    )

    create_logs, total = await get_audit_logs(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[
            FilterSpec(field="action", operator=FilterOperator.EQ, value="CREATE")
        ],
    )

    assert total == 1
    assert create_logs[0].action == "CREATE"


@pytest.mark.asyncio
async def test_get_audit_logs_filter_by_actor(
    async_session, test_organization, test_user, test_admin_user
):
    """Test filtering audit logs by actor."""
    # Create logs from different actors
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
        actor_id=str(test_user.id),
    )
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.UPDATE,
        resource_type="User",
        resource_id=str(test_user.id),
        actor_id=str(test_admin_user.id),
    )

    user_logs, total = await get_audit_logs(
        session=async_session,
        organization_id=str(test_organization.id),
        filters=[
            FilterSpec(
                field="actor_id", operator=FilterOperator.EQ, value=str(test_user.id)
            )
        ],
    )

    assert total == 1
    assert str(user_logs[0].actor_id) == str(test_user.id)


@pytest.mark.asyncio
async def test_get_audit_log_by_id(async_session, test_organization, test_user):
    """Test retrieving a specific audit log by ID."""
    created_log = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )

    fetched_log = await get_audit_log_by_id(
        session=async_session,
        audit_log_id=str(created_log.id),
        organization_id=str(test_organization.id),
    )

    assert fetched_log is not None
    assert fetched_log.id == created_log.id


@pytest.mark.asyncio
async def test_get_audit_log_by_id_wrong_org(
    async_session, test_organization, second_organization, test_user
):
    """Test that audit logs are isolated by organization."""
    created_log = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )

    # Try to fetch with wrong organization
    fetched_log = await get_audit_log_by_id(
        session=async_session,
        audit_log_id=str(created_log.id),
        organization_id=str(second_organization.id),
    )

    assert fetched_log is None


@pytest.mark.asyncio
async def test_get_resource_history(async_session, test_organization, test_user):
    """Test retrieving complete audit history for a resource."""
    # Create multiple logs for same resource
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.UPDATE,
        resource_type="User",
        resource_id=str(test_user.id),
        changes={"email": {"old": "old@test.com", "new": "new@test.com"}},
    )
    await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.UPDATE,
        resource_type="User",
        resource_id=str(test_user.id),
        changes={"first_name": {"old": None, "new": "John"}},
    )

    history = await get_resource_history(
        session=async_session,
        organization_id=str(test_organization.id),
        resource_type="User",
        resource_id=str(test_user.id),
    )

    assert len(history) == 3
    # Should be ordered by time descending (most recent first)
    assert history[0].action == "UPDATE"


def test_compute_changes_detects_differences():
    """Test that compute_changes correctly identifies changed fields."""
    old_values = {"email": "old@example.com", "name": "Old Name", "status": "active"}
    new_values = {"email": "new@example.com", "name": "Old Name", "status": "inactive"}

    changes = compute_changes(old_values, new_values)

    assert "email" in changes
    assert changes["email"] == {"old": "old@example.com", "new": "new@example.com"}
    assert "status" in changes
    assert changes["status"] == {"old": "active", "new": "inactive"}
    assert "name" not in changes  # No change


def test_compute_changes_handles_new_fields():
    """Test that compute_changes handles new fields being added."""
    old_values = {"email": "test@example.com"}
    new_values = {"email": "test@example.com", "phone": "+1234567890"}

    changes = compute_changes(old_values, new_values)

    assert "phone" in changes
    assert changes["phone"] == {"old": None, "new": "+1234567890"}


def test_compute_changes_handles_removed_fields():
    """Test that compute_changes handles fields being removed."""
    old_values = {"email": "test@example.com", "phone": "+1234567890"}
    new_values = {"email": "test@example.com"}

    changes = compute_changes(old_values, new_values)

    assert "phone" in changes
    assert changes["phone"] == {"old": "+1234567890", "new": None}


def test_compute_changes_redacts_passwords():
    """Test that compute_changes redacts password fields."""
    old_values = {"email": "test@example.com", "password": "oldpassword123"}
    new_values = {"email": "test@example.com", "password": "newpassword456"}

    changes = compute_changes(old_values, new_values)

    assert "password" in changes
    assert changes["password"] == {"old": "[REDACTED]", "new": "[REDACTED]"}


def test_compute_changes_returns_empty_for_no_changes():
    """Test that compute_changes returns empty dict when nothing changed."""
    values = {"email": "test@example.com", "name": "Test"}

    changes = compute_changes(values, values.copy())

    assert changes == {}


@pytest.mark.asyncio
async def test_audit_logs_ordered_by_time_descending(
    async_session, test_organization, test_user
):
    """Test that audit logs are returned in descending time order."""
    # Create logs
    log1 = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.CREATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )
    log2 = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.UPDATE,
        resource_type="User",
        resource_id=str(test_user.id),
    )
    log3 = await create_audit_log(
        session=async_session,
        organization_id=str(test_organization.id),
        action=AuditAction.DELETE,
        resource_type="User",
        resource_id=str(test_user.id),
    )

    logs, _ = await get_audit_logs(
        session=async_session,
        organization_id=str(test_organization.id),
    )

    # Most recent should be first
    assert logs[0].id == log3.id
    assert logs[1].id == log2.id
    assert logs[2].id == log1.id
