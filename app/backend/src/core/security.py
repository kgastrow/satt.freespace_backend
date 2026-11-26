"""
JWT token handling and password security utilities for FastAPI.

Provides functions for:
- Creating and decoding JWT access/refresh tokens
- Password hashing and verification using bcrypt
- Token validation and expiration handling

Uses PyJWT and bcrypt for cryptographic operations.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.core.config import settings


# ---------------------------------------------------------------------------
# JWT clock-skew policy
# ---------------------------------------------------------------------------
# PyJWT >= 2.10 validates the ``iat`` (issued-at) claim with ZERO tolerance:
# ``if iat > now: raise ImmatureSignatureError``. ``ImmatureSignatureError``
# subclasses ``InvalidTokenError``, which every decode site in this codebase
# maps to "invalid token" (HTTP 401 ``auth.invalid_token``, a rejected
# unsubscribe link, a failed SSO callback, ...).
#
# That makes authentication fail on a token minted seconds earlier whenever the
# validating host's clock is BEHIND the minting host's: an NTP correction, a VM
# migration, a hypervisor pause/resume, or simply two app hosts whose clocks
# differ by a second. The token is perfectly valid; only our clock moved.
#
# Fix: stop treating ``iat`` as a validity constraint. RFC 7519 s4.1.6 defines
# ``iat`` as informational -- "can be used to determine the age of the JWT" --
# and NOT as a bound on when the token becomes usable. s4.1.5 ``nbf`` is the
# claim that means "not valid before"; s4.1.4 ``exp`` is the claim that means
# "not valid after". Both remain verified here, with zero leeway.
#
# Deliberately NOT using PyJWT's ``leeway=N``: leeway is not per-claim
# (``jwt/api_jwt.py`` passes the same value to the ``exp``, ``nbf`` and ``iat``
# checks), so ``leeway=30`` would also keep EXPIRED tokens accepted for 30 extra
# seconds -- weakening logout, session revocation and every short-lived
# capability token. Disabling the ``iat`` immaturity check removes the false
# rejection without extending any token's lifetime by a single second.
#
# Note this only skips the range check; the ``iat`` value itself is still
# returned in the payload, so any application-level use of it is unaffected.
JWT_DECODE_OPTIONS: dict[str, bool] = {"verify_iat": False}


def jwt_decode_options(**overrides: bool) -> dict[str, bool]:
    """Return the project-standard ``jwt.decode`` options.

    Every ``jwt.decode`` call in this codebase must pass ``options=`` from this
    helper so the ``iat`` policy above is applied uniformly and a new call site
    cannot silently reintroduce the clock-skew failure.

    Args:
        **overrides: Per-call PyJWT option overrides (e.g. ``verify_exp=False``
            when peeking at an expiry). Overrides are merged on top of the
            shared policy, so a caller that already needs a non-default option
            keeps it *and* gets the ``iat`` policy.

    Returns:
        A fresh options dict on every call -- never the shared
        ``JWT_DECODE_OPTIONS`` constant -- so a caller that mutates the result
        cannot change the policy for everybody else.

    Warning:
        Never call this with ``verify_signature=False`` on a token that is
        about to be trusted. Disabling signature verification turns the decode
        into "parse whatever the client sent"; the only legitimate use is
        inspecting a token this process is NOT going to act on (see
        :func:`get_token_expiry`).
    """
    return {**JWT_DECODE_OPTIONS, **overrides}


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a hashed password.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    user_id: str, organization_id: str, extra_claims: Optional[dict[str, Any]] = None
) -> str:
    """
    Create a JWT access token with user and organization context.

    Args:
        user_id: User's unique identifier (UUID string)
        organization_id: Organization's unique identifier (UUID string)
        extra_claims: Optional additional claims to include in token

    Returns:
        Encoded JWT token string

    Example:
        token = create_access_token("user-uuid", "org-uuid", {"email": "user@example.com"})
    """
    expiry = datetime.now(timezone.utc) + timedelta(
        seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS
    )

    payload = {
        "user_id": str(user_id),
        "organization_id": str(organization_id),
        "exp": expiry,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    # Add any extra claims
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, organization_id: str) -> str:
    """
    Create a JWT refresh token for renewing access tokens.

    Refresh tokens have a longer expiration time and contain minimal claims.

    Args:
        user_id: User's unique identifier (UUID string)
        organization_id: Organization's unique identifier (UUID string)

    Returns:
        Encoded JWT refresh token string
    """
    expiry = datetime.now(timezone.utc) + timedelta(
        seconds=settings.REFRESH_TOKEN_EXPIRE_SECONDS
    )

    payload = {
        "user_id": str(user_id),
        "organization_id": str(organization_id),
        "exp": expiry,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_impersonation_token(
    user_id: str,
    organization_id: str,
    impersonator_id: str,
    impersonation_session_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT token with impersonation context.

    This token contains the target user's identity but also includes the
    original admin's ID for audit traceability.

    Args:
        user_id: ID of the user being impersonated
        organization_id: Organization ID of the target user
        impersonator_id: ID of the super admin performing impersonation
        impersonation_session_id: ID of the impersonation session
        expires_delta: Optional custom expiration time

    Returns:
        JWT token string containing impersonation context
    """
    # Use shorter expiration for impersonation tokens (1 hour default)
    # This limits the window of opportunity if token is compromised
    if expires_delta is None:
        expires_delta = timedelta(seconds=settings.IMPERSONATION_TOKEN_EXPIRE_SECONDS)

    payload = {
        "user_id": user_id,
        "organization_id": organization_id,
        "impersonator_id": impersonator_id,
        "impersonation_session_id": impersonation_session_id,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
        "type": "impersonation",
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        Dictionary containing token payload/claims

    Raises:
        ValueError: If token is expired or invalid

    Example:
        try:
            claims = decode_token(token)
            user_id = claims["user_id"]
        except ValueError as e:
            # Handle invalid token
            pass
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options=jwt_decode_options(),
        )
        return payload
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}")


