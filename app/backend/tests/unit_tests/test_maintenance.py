"""
Unit tests for maintenance mode functionality.

Tests cover:
- Public maintenance status endpoint (GET /api/v1/maintenance/status)
- Admin maintenance config retrieval (GET /api/v1/maintenance/admin/config)
- Admin maintenance config update (PUT /api/v1/maintenance/admin/config)
- CRUD operations for maintenance configuration
- Validation of scheduled times
- Maintenance history tracking
"""

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.maintenance import (
    cancel_scheduled_maintenance,
    create_maintenance_history,
    end_maintenance,
    get_active_maintenance_history,
    get_maintenance_config,
    get_maintenance_history,
    get_maintenance_history_by_id,
    is_maintenance_active,
    start_maintenance,
    update_maintenance_config,
)
from src.models.maintenance_history import MaintenanceStatus


# =============================================================================
# CRUD Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_maintenance_config_default(async_session: AsyncSession):
    """Test getting maintenance config returns defaults when not configured"""
    config = await get_maintenance_config(async_session)

    assert config["enabled"] is False
    assert config["message"] is None
    assert config["scheduled_start"] is None
    assert config["scheduled_end"] is None
    assert config["allow_super_admin"] is True


@pytest.mark.asyncio
async def test_update_maintenance_config(async_session: AsyncSession):
    """Test updating maintenance configuration"""
    future_start = datetime.now(timezone.utc) + timedelta(hours=1)
    future_end = datetime.now(timezone.utc) + timedelta(hours=3)

    config = await update_maintenance_config(
        session=async_session,
        enabled=True,
        message="System maintenance in progress",
        scheduled_start=future_start,
        scheduled_end=future_end,
        allow_super_admin=True,
    )

    assert config["enabled"] is True
    assert config["message"] == "System maintenance in progress"
    assert config["scheduled_start"] == future_start.isoformat()
    assert config["scheduled_end"] == future_end.isoformat()
    assert config["allow_super_admin"] is True


@pytest.mark.asyncio
async def test_update_maintenance_config_enable_only(async_session: AsyncSession):
    """Test enabling maintenance without schedule"""
    config = await update_maintenance_config(
        session=async_session,
        enabled=True,
        message="Maintenance active",
        allow_super_admin=False,
    )

    assert config["enabled"] is True
    assert config["message"] == "Maintenance active"
    assert config["scheduled_start"] is None
    assert config["scheduled_end"] is None
    assert config["allow_super_admin"] is False


@pytest.mark.asyncio
async def test_is_maintenance_active(async_session: AsyncSession):
    """Test checking if maintenance is active"""
    # Initially not active
    assert await is_maintenance_active(async_session) is False

    # Enable maintenance
    await update_maintenance_config(
        session=async_session,
        enabled=True,
    )

    # Should now be active
    assert await is_maintenance_active(async_session) is True

    # Disable maintenance
    await update_maintenance_config(
        session=async_session,
        enabled=False,
    )

    # Should no longer be active
    assert await is_maintenance_active(async_session) is False


