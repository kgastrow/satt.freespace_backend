"""Serialisers for the user-facing Web Push subscription API.

The provider-management (VAPID keypair) schemas live in ``serialisers/web_push``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PushSubscriptionKeys(BaseModel):
    """The encryption keys a browser hands out with a ``PushSubscription``."""

    p256dh: str
    auth: str
    model_config = ConfigDict(extra="forbid")


class PushSubscriptionRequest(BaseModel):
    """A serialised browser ``PushSubscription``, registered for this device."""

    endpoint: str = Field(..., min_length=1)
    keys: PushSubscriptionKeys
    # Diagnostic only, and bounded to the column width. `navigator.userAgent`
    # has no upper limit, and a browser that reports more than 255 characters
    # would otherwise be rejected 422 on every retry, from the same device,
    # forever - so the client truncates and this simply agrees with it.
    user_agent: str | None = Field(None, max_length=255)
    model_config = ConfigDict(extra="forbid")


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="forbid")


class VapidKeyResponse(BaseModel):
    """The public half of the VAPID keypair, for ``pushManager.subscribe``."""

    public_key: str


class PushSubscriptionResponse(BaseModel):
    id: UUID
    endpoint: str
    created_time: datetime | None
    model_config = ConfigDict(from_attributes=True)