def get_token_expiry(token: str) -> Optional[int]:
    """
    Get the expiration timestamp from a JWT token without full validation.

    Useful for cache TTL calculations.

    Args:
        token: JWT token string

    Returns:
        Unix timestamp of token expiration, or None if not found
    """
    try:
        # Decode without verification to peek at expiry
        # Peek only: this payload is never trusted, it just feeds a cache TTL.
        # verify_signature/verify_exp must stay False here (foreign and expired
        # tokens are legitimate input); they are MERGED with the shared iat
        # policy rather than replacing it.
        unverified = jwt.decode(
            token,
            options=jwt_decode_options(verify_signature=False, verify_exp=False),
        )
        return unverified.get("exp")
    except Exception:
        return None


def get_api_key_identifier(api_key_id: str, organization_id: str) -> str:
    """
    Generate a unique identifier for API key rate limiting.

    Args:
        api_key_id: API key UUID
        organization_id: Organization UUID

    Returns:
        Unique identifier string for rate limiting

    Note:
        This identifier can be used with SlowAPI or custom rate limiting
        to apply per-API-key limits. Configuration is managed separately.
    """
    return f"api_key:{organization_id}:{api_key_id}"


def create_file_access_token(
    storage_key: str,
    organization_id: str,
    expires_in_seconds: int = 3600,
) -> str:
    """
    Create a short-lived JWT token for file access.

    This token is used for local file storage to allow authenticated access
    via URL query parameter (similar to S3 presigned URLs).

    Args:
        storage_key: The storage key of the file
        organization_id: Organization ID that owns the file
        expires_in_seconds: Token expiration time in seconds (default 1 hour)

    Returns:
        Encoded JWT token string
    """
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

    payload = {
        "storage_key": storage_key,
        "organization_id": str(organization_id),
        "exp": expiry,
        "iat": datetime.now(timezone.utc),
        "type": "file_access",
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_file_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a file access token.

    Args:
        token: JWT token string to decode

    Returns:
        Dictionary containing token payload with storage_key and organization_id

    Raises:
        ValueError: If token is expired, invalid, or not a file_access token
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options=jwt_decode_options(),
        )
        if payload.get("type") != "file_access":
            raise ValueError("Invalid token type")
        return payload
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except InvalidTokenError as e:
        raise ValueError(f"Invalid token: {str(e)}")
