"""
Field-level encryption utilities for sensitive data storage.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC) for encrypting
sensitive fields like API keys, passwords, and credentials.

Key Management:
- Primary key (ENCRYPTION_KEY): Used for all new encryptions
- Previous key (ENCRYPTION_KEY_PREVIOUS): Used during key rotation for decryption
- Fallback: If no keys configured, derives from JWT_SECRET (dev only)

Key Rotation Process:
1. Generate new key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
2. Move current ENCRYPTION_KEY to ENCRYPTION_KEY_PREVIOUS
3. Set new key as ENCRYPTION_KEY
4. Run rotation command to re-encrypt all data
5. After verification, clear ENCRYPTION_KEY_PREVIOUS
"""

import base64
from dataclasses import dataclass
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings
from src.logger.logger import Logger as logger


@dataclass
class EncryptionKeyInfo:
    """Information about encryption keys in use."""

    has_primary_key: bool
    has_previous_key: bool
    using_fallback: bool
    key_source: str  # 'config', 'fallback', 'none'


def get_key_info() -> EncryptionKeyInfo:
    """
    Get information about the current encryption key configuration.

    Returns:
        EncryptionKeyInfo with details about configured keys
    """
    has_primary = bool(settings.ENCRYPTION_KEY)
    has_previous = bool(settings.ENCRYPTION_KEY_PREVIOUS)

    if has_primary:
        return EncryptionKeyInfo(
            has_primary_key=True,
            has_previous_key=has_previous,
            using_fallback=False,
            key_source="config",
        )
    else:
        return EncryptionKeyInfo(
            has_primary_key=False,
            has_previous_key=False,
            using_fallback=True,
            key_source="fallback",
        )


def _derive_fallback_key() -> bytes:
    """
    Derive a Fernet-compatible key from the JWT secret.

    This is a fallback for development. In production, use ENCRYPTION_KEY.

    Returns:
        A 32-byte URL-safe base64-encoded key for Fernet
    """
    key_bytes = hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def _get_encryption_keys() -> list[bytes]:
    """
    Get all available encryption keys in priority order.

    Returns:
        List of Fernet-compatible keys [primary, previous, fallback]
    """
    keys = []

    # Primary key from config
    if settings.ENCRYPTION_KEY:
        try:
            # Validate key format
            Fernet(settings.ENCRYPTION_KEY.encode())
            keys.append(settings.ENCRYPTION_KEY.encode())
        except Exception as e:
            logger.error(f"Invalid ENCRYPTION_KEY format: {e}")

    # Previous key for rotation
    if settings.ENCRYPTION_KEY_PREVIOUS:
        try:
            Fernet(settings.ENCRYPTION_KEY_PREVIOUS.encode())
            keys.append(settings.ENCRYPTION_KEY_PREVIOUS.encode())
        except Exception as e:
            logger.error(f"Invalid ENCRYPTION_KEY_PREVIOUS format: {e}")

    # Fallback to JWT-derived key (testing only)
    if not keys:
        if settings.TESTING:
            keys.append(_derive_fallback_key())
        else:
            raise RuntimeError(
                "No ENCRYPTION_KEY configured. "
                "Generate a key with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )

    return keys


def _get_primary_fernet() -> Fernet:
    """Get Fernet instance for the primary (current) encryption key."""
    keys = _get_encryption_keys()
    return Fernet(keys[0])


def _get_all_fernets() -> list[Fernet]:
    """Get Fernet instances for all available keys (for decryption)."""
    return [Fernet(key) for key in _get_encryption_keys()]


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """
    Encrypt a string value for storage in the database.

    Always uses the primary (current) encryption key.

    Args:
        value: The plaintext value to encrypt. If None or empty, returns None.

    Returns:
        The encrypted value as a base64-encoded string, or None if input is None/empty.

    Raises:
        ValueError: If encryption fails

    Example:
        >>> encrypted = encrypt_field("my_api_key_123")
        >>> print(encrypted)  # "gAAAAABh..."
    """
    if not value:
        return None

    try:
        fernet = _get_primary_fernet()
        encrypted_bytes = fernet.encrypt(value.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise ValueError("Failed to encrypt value") from e


def decrypt_field(encrypted_value: Optional[str]) -> Optional[str]:
    """
    Decrypt an encrypted string value from the database.

    Tries all available keys in order: primary, previous, fallback.
    This enables seamless key rotation.

    Args:
        encrypted_value: The encrypted value to decrypt. If None or empty, returns None.

    Returns:
        The decrypted plaintext value, or None if input is None/empty.

    Raises:
        ValueError: If decryption fails with all available keys

    Example:
        >>> decrypted = decrypt_field(encrypted_value)
        >>> print(decrypted)  # "my_api_key_123"
    """
    if not encrypted_value:
        return None

    fernets = _get_all_fernets()
    last_error = None

    for i, fernet in enumerate(fernets):
        try:
            decrypted_bytes = fernet.decrypt(encrypted_value.encode("utf-8"))
            if i > 0:
                logger.info(
                    f"Decrypted with key #{i + 1} (not primary). "
                    "Consider running key rotation to re-encrypt with primary key."
                )
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            last_error = "Invalid token"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    logger.error(f"Decryption failed with all keys: {last_error}")
    raise ValueError("Failed to decrypt value: invalid token or wrong key")


def rotate_encrypted_value(
    encrypted_value: Optional[str],
) -> tuple[Optional[str], bool]:
    """
    Re-encrypt a value with the current primary key.

    Used during key rotation to update all encrypted values.

    Args:
        encrypted_value: The currently encrypted value

    Returns:
        Tuple of (new_encrypted_value, was_rotated)
        - new_encrypted_value: Value encrypted with primary key
        - was_rotated: True if the value was re-encrypted, False if already using primary key

    Raises:
        ValueError: If decryption fails
    """
    if not encrypted_value:
        return None, False

    # Try to decrypt with primary key first
    primary_fernet = _get_primary_fernet()
    try:
        primary_fernet.decrypt(encrypted_value.encode("utf-8"))
        # Already encrypted with primary key
        return encrypted_value, False
    except InvalidToken:
        pass

    # Decrypt with any available key and re-encrypt with primary
    decrypted = decrypt_field(encrypted_value)
    new_encrypted = encrypt_field(decrypted)
    return new_encrypted, True


def mask_credential(value: Optional[str], visible_chars: int = 4) -> Optional[str]:
    """
    Mask a credential for display purposes.

    Shows only the last N characters, replacing the rest with asterisks.

    Args:
        value: The value to mask. If None or empty, returns None.
        visible_chars: Number of characters to show at the end (default: 4)

    Returns:
        The masked value (e.g., "**************cdef"), or None if input is None/empty.

    Example:
        >>> mask_credential("sk-1234567890abcdef")
        "**************cdef"
    """
    if not value:
        return None

    if len(value) <= visible_chars:
        return "*" * len(value)

    masked_length = len(value) - visible_chars
    return "*" * masked_length + value[-visible_chars:]


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        A new Fernet-compatible encryption key as a string

    Example:
        >>> key = generate_encryption_key()
        >>> print(key)  # "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY="
    """
    return Fernet.generate_key().decode()


def validate_encryption_key(key: str) -> bool:
    """
    Validate that a string is a valid Fernet encryption key.

    Args:
        key: The key string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        Fernet(key.encode())
        return True
    except Exception:
        return False
