"""
WebSocket API serializer models.
Contains Pydantic models for WebSocket messages, connection metadata, and broadcast payloads.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BroadcastTarget(str, Enum):
    """Target scope for WebSocket message broadcasts."""

    USER = "user"
    ORGANIZATION = "organization"
    PLATFORM = "platform"


class WebSocketMessage(BaseModel):
    """Base model for WebSocket messages sent to clients."""

    type: str = Field(..., description="Message type identifier")
    payload: dict[str, Any] = Field(..., description="Message payload data")
    timestamp: datetime = Field(
        ..., description="ISO8601 timestamp of message creation"
    )

    model_config = ConfigDict(extra="forbid")


class ConnectionMetadata(BaseModel):
    """Metadata for an active WebSocket connection."""

    user_id: UUID = Field(..., description="ID of the connected user")
    organization_id: UUID = Field(..., description="ID of the user's organization")
    connection_id: str = Field(..., description="Unique connection identifier")
    connected_at: datetime = Field(
        ..., description="Timestamp when connection was established"
    )

    model_config = ConfigDict(extra="forbid")


class BroadcastRequest(BaseModel):
    """Request model for broadcasting a WebSocket message."""

    target: BroadcastTarget = Field(..., description="Broadcast target scope")
    target_id: Optional[UUID] = Field(
        None,
        description="Target ID (user_id or organization_id). Required for USER and ORGANIZATION targets.",
    )
    message: WebSocketMessage = Field(..., description="Message to broadcast")

    model_config = ConfigDict(extra="forbid")
