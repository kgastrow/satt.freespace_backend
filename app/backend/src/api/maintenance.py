"""
Maintenance mode API endpoints.

Provides public endpoint for checking maintenance status (no auth required).
Admin endpoints are in admin.py under /admin/maintenance.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.crud.maintenance import get_maintenance_config
from src.serialisers.maintenance import MaintenanceStatusResponse


router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get(
    "/status", response_model=MaintenanceStatusResponse, status_code=status.HTTP_200_OK
)
async def get_maintenance_status(
    session: Annotated[AsyncSession, Depends(get_session)]
):
    """
    Get current maintenance mode status.

    This is a public endpoint (no authentication required) that returns the current
    maintenance mode status. The frontend uses this to check if the system is in
    maintenance mode and display the maintenance page accordingly.

    Maintenance is considered active if:
    - enabled is True (manually enabled), OR
    - Current time is within scheduled_start and scheduled_end window

    Returns:
        MaintenanceStatusResponse with current maintenance status
    """
    from datetime import timezone

    config = await get_maintenance_config(session)

    # Parse datetime strings back to datetime objects if present
    scheduled_start = None
    scheduled_end = None

    if config.get("scheduled_start"):
        scheduled_start = datetime.fromisoformat(config["scheduled_start"])

    if config.get("scheduled_end"):
        scheduled_end = datetime.fromisoformat(config["scheduled_end"])

    # Determine if maintenance is active
    # Either manually enabled OR within scheduled window
    manually_enabled = config.get("enabled", False)
    now = datetime.now(timezone.utc)

    # Check if we're within the scheduled maintenance window
    within_schedule = False
    if scheduled_start and scheduled_end:
        # Make datetimes timezone-aware if they aren't
        if scheduled_start.tzinfo is None:
            scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
        if scheduled_end.tzinfo is None:
            scheduled_end = scheduled_end.replace(tzinfo=timezone.utc)
        within_schedule = scheduled_start <= now <= scheduled_end

    is_active = manually_enabled or within_schedule

    return MaintenanceStatusResponse(
        enabled=is_active,
        message=config.get("message"),
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        allow_super_admin=config.get("allow_super_admin", True),
    )
