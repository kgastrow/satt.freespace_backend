"""
Pydantic serializers for CronJob API endpoints.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.crud.cron_job import is_valid_cron_expression


class CreateCronJobRequest(BaseModel):
    """Request schema for creating a cron job definition"""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    code: str = Field(
        ..., min_length=1, max_length=100, description="Unique identifier for job type"
    )
    schedule_expression: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cron expression (e.g., '0 2 * * *')",
    )
    is_active: bool = Field(default=True)
    is_enabled_by_default_for_new_orgs: bool = Field(default=False)
    parameters: Optional[dict[str, Any]] = Field(
        None, description="Job-specific parameters as JSON"
    )
    is_platform_wide: bool = Field(
        default=False,
        description="If True, create platform-wide job (super admin only)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("schedule_expression")
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        """Validate that the cron expression is valid."""
        if not is_valid_cron_expression(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        """Validate that code contains only alphanumeric characters, underscores, and hyphens."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Code must contain only alphanumeric characters, underscores, and hyphens"
            )
        return v


class UpdateCronJobRequest(BaseModel):
    """Request schema for updating a cron job definition"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    schedule_expression: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    is_enabled_by_default_for_new_orgs: Optional[bool] = None
    parameters: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("schedule_expression")
    @classmethod
    def validate_cron_expression(cls, v: Optional[str]) -> Optional[str]:
        """Validate that the cron expression is valid if provided."""
        if v is not None and not is_valid_cron_expression(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v


class CronJobResponse(BaseModel):
    """Response schema for a single cron job definition"""

    id: UUID
    organization_id: Optional[UUID]
    name: str
    description: Optional[str]
    code: str
    schedule_expression: str
    is_active: bool
    is_enabled_by_default_for_new_orgs: bool
    parameters: Optional[dict[str, Any]]
    last_run_time: Optional[datetime]
    next_run_time: Optional[datetime]
    last_run_status: str
    last_run_error_message: Optional[str]
    created_time: Optional[datetime]
    updated_time: Optional[datetime]
    is_platform_wide: bool = Field(
        default=False, description="True if organization_id is None"
    )
    # Execution stats (last 24 hours)
    executions_24h: int = Field(
        default=0, description="Number of executions in the last 24 hours"
    )
    failures_24h: int = Field(
        default=0, description="Number of failures in the last 24 hours"
    )
    failure_rate: float = Field(
        default=0.0, description="Failure rate percentage (0-100)"
    )
    avg_duration_ms: Optional[float] = Field(
        default=None, description="Average execution duration in milliseconds"
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_cron_job(
        cls,
        job,
        executions_24h: int = 0,
        failures_24h: int = 0,
        failure_rate: float = 0.0,
        avg_duration_ms: Optional[float] = None,
    ):
        """Convert CronJobDefinition ORM object to response with optional stats"""
        return cls(
            id=job.id,
            organization_id=job.organization_id,
            name=job.name,
            description=job.description,
            code=job.code,
            schedule_expression=job.schedule_expression,
            is_active=job.is_active,
            is_enabled_by_default_for_new_orgs=job.is_enabled_by_default_for_new_orgs,
            parameters=job.parameters,
            last_run_time=job.last_run_time,
            next_run_time=job.next_run_time,
            last_run_status=job.last_run_status,
            last_run_error_message=job.last_run_error_message,
            created_time=job.created_time,
            updated_time=job.updated_time,
            is_platform_wide=job.organization_id is None,
            executions_24h=executions_24h,
            failures_24h=failures_24h,
            failure_rate=failure_rate,
            avg_duration_ms=avg_duration_ms,
        )


class CronJobListResponse(BaseModel):
    """Response schema for list of cron jobs with pagination"""

    items: list[CronJobResponse]
    total: int
    limit: int
    offset: int


class CronJobExecutionResponse(BaseModel):
    """Response schema for a single cron job execution"""

    id: UUID
    cron_job_id: UUID
    organization_id: Optional[UUID]
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    result: Optional[dict[str, Any]]
    error_message: Optional[str]
    created_time: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CronJobExecutionListResponse(BaseModel):
    """Response schema for list of cron job executions with pagination"""

    items: list[CronJobExecutionResponse]
    total: int
    limit: int
    offset: int


class ToggleCronJobRequest(BaseModel):
    """Request schema for toggling cron job active status"""

    is_active: bool

    model_config = ConfigDict(extra="forbid")


class TriggerCronJobRequest(BaseModel):
    """Request schema for manually triggering a cron job"""

    model_config = ConfigDict(extra="forbid")


class TriggerCronJobResponse(BaseModel):
    """Response schema for manually triggering a cron job"""

    message: str
    message_code: str
    execution_id: UUID


class CronJobConfigKeyResponse(BaseModel):
    """Response schema for a single config key associated with a cron job"""

    key: str
    value_type: str  # "integer", "string", "boolean", "float"
    default: Optional[Any]
    current_value: Optional[Any]
    label: str
    description: str
    min_value: Optional[int] = None
    max_value: Optional[int] = None


class CronJobConfigResponse(BaseModel):
    """Response schema for cron job configuration"""

    job_code: str
    has_config: bool
    config_keys: list[CronJobConfigKeyResponse]


class UpdateCronJobConfigRequest(BaseModel):
    """Request schema for updating a cron job config value"""

    key: str
    value: str

    model_config = ConfigDict(extra="forbid")
