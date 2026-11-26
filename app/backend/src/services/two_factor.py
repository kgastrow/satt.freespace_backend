"""
Two-Factor Authentication Service.
Handles TOTP generation, verification, and backup code management.
"""

import secrets
import string

import pyotp

from src.core.security import hash_password, verify_password


class TwoFactorService:
    """Service for managing TOTP and backup codes for 2FA."""

    @staticmethod
    def generate_secret() -> str:
        """
        Generate a random base32 secret for TOTP.

        Returns:
            Base32-encoded secret string
        """
        return pyotp.random_base32()

    @staticmethod
    def generate_provisioning_uri(
        secret: str, email: str, issuer: str = "FREESPACE"
    ) -> str:
        """
        Generate a provisioning URI for QR code display.

        Args:
            secret: Base32-encoded TOTP secret
            email: User's email address
            issuer: Issuer name (default: FREESPACE)

        Returns:
            otpauth:// URI string
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)

    @staticmethod
    def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
        """
        Verify a TOTP code against the secret.

        Args:
            secret: Base32-encoded TOTP secret
            code: 6-digit TOTP code to verify
            valid_window: Number of time windows to check (default: 1, allows 30s drift)

        Returns:
            True if code is valid, False otherwise
        """
        if not code or len(code) != 6 or not code.isdigit():
            return False

        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=valid_window)

    @staticmethod
    def generate_backup_codes(count: int = 10) -> tuple[list[str], list[str]]:
        """
        Generate cryptographically random backup codes.

        Args:
            count: Number of backup codes to generate (default: 10)

        Returns:
            Tuple of (plain_codes, hashed_codes) where:
            - plain_codes: List of 8-character alphanumeric codes for display
            - hashed_codes: List of bcrypt hashed codes for storage
        """
        plain_codes = []
        hashed_codes = []

        alphabet = string.ascii_uppercase + string.digits
        for _ in range(count):
            # Generate 8-character alphanumeric code
            plain_code = "".join(secrets.choice(alphabet) for _ in range(8))
            plain_codes.append(plain_code)

            # Hash the code for storage
            hashed_code = hash_password(plain_code)
            hashed_codes.append(hashed_code)

        return plain_codes, hashed_codes

    @staticmethod
    def verify_backup_code(plain_code: str, hashed_code: str) -> bool:
        """
        Verify a backup code against its hash.

        Args:
            plain_code: Plain text backup code from user
            hashed_code: Hashed backup code from database

        Returns:
            True if code matches, False otherwise
        """
        return verify_password(plain_code, hashed_code)
