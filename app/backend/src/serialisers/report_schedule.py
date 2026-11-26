"""
Pydantic serializers for Report Schedule API endpoints.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from croniter import croniter
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ReportScheduleCreateRequest(BaseModel):
    """Request schema for creating a report schedule."""

    report_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of report to generate (e.g., 'users_report')",
    )
    name: str = Field(
        ..., min_length=1, max_length=200, description="Name for this schedule"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Optional description"
    )
    schedule_expression: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cron expression (e.g., '0 9 * * 1' for every Monday at 9am)",
    )
    parameters: Optional[dict[str, Any]] = Field(
        None, description="Report-specific parameters/filters"
    )
    recipients: list[EmailStr] = Field(
        ...,
        min_length=1,
        description="List of email addresses to send the report to",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("schedule_expression")
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        """Validate that the schedule expression is a valid cron expression."""
        try:
            croniter(v)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid cron expression: {e}")
        return v


class ReportScheduleUpdateRequest(BaseModel):
    """Request schema for updating a report schedule."""

    name: Optional[str] = Field(
        None, min_length=1, max_length=200, description="Name for this schedule"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Optional description"
    )
    schedule_expression: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Cron expression (e.g., '0 9 * * 1' for every Monday at 9am)",
    )
    parameters: Optional[dict[str, Any]] = Field(
        None, description="Report-specific parameters/filters"
    )
    recipients: Optional[list[EmailStr]] = Field(
        None,
        min_length=1,
        description="List of email addresses to send the report to",
    )
    is_active: Optional[bool] = Field(
        None, description="Whether the schedule is active"
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("schedule_expression")
    @classmethod
    def validate_cron_expression(cls, v: Optional[str]) -> Optional[str]:
        """Validate that the schedule expression is a valid cron expression."""
        if v is not None:
            try:
                croniter(v)
            except (KeyError, ValueError) as e:
                raise ValueError(f"Invalid cron expression: {e}")
        return v


class ReportScheduleResponse(BaseModel):
    """Response schema for a single report schedule."""

    id: UUID
    organization_id: UUID
    created_by_user_id: Optional[UUID] = None
    report_type: str
    name: str
    description: Optional[str] = None
    schedule_expression: str
    is_active: bool
    parameters: Optional[dict[str, Any]] = None
    recipients: Optional[list[str]] = None
    last_run_time: Optional[datetime] = None
    next_run_time: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_error_message: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReportScheduleListResponse(BaseModel):
    """Response schema for paginated list of report schedules."""

    items: list[ReportScheduleResponse]
    total: int = Field(..., description="Total number of matching schedules")
    limit: int = Field(..., description="Number of items per page")
    offset: int = Field(..., description="Number of items skipped")

    model_config = ConfigDict(extra="forbid")


class CreateReportScheduleResponse(BaseModel):
    """Response schema for report schedule creation."""

    message: str
    message_code: str
    schedule: ReportScheduleResponse


class UpdateReportScheduleResponse(BaseModel):
    """Response schema for report schedule update."""

    message: str
    message_code: str
    schedule: ReportScheduleResponse


class DeleteReportScheduleResponse(BaseModel):
    """Response schema for report schedule deletion."""

    message: str
    message_code: str
    schedule_id: UUID
