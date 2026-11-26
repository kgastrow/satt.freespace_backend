"""Serialisers for the ingest-key and app-key admin API (M2).

No response model carries a key hash. The plaintext key appears only in the
``Create...Response`` models, once, at creation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.datetime_utils import serialize_datetime, serialize_datetime_required
from src.models.app_key import AppKey
from src.models.ingest_key import IngestKey
from src.services.freespace.clock import ensure_utc


class CreateIngestKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    expires_at: datetime | None = Field(None, description="Optional expiry (future)")

    model_config = ConfigDict(extra="forbid")


class IngestKeyResponse(BaseModel):
    """An ingest key as listed: never the hash or plaintext."""

    id: str
    site_id: str
    name: str
    key_hint: str
    expires_at: str | None = None
    revoked_at: str | None = None
    last_used_at: str | None = None
    last_used_ip: str | None = None
    created_by: str | None = None
    created_time: str


class ListIngestKeysResponse(BaseModel):
    items: list[IngestKeyResponse]


class CreateIngestKeyResponse(IngestKeyResponse):
    """Create response: ``key`` is the plaintext, shown exactly once."""

    key: str
    message: str
    message_code: str


class RevokeIngestKeyResponse(BaseModel):
    key: IngestKeyResponse
    message: str
    message_code: str


class CreateAppKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

    model_config = ConfigDict(extra="forbid")


class AppKeyResponse(BaseModel):
    id: str
    name: str
    key_hint: str
    revoked_at: str | None = None
    created_by: str | None = None
    created_time: str


class ListAppKeysResponse(BaseModel):
    items: list[AppKeyResponse]


class CreateAppKeyResponse(AppKeyResponse):
    key: str
    message: str
    message_code: str


class RevokeAppKeyResponse(BaseModel):
    key: AppKeyResponse
    message: str
    message_code: str


def _iso(value: datetime | None) -> str | None:
    return serialize_datetime(ensure_utc(value)) if value else None


def serialise_ingest_key(row: IngestKey) -> IngestKeyResponse:
    return IngestKeyResponse(
        id=str(row.id),
        site_id=str(row.site_id),
        name=row.name,
        key_hint=row.key_hint,
        expires_at=_iso(row.expires_at),
        revoked_at=_iso(row.revoked_at),
        last_used_at=_iso(row.last_used_at),
        last_used_ip=row.last_used_ip,
        created_by=str(row.created_by) if row.created_by else None,
        created_time=serialize_datetime_required(
            ensure_utc(row.created_time) if row.created_time else None
        ),
    )


def serialise_app_key(row: AppKey) -> AppKeyResponse:
    return AppKeyResponse(
        id=str(row.id),
        name=row.name,
        key_hint=row.key_hint,
        revoked_at=_iso(row.revoked_at),
        created_by=str(row.created_by) if row.created_by else None,
        created_time=serialize_datetime_required(
            ensure_utc(row.created_time) if row.created_time else None
        ),
    )
