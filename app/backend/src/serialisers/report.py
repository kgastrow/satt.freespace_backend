"""
Pydantic serializers for Report API endpoints.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportCreateRequest(BaseModel):
    """Request schema for creating a report."""

    report_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Type of report to generate (e.g., 'users_report')",
    )
    name: str = Field(
        ..., min_length=1, max_length=200, description="Name for this report"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Optional description"
    )
    parameters: Optional[dict[str, Any]] = Field(
        None, description="Report-specific parameters/filters"
    )

    model_config = ConfigDict(extra="forbid")


class ReportResponse(BaseModel):
    """Response schema for a single report."""

    id: UUID
    organization_id: UUID
    generated_by_user_id: Optional[UUID] = None
    report_type: str
    name: str
    description: Optional[str] = None
    parameters: Optional[dict[str, Any]] = None
    status: str
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_id: Optional[UUID] = None
    row_count: Optional[int] = None
    schedule_id: Optional[UUID] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    # Computed field for download URL (populated by API)
    download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReportListResponse(BaseModel):
    """Response schema for paginated list of reports."""

    items: list[ReportResponse]
    total: int = Field(..., description="Total number of matching reports")
    limit: int = Field(..., description="Number of items per page")
    offset: int = Field(..., description="Number of items skipped")

    model_config = ConfigDict(extra="forbid")


class ReportTypeResponse(BaseModel):
    """Response schema for a single report type."""

    code: str = Field(..., description="Report type code (e.g., 'users_report')")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Description of what the report contains")

    model_config = ConfigDict(extra="forbid")


class ReportTypesListResponse(BaseModel):
    """Response schema for list of available report types."""

    items: list[ReportTypeResponse]

    model_config = ConfigDict(extra="forbid")


class CreateReportResponse(BaseModel):
    """Response schema for report creation."""

    message: str
    message_code: str
    report: ReportResponse


class DeleteReportResponse(BaseModel):
    """Response schema for report deletion."""

    message: str
    message_code: str
    report_id: UUID
