"""Web Push (VAPID) provider configuration — DB-backed with settings fallback.

The startup ``settings.VAPID_*`` (from ``config.json`` / env) are immutable at
runtime, and the ``web_push_provider`` is a process-level singleton. To let a
super-admin manage the keypair *and have it take effect*, the effective config
is resolved here from the SystemConfig store first, falling back to startup
settings. The private key is encrypted at rest (Fernet) because the generic
SystemConfig key-pattern matcher does not treat ``VAPID_PRIVATE_KEY`` as
sensitive.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.encryption import decrypt_field, encrypt_field
from src.crud.system_config import (
    delete_system_config,
    get_system_config_by_key,
    update_system_config,
)
from src.models.web_push_subscription import WebPushSubscription


# SystemConfig keys (upper-snake, mirroring core/config.py settings names).
VAPID_PUBLIC_KEY = "VAPID_PUBLIC_KEY"
VAPID_PRIVATE_KEY = "VAPID_PRIVATE_KEY"
VAPID_SUBJECT = "VAPID_SUBJECT"
# RFC 8292 requires a contact URI so a push service can reach the operator
# about a misbehaving sender. Override with VAPID_SUBJECT per deployment.
DEFAULT_SUBJECT = "mailto:admin@example.com"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_vapid_keypair() -> tuple[str, str]:
    """Generate a P-256 VAPID keypair.

    Returns ``(public_key, private_key)`` as base64url strings: the public key
    is the uncompressed point (the browser ``applicationServerKey``); the
    private key is the raw 32-byte scalar (consumed by ``pywebpush``).
    """
    priv = ec.generate_private_key(ec.SECP256R1())
    pub_point = priv.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    priv_scalar = priv.private_numbers().private_value.to_bytes(32, "big")
    return _b64u(pub_point), _b64u(priv_scalar)


def _safe_decrypt(value: str | None) -> str:
    """Decrypt a stored private key, tolerating a plaintext value.

    A value set through the generic SystemConfig editor is stored plaintext
    (VAPID keys do not match the encryption patterns), so a decrypt failure
    means the value is already plaintext.
    """
    if not value:
        return ""
    try:
        return decrypt_field(value) or ""
    except Exception:
        return value


async def get_web_push_config(session: AsyncSession) -> dict[str, Any]:
    """Resolve the effective Web Push config: DB first, else startup settings."""
    pub_row = await get_system_config_by_key(session, VAPID_PUBLIC_KEY)
    priv_row = await get_system_config_by_key(session, VAPID_PRIVATE_KEY)
    subj_row = await get_system_config_by_key(session, VAPID_SUBJECT)

    pub = (pub_row.value if pub_row else "") or ""
    priv_enc = (priv_row.value if priv_row else "") or ""
    subj = (subj_row.value if subj_row else "") or ""

    if pub or priv_enc:
        return {
            "public_key": pub,
            "private_key": _safe_decrypt(priv_enc),
            "subject": subj or DEFAULT_SUBJECT,
            "source": "database",
        }

    if settings.VAPID_PUBLIC_KEY or settings.VAPID_PRIVATE_KEY:
        return {
            "public_key": settings.VAPID_PUBLIC_KEY,
            "private_key": settings.VAPID_PRIVATE_KEY,
            "subject": settings.VAPID_SUBJECT or DEFAULT_SUBJECT,
            "source": "settings",
        }

    return {
        "public_key": "",
        "private_key": "",
        "subject": DEFAULT_SUBJECT,
        "source": "unset",
    }


async def set_web_push_config(
    session: AsyncSession,
    *,
    public_key: str,
    private_key: str,
    subject: str,
    updated_by_user_id: str | None = None,
) -> None:
    """Persist the VAPID keypair + subject (private key encrypted at rest)."""
    await update_system_config(
        session, VAPID_PUBLIC_KEY, public_key, updated_by_user_id=updated_by_user_id
    )
    await update_system_config(
        session,
        VAPID_PRIVATE_KEY,
        encrypt_field(private_key),
        updated_by_user_id=updated_by_user_id,
    )
    await update_system_config(
        session, VAPID_SUBJECT, subject, updated_by_user_id=updated_by_user_id
    )


async def clear_web_push_config(session: AsyncSession) -> None:
    """Remove the DB-stored VAPID config (reverts to startup settings/unset)."""
    for key in (VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT):
        await delete_system_config(session, key)


async def active_subscription_count(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count())
        .select_from(WebPushSubscription)
        .where(WebPushSubscription.deleted_time.is_(None))
    )
    return int(res.scalar() or 0)


async def purge_all_subscriptions(session: AsyncSession) -> int:
    """Soft-delete all active push subscriptions (after a key rotation)."""
    res = await session.execute(
        select(WebPushSubscription).where(WebPushSubscription.deleted_time.is_(None))
    )
    subs = res.scalars().all()
    now = datetime.now(timezone.utc)
    for sub in subs:
        sub.deleted_time = now
    await session.commit()
    return len(subs)
