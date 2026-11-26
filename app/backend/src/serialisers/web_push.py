"""Serialisers for the Web Push (VAPID) provider-management surface.

The provider's signing keys live in the SystemConfig store (see
``services/notifications/web_push_config``). These models never carry the VAPID
*private* key back to a client — status only reports whether it is configured;
the one place a private key is returned is the ``generate`` preview, which does
not persist it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class WebPushProviderStatusResponse(BaseModel):
    """Current Web Push provider configuration (no private key)."""

    configured: bool
    public_key: str | None = None
    subject: str
    private_key_configured: bool
    # Where the effective config is resolved from: "database" (admin-set),
    # "settings" (config.json / env), or "unset".
    source: str
    active_subscriptions: int


class GenerateVapidKeyResponse(BaseModel):
    """A freshly generated VAPID keypair (preview only — not persisted)."""

    public_key: str
    private_key: str
    subject_suggestion: str
    warning: str


class SetWebPushProviderRequest(BaseModel):
    """Persist a VAPID keypair + subject for the Web Push channel."""

    public_key: str = Field(min_length=1)
    private_key: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    # Rotating the keypair invalidates every existing subscription; the caller
    # opts in to soft-deleting them so stale rows are not retried forever.
    purge_subscriptions: bool = False

    @field_validator("subject")
    @classmethod
    def _subject_is_uri(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("mailto:") or v.startswith("https://")):
            raise ValueError("subject must be a 'mailto:' or 'https://' URI")
        return v
