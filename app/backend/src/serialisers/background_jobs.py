"""
Serializers for background job monitoring endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class JobTypeInfo(BaseModel):
    """Information about a job type."""

    code: str = Field(..., description="Job type code")
    name: str = Field(..., description="Human-readable job name")
    description: str = Field(..., description="Job description")
    category: str = Field(..., description="Job category")
    is_cron: bool = Field(..., description="Whether this is a cron job")
    enabled: bool = Field(True, description="Whether the job is enabled")


class JobTypeStats(BaseModel):
    """Statistics for a single job type."""

    job_type: str = Field(..., description="Job type code")
    name: str = Field(..., description="Human-readable job name")
    description: str = Field(..., description="Job description")
    category: str = Field(..., description="Job category")
    is_cron: bool = Field(..., description="Whether this is a cron job")
    enabled: bool = Field(True, description="Whether the job is enabled")
    executions_24h: int = Field(0, description="Execution count in last 24 hours")
    failures_24h: int = Field(0, description="Failure count in last 24 hours")
    failure_rate: float = Field(0.0, description="Failure rate percentage")
    avg_duration_ms: float = Field(0.0, description="Average execution duration in ms")
    # Populated straight from func.max(BackgroundJobExecution.started_at), a
    # datetime. Pydantic v2 does not coerce datetime -> str, so typing this as
    # str raises a ValidationError for every job that has ever run. Pydantic
    # serialises it to an ISO 8601 string in the JSON response, so the client
    # contract (nullable ISO string) is unchanged.
    last_execution: Optional[datetime] = Field(
        None, description="Timestamp of last execution (ISO 8601 in JSON)"
    )


class JobTypesListResponse(BaseModel):
    """Response for list of job types."""

    items: list[JobTypeInfo] = Field(..., description="List of job types")


class BackgroundJobsStatsResponse(BaseModel):
    """Response for background jobs stats."""

    job_stats: list[JobTypeStats] = Field(..., description="Stats for all job types")
    total_executions_24h: int = Field(0, description="Total executions across all jobs")
    total_failures_24h: int = Field(0, description="Total failures across all jobs")


class StuckJob(BaseModel):
    """Information about a stuck job."""

    job_id: str = Field(..., description="Job ID")
    function: str = Field(..., description="Job function name")
    start_time: str = Field(..., description="ISO timestamp when job started")
    duration_minutes: int = Field(..., description="Duration in minutes")


class QueueHealthResponse(BaseModel):
    """Response for queue health check."""

    is_healthy: bool = Field(..., description="Overall health status")
    issues: list[str] = Field(default_factory=list, description="List of issues found")
    queue_depth: int = Field(0, description="Number of jobs waiting in queue")
    depth_threshold: int = Field(100, description="Queue depth warning threshold")
    stuck_jobs_count: int = Field(0, description="Number of stuck jobs")
    stuck_jobs: list[StuckJob] = Field(
        default_factory=list, description="Details of stuck jobs (first 10)"
    )
    workers_online: int = Field(0, description="Number of online workers")
    workers_offline: int = Field(0, description="Number of offline workers")
    total_workers: int = Field(0, description="Total number of workers")
    checked_at: str = Field(..., description="ISO timestamp of health check")


class ToggleJobTypeRequest(BaseModel):
    """Request to toggle job type enabled status."""

    enabled: bool = Field(..., description="Whether to enable or disable the job type")


class ToggleJobTypeResponse(BaseModel):
    """Response for toggling job type."""

    job_type: str = Field(..., description="Job type code")
    enabled: bool = Field(..., description="New enabled status")
    message: str = Field(..., description="Result message")