# =============================================================================
# API Tests - Public Endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_get_maintenance_status_public(client: AsyncClient):
    """Test public maintenance status endpoint (no auth required)"""
    response = await client.get("/api/v1/maintenance/status")

    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "message" in data
    assert "scheduled_start" in data
    assert "scheduled_end" in data
    assert "allow_super_admin" in data
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_get_maintenance_status_when_active(
    client: AsyncClient, async_session: AsyncSession
):
    """Test public status endpoint returns correct data when maintenance is active"""
    # Enable maintenance with message
    await update_maintenance_config(
        session=async_session,
        enabled=True,
        message="System under maintenance",
        allow_super_admin=True,
    )

    response = await client.get("/api/v1/maintenance/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["message"] == "System under maintenance"
    assert data["allow_super_admin"] is True


@pytest.mark.asyncio
async def test_get_maintenance_status_with_schedule(
    client: AsyncClient, async_session: AsyncSession
):
    """Test public status endpoint returns scheduled times"""
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = datetime.now(timezone.utc) + timedelta(hours=4)

    await update_maintenance_config(
        session=async_session,
        enabled=False,
        scheduled_start=future_start,
        scheduled_end=future_end,
    )

    response = await client.get("/api/v1/maintenance/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["scheduled_start"] is not None
    assert data["scheduled_end"] is not None


# =============================================================================
# API Tests - Admin Endpoints
# =============================================================================


@pytest.mark.asyncio
async def test_get_maintenance_config_requires_admin(
    client: AsyncClient, test_jwt_token: str
):
    """Test getting full config requires super admin auth"""
    response = await client.get(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_maintenance_config_admin(client: AsyncClient, test_admin_token: str):
    """Test super admin can get full maintenance config"""
    response = await client.get(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "message" in data
    assert "scheduled_start" in data
    assert "scheduled_end" in data
    assert "allow_super_admin" in data
    assert "updated_time" in data
    assert "updated_by_user_id" in data


@pytest.mark.asyncio
async def test_update_maintenance_config_requires_admin(
    client: AsyncClient, test_jwt_token: str
):
    """Test updating config requires super admin auth"""
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_jwt_token},
        json={"enabled": True, "allow_super_admin": True},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_maintenance_config_admin(
    client: AsyncClient, test_admin_token: str
):
    """Test super admin can update maintenance config"""
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": True,
            "message": "Scheduled maintenance",
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "message_code" in data
    assert data["message_code"] == "maintenance.updated"
    assert "config" in data
    assert data["config"]["enabled"] is True
    assert data["config"]["message"] == "Scheduled maintenance"


@pytest.mark.asyncio
async def test_update_maintenance_config_with_schedule(
    client: AsyncClient, test_admin_token: str
):
    """Test updating maintenance config with scheduled times"""
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = datetime.now(timezone.utc) + timedelta(hours=4)

    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": False,
            "message": "Scheduled for later",
            "scheduled_start": future_start.isoformat(),
            "scheduled_end": future_end.isoformat(),
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["config"]["enabled"] is False
    assert data["config"]["scheduled_start"] is not None
    assert data["config"]["scheduled_end"] is not None


@pytest.mark.asyncio
async def test_update_maintenance_disable(
    client: AsyncClient, test_admin_token: str, async_session: AsyncSession
):
    """Test disabling maintenance mode"""
    # First enable it
    await update_maintenance_config(
        session=async_session,
        enabled=True,
        message="Active maintenance",
    )

    # Now disable via API
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": False,
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["config"]["enabled"] is False


@pytest.mark.asyncio
async def test_maintenance_config_validates_required_fields(
    client: AsyncClient, test_admin_token: str
):
    """Test that required fields are validated"""
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            # Missing 'enabled' field
            "message": "Test",
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_maintenance_config_rejects_extra_fields(
    client: AsyncClient, test_admin_token: str
):
    """Test that extra fields are rejected"""
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": True,
            "allow_super_admin": True,
            "extra_field": "should_be_rejected",
        },
    )

    assert response.status_code == 422


# =============================================================================
# Maintenance History CRUD Tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_maintenance_history(async_session: AsyncSession):
    """Test creating a maintenance history record"""
    history = await create_maintenance_history(
        session=async_session,
        scheduled_start=datetime.now(timezone.utc) + timedelta(hours=1),
        scheduled_end=datetime.now(timezone.utc) + timedelta(hours=3),
        message="Scheduled maintenance",
        status=MaintenanceStatus.SCHEDULED,
    )

    assert history.id is not None
    assert history.status == MaintenanceStatus.SCHEDULED.value
    assert history.message == "Scheduled maintenance"
    assert history.scheduled_start is not None
    assert history.scheduled_end is not None
    assert history.actual_start is None
    assert history.actual_end is None


@pytest.mark.asyncio
async def test_create_maintenance_history_active(async_session: AsyncSession):
    """Test creating an active maintenance history record"""
    now = datetime.now(timezone.utc)
    history = await create_maintenance_history(
        session=async_session,
        actual_start=now,
        message="Immediate maintenance",
        status=MaintenanceStatus.ACTIVE,
    )

    assert history.status == MaintenanceStatus.ACTIVE.value
    assert history.actual_start is not None
    assert history.scheduled_start is None


@pytest.mark.asyncio
async def test_get_maintenance_history_by_id(async_session: AsyncSession):
    """Test getting a maintenance history record by ID"""
    # Create a history record
    created = await create_maintenance_history(
        session=async_session,
        message="Test maintenance",
        status=MaintenanceStatus.SCHEDULED,
    )

    # Retrieve it
    retrieved = await get_maintenance_history_by_id(async_session, created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.message == "Test maintenance"


@pytest.mark.asyncio
async def test_get_maintenance_history_pagination(async_session: AsyncSession):
    """Test getting maintenance history with pagination"""
    # Create multiple history records
    for i in range(5):
        await create_maintenance_history(
            session=async_session,
            message=f"Maintenance {i}",
            status=MaintenanceStatus.COMPLETED,
        )

    # Get with limit
    histories, total = await get_maintenance_history(
        session=async_session,
        limit=2,
        offset=0,
    )

    assert len(histories) == 2
    assert total >= 5


@pytest.mark.asyncio
async def test_get_maintenance_history_status_filter(async_session: AsyncSession):
    """Test filtering maintenance history by status"""
    # Create records with different statuses
    await create_maintenance_history(
        session=async_session,
        message="Scheduled",
        status=MaintenanceStatus.SCHEDULED,
    )
    await create_maintenance_history(
        session=async_session,
        message="Active",
        status=MaintenanceStatus.ACTIVE,
    )
    await create_maintenance_history(
        session=async_session,
        message="Completed",
        status=MaintenanceStatus.COMPLETED,
    )

    # Filter by ACTIVE
    histories, total = await get_maintenance_history(
        session=async_session,
        status_filter=MaintenanceStatus.ACTIVE,
    )

    assert total >= 1
    for h in histories:
        assert h.status == MaintenanceStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_get_active_maintenance_history(async_session: AsyncSession):
    """Test getting the currently active maintenance history"""
    # Initially no active maintenance
    active = await get_active_maintenance_history(async_session)
    assert active is None

    # Create active maintenance
    created = await create_maintenance_history(
        session=async_session,
        actual_start=datetime.now(timezone.utc),
        message="Active now",
        status=MaintenanceStatus.ACTIVE,
    )

    # Should find it
    active = await get_active_maintenance_history(async_session)
    assert active is not None
    assert active.id == created.id


@pytest.mark.asyncio
async def test_start_maintenance_immediate(async_session: AsyncSession):
    """Test starting immediate maintenance"""
    history = await start_maintenance(
        session=async_session,
        message="Emergency maintenance",
        is_immediate=True,
    )

    assert history.status == MaintenanceStatus.ACTIVE.value
    assert history.actual_start is not None
    assert history.message == "Emergency maintenance"


@pytest.mark.asyncio
async def test_start_maintenance_scheduled(async_session: AsyncSession):
    """Test scheduling maintenance for the future"""
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = datetime.now(timezone.utc) + timedelta(hours=4)

    history = await start_maintenance(
        session=async_session,
        scheduled_start=future_start,
        scheduled_end=future_end,
        message="Planned maintenance",
        is_immediate=False,
    )

    assert history.status == MaintenanceStatus.SCHEDULED.value
    assert history.actual_start is None
    assert history.scheduled_start is not None
    assert history.scheduled_end is not None


@pytest.mark.asyncio
async def test_end_maintenance(async_session: AsyncSession):
    """Test ending an active maintenance period"""
    # Start maintenance
    history = await start_maintenance(
        session=async_session,
        message="To be ended",
        is_immediate=True,
    )

    # End it
    ended = await end_maintenance(
        session=async_session,
        history_id=history.id,
    )

    assert ended is not None
    assert ended.status == MaintenanceStatus.COMPLETED.value
    assert ended.actual_end is not None


@pytest.mark.asyncio
async def test_cancel_scheduled_maintenance(async_session: AsyncSession):
    """Test cancelling scheduled maintenance"""
    # Schedule maintenance
    history = await start_maintenance(
        session=async_session,
        scheduled_start=datetime.now(timezone.utc) + timedelta(hours=2),
        scheduled_end=datetime.now(timezone.utc) + timedelta(hours=4),
        message="To be cancelled",
        is_immediate=False,
    )

    # Cancel it
    cancelled = await cancel_scheduled_maintenance(
        session=async_session,
        history_id=history.id,
    )

    assert cancelled is not None
    assert cancelled.status == MaintenanceStatus.CANCELLED.value


# =============================================================================
# Maintenance History API Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_maintenance_history_requires_admin(
    client: AsyncClient, test_jwt_token: str
):
    """Test getting maintenance history requires super admin auth"""
    response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_maintenance_history_admin(
    client: AsyncClient, test_admin_token: str
):
    """Test super admin can get maintenance history"""
    response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_maintenance_history_with_pagination(
    client: AsyncClient, test_admin_token: str, async_session: AsyncSession
):
    """Test maintenance history pagination"""
    # Create some history records
    for i in range(3):
        await create_maintenance_history(
            session=async_session,
            message=f"API Test {i}",
            status=MaintenanceStatus.COMPLETED,
        )

    response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_admin_token},
        params={"limit": 2, "offset": 0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 2
    assert len(data["items"]) <= 2


@pytest.mark.asyncio
async def test_get_maintenance_history_with_status_filter(
    client: AsyncClient, test_admin_token: str, async_session: AsyncSession
):
    """Test filtering maintenance history by status via API"""
    # Create records with different statuses
    await create_maintenance_history(
        session=async_session,
        message="API Completed",
        status=MaintenanceStatus.COMPLETED,
    )

    response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_admin_token},
        params={"status": "completed"},
    )

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "completed"


