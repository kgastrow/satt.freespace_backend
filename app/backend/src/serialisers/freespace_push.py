"""Admin serialisers for test push and announcements (M8). snake_case.

Wording (BF-69): "accepted by FCM", never "delivered". Responses never echo a
device id, suffix or token.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class TestPushRequest(BaseModel):
    """``target=device`` needs ``device_suffix`` (last 6 characters of the id
    shown in the app's settings); ``target=topic`` needs ``confirm_topic``
    repeating the site's topic name exactly."""

    __test__ = False  # not a pytest class

    target: Literal["device", "topic"]
    device_suffix: StrictStr | None = Field(None, max_length=6)
    confirm_topic: StrictStr | None = Field(None, max_length=255)
    model_config = ConfigDict(extra="forbid")


class AnnouncementRequest(BaseModel):
    message: StrictStr = Field(..., min_length=1, max_length=500)
    title: StrictStr | None = Field(None, max_length=65)
    confirm_topic: StrictStr | None = Field(None, max_length=255)
    model_config = ConfigDict(extra="forbid")


class PushResponse(BaseModel):
    message: str
    message_code: str
    event_id: UUID
    target: Literal["device", "topic"]
    outcome: str  # ACCEPTED_BY_FCM
    accepted_by_fcm: bool
    latency_ms: int
