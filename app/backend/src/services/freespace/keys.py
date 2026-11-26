"""
Key and device-id helpers (BF-10a, D3, D5, BF-35). Fully implemented.

* Ingest keys: ``fsk_`` + 43 base64url characters (256 bits of randomness),
  well inside ParkIT's ``^[\\x21-\\x7e]{1,512}$`` (BF-10a).
* App keys: ``fsa_`` + 43 base64url characters.
* Keys and device ids are stored only as SHA-256 hex digests. SHA-256 (not
  bcrypt) is sufficient because the inputs are high-entropy, and the lookup
  must be an exact index match (D3).
* Never log a plaintext key, a device id or an FCM token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from src.constants.freespace import (
    APP_KEY_PREFIX,
    DEVICE_ID_RE,
    DEVICE_ID_SUFFIX_LENGTH,
    INGEST_KEY_FORMAT_RE,
    INGEST_KEY_PREFIX,
    KEY_HINT_LENGTH,
)


_KEY_RANDOM_BYTES = 32  # 256 bits -> 43 base64url characters


def _generate(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(_KEY_RANDOM_BYTES)


def generate_ingest_key() -> str:
    """A new plaintext ingest key (``fsk_...``). Show it once, store its hash."""
    return _generate(INGEST_KEY_PREFIX)


def generate_app_key() -> str:
    """A new plaintext app key (``fsa_...``). Show it once, store its hash."""
    return _generate(APP_KEY_PREFIX)


def hash_key(plaintext: str) -> str:
    """SHA-256 hex digest (64 chars) of a key; the stored ``key_hash``."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def key_hint(plaintext: str) -> str:
    """Last ``KEY_HINT_LENGTH`` characters, for display next to a key."""
    return plaintext[-KEY_HINT_LENGTH:]


def is_valid_key_format(value: str) -> bool:
    """BF-10a: 1-512 printable ASCII characters with no space."""
    return bool(INGEST_KEY_FORMAT_RE.fullmatch(value))


def keys_equal(a: str, b: str) -> bool:
    """Constant-time comparison of two hashes or keys."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def is_valid_device_id(device_id: str) -> bool:
    """BF-33: ``^[A-Za-z0-9_-]{22,64}$``."""
    return bool(DEVICE_ID_RE.fullmatch(device_id))


def hash_device_id(device_id: str) -> str:
    """SHA-256 hex of a deviceId: the stored ``device.device_key_hash`` (D5).

    Also the value to use wherever a device must be keyed without exposing
    its id (e.g. the per-deviceId rate-limit ``key_func``, BF-36).
    """
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()


def device_id_suffix(device_id: str) -> str:
    """Last 6 characters of a deviceId (``device.id_suffix``, BF-74)."""
    return device_id[-DEVICE_ID_SUFFIX_LENGTH:]