@pytest.mark.asyncio
async def test_enable_maintenance_creates_history(
    client: AsyncClient, test_admin_token: str
):
    """Test that enabling maintenance creates a history record"""
    # Enable maintenance
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": True,
            "message": "Test enable history",
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 200

    # Check history was created
    history_response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_admin_token},
        params={"status": "active"},
    )

    assert history_response.status_code == 200
    data = history_response.json()
    assert data["total"] >= 1

    # Find our record
    found = False
    for item in data["items"]:
        if item["message"] == "Test enable history":
            found = True
            assert item["status"] == "active"
            assert item["actual_start"] is not None
            break
    assert found, "History record not created when enabling maintenance"


@pytest.mark.asyncio
async def test_disable_maintenance_completes_history(
    client: AsyncClient, test_admin_token: str, async_session: AsyncSession
):
    """Test that disabling maintenance completes the history record"""
    # First enable via CRUD to create a known record
    history = await start_maintenance(
        session=async_session,
        message="To be disabled via API",
        is_immediate=True,
    )

    # Also update the config to match
    await update_maintenance_config(
        session=async_session,
        enabled=True,
        message="To be disabled via API",
        allow_super_admin=True,
    )

    # Now disable via API
    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": False,
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 200

    # Check history was completed
    updated = await get_maintenance_history_by_id(async_session, history.id)
    assert updated.status == MaintenanceStatus.COMPLETED.value
    assert updated.actual_end is not None


