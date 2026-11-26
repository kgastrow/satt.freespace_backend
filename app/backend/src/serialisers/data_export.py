from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DataExportRequestResponse(BaseModel):
    """Response model for a single data export request."""

    id: UUID
    status: str
    file_size_bytes: Optional[int]
    expires_at: Optional[datetime]
    completed_at: Optional[datetime]
    download_count: int
    created_time: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateExportRequestResponse(BaseModel):
    """Response when creating a new export request."""

    message: str
    message_code: str
    request_id: UUID


class ListExportRequestsResponse(BaseModel):
    """Response for listing export requests with pagination."""

    items: list[DataExportRequestResponse]
    total: int
    limit: int
    offset: int


class ExportDownloadUrlResponse(BaseModel):
    """Response containing a signed download URL."""

    message: str
    message_code: str
    download_url: str
    expires_at: datetime


class DataDeletionRequestResponse(BaseModel):
    """Response model for a data deletion request."""

    id: UUID
    status: str
    scheduled_hard_delete_at: Optional[datetime]
    hard_deleted_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancellation_reason: Optional[str]
    created_time: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateDeletionRequestResponse(BaseModel):
    """Response when creating a new deletion request."""

    message: str
    message_code: str
    request_id: UUID
    scheduled_hard_delete_at: datetime


class CancelDeletionRequestResponse(BaseModel):
    """Response when cancelling a deletion request."""

    message: str
    message_code: str


class GetDeletionStatusResponse(BaseModel):
    """Response for getting deletion status."""

    has_active_request: bool
    request: Optional[DataDeletionRequestResponse]