@pytest.mark.asyncio
async def test_schedule_maintenance_creates_scheduled_history(
    client: AsyncClient, test_admin_token: str
):
    """Test that scheduling maintenance creates a SCHEDULED history record"""
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = datetime.now(timezone.utc) + timedelta(hours=4)

    response = await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": False,
            "message": "Scheduled via API",
            "scheduled_start": future_start.isoformat(),
            "scheduled_end": future_end.isoformat(),
            "allow_super_admin": True,
        },
    )

    assert response.status_code == 200

    # Check history was created as scheduled
    history_response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_admin_token},
        params={"status": "scheduled"},
    )

    assert history_response.status_code == 200
    data = history_response.json()

    # Find our record
    found = False
    for item in data["items"]:
        if item["message"] == "Scheduled via API":
            found = True
            assert item["status"] == "scheduled"
            assert item["scheduled_start"] is not None
            assert item["scheduled_end"] is not None
            assert item["actual_start"] is None
            break
    assert found, "Scheduled history record not created"


@pytest.mark.asyncio
async def test_history_response_includes_user_info(
    client: AsyncClient, test_admin_token: str
):
    """Test that history response includes user information"""
    # Enable maintenance to create a history record with user
    await client.put(
        "/api/v1/admin/maintenance",
        headers={"Authorization": test_admin_token},
        json={
            "enabled": True,
            "message": "User info test",
            "allow_super_admin": True,
        },
    )

    # Get history
    response = await client.get(
        "/api/v1/admin/maintenance/history",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()

    # Find our record and check user info
    for item in data["items"]:
        if item["message"] == "User info test":
            assert item["started_by"] is not None
            assert "id" in item["started_by"]
            assert "email" in item["started_by"]
            break
