"""
CRUD operations for Notification model.

All functions filter by organization_id for multi-tenancy isolation.
Notifications support mixed scope: organization_id=None for system notifications.
"""

from datetime import datetime, timezone
import re
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sort,
    get_total_count,
)
from src.core.query_params import FilterSpec, SortSpec
from src.models.notification import Notification


# SDL configuration for notifications
NOTIFICATION_FILTER_FIELDS = {"channel", "status", "user_id", "created_time"}
NOTIFICATION_FIELD_MAPPING: dict[str, str] = {}


# Marker written in place of a sensitive metadata value.
REDACTED_MARKER = "[redacted]"

# How much of a rendered message body is kept in `notification.body_preview`.
#
# The column is String(500) and the dispatcher used to fill all of it. That
# preview is the single largest deliberate copy of user-facing message content
# in the database, and it is readable by every holder of `notifications:read` -
# a much wider audience than the recipient. Its only job is "which message was
# this?", which a short opening fragment answers just as well as 500
# characters, so the default retains less. Set to 0 in a fork to stop storing
# message content entirely; delivery does not depend on this value (the
# provider is handed the full content before the record is written).
BODY_PREVIEW_MAX_LENGTH = 200

# Maximum nesting depth walked by redact_notification_metadata(). Anything
# deeper is replaced wholesale rather than inspected, so a hostile or cyclic
# structure cannot be used to smuggle a secret past the denylist.
_MAX_REDACTION_DEPTH = 6

# Substring patterns that mark a metadata key as sensitive. Matching is
# case-insensitive and by substring, so "reset_token", "otpCode" and
# "sendgrid_api_key" are all caught.
#
# The list is deliberately over-broad. A false positive costs one missing
# diagnostic value in the notification history; a false negative persists a
# live credential in a column that any holder of `notifications:read` can
# query through GET /notifications.
_SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    # Authentication material handed to users in notifications
    "token",  # password reset / email verification / invitation tokens
    "otp",  # one-time passcodes
    "code",  # verification, invite, recovery and 2FA codes
    "password",  # plaintext or temporary passwords
    "passwd",
    "pwd",
    "passcode",
    "pin",
    # Provider and platform credentials that can appear in send metadata
    "secret",
    "key",  # api_key, sendgrid_api_key, private_key, encryption_key
    "credential",
    "auth",  # authorization headers, auth codes
    "bearer",
    "signature",
    "sig",  # near-miss of "signature": `sig`, `sig_v1`, `x_sig`
    "hmac",
    "jwt",
    "assertion",  # SAML / OAuth client assertions
    "saml",
    "nonce",
    "salt",
    "hash",  # password hashes are still credential-equivalent
    "private",
    "session",  # session identifiers are bearer credentials
    "cookie",
    # Second-factor material. "otp" alone misses every one of these.
    "mfa",
    "2fa",
    "two_factor",
    "twofactor",
    "totp",
    "provisioning",  # otpauth:// provisioning_uri encodes the TOTP secret
    "qr",  # bare `qr`, not just `qr_code`
    "seed",  # seed_phrase / seed
    "phrase",
    "recovery",
    "backup",  # backup_codes
    "challenge",
    # Whole-URL credentials. For these the *entire* value is the secret: the
    # token is often in the path, not a query parameter, so value scrubbing
    # cannot be relied on and the value is dropped outright.
    "magic_link",
    "magiclink",
    "magic_url",
    "invite_url",
    "invite_link",
    "invitation_url",
    "invitation_link",
    "verification_url",
    "verification_link",
    "verify_url",
    "verify_link",
    "activation_url",
    "activation_link",
    "activate_url",
    "activate_link",
    "reset_url",
    "reset_link",
    "confirm_url",
    "confirm_link",
    "confirmation_url",
    "confirmation_link",
    "login_url",
    "login_link",
    "signin_url",
    "signin_link",
    # Payment and identity data that must never land in a queryable column
    "card",
    "cvv",
    "cvc",
    "iban",
    "ssn",
)


def _is_sensitive_key(key: str) -> bool:
    """Return True when a metadata key name matches the sensitive denylist."""
    lowered = key.lower()
    return any(pattern in lowered for pattern in _SENSITIVE_KEY_PATTERNS)


# ---------------------------------------------------------------------------
# Value-level credential scrubbing
# ---------------------------------------------------------------------------
#
# A key denylist can only protect a value that arrives under a name we
# anticipated. It does nothing for:
#
#   * free text - `body_preview`, `subject` and `error_message` are plain
#     strings with no key to inspect, and every OTP path in this codebase puts
#     the live code straight into the message body;
#   * a credential hidden inside an innocuously named value, e.g.
#     `{"action_url": "https://app/reset?token=LIVE"}`.
#
# So each pattern below matches the *shape* of a credential. Every one is
# deliberately narrow: an over-eager pattern that mangles ordinary prose
# destroys the diagnostic value these columns exist for, which is worse than
# not scrubbing at all. Each pattern therefore requires a structural marker
# (a `name=` pair, an auth scheme keyword, a JWT header prefix, a credential
# noun) *and*, where the value could otherwise be an ordinary English word, at
# least one digit.

# Query-string / key-value parameter names whose value is always a credential.
# Any non-empty value is dropped - none of these ever carries diagnostic value.
_ALWAYS_SENSITIVE_PARAM = (
    r"token|secret|password|passwd|pwd|passcode|otp|api[_-]?key|apikey|jwt|hmac"
    r"|signature|sig|assertion|saml[_-]?response|credential|bearer|private[_-]?key"
)

# Parameter names that are *usually* credentials but also appear in benign
# diagnostics ("code=550", "auth=none"). Their value is only dropped when it is
# at least _PARAM_MIN_LENGTH characters, which keeps SMTP reply codes (3
# digits) and Twilio error codes (5 digits) readable while still catching a
# 6-digit OTP or a 32-character reset token.
_MAYBE_SENSITIVE_PARAM = (
    r"key|code|pin|hash|auth|authorization|session|sid|ticket|challenge|nonce"
    r"|seed|recovery|mfa|2fa|two[_-]?factor|magic|invite|invitation|activation"
    r"|verification|totp|qr"
)

_PARAM_MIN_LENGTH = 6

_PARAM_VALUE_RE = re.compile(
    # Not preceded by an alphanumeric, so the optional prefix below is what
    # absorbs `reset_`, `x-`, `access_` etc. rather than matching mid-word.
    r"(?<![A-Za-z0-9])"
    r"([A-Za-z0-9_.\[\]-]*?(?:"
    + _ALWAYS_SENSITIVE_PARAM
    + r"|"
    + _MAYBE_SENSITIVE_PARAM
    + r")[A-Za-z0-9_.\[\]-]*)"
    r"=([^\s&#\"'<>]+)",
    re.IGNORECASE,
)

_ALWAYS_SENSITIVE_PARAM_RE = re.compile(_ALWAYS_SENSITIVE_PARAM, re.IGNORECASE)

# Trailing sentence punctuation is not part of a token value.
_VALUE_TRAILING_PUNCTUATION = ".,;:!?)]}"

# `Authorization: Bearer <blob>` / `Basic <blob>`. The scheme keyword is the
# structural marker. The blob must be 8+ chars AND contain a digit or a
# base64/URL symbol, so ordinary prose ("bearer therefore ...") is untouched.
_AUTH_SCHEME_RE = re.compile(
    r"\b(bearer|basic)(\s+)(?=[A-Za-z0-9._~+/=-]*[0-9._~+/=-])([A-Za-z0-9._~+/=-]{8,})",
    re.IGNORECASE,
)

# A JWT header is always a JSON object, so it always base64url-encodes to a
# string starting `eyJ`. Anchoring on that makes this pattern effectively
# false-positive free while still matching every real JWT.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*")

# "Your verification code is: 483-920" - the exact shape every OTP path in this
# repo sends. A credential *noun* (code/passcode/pin/token/password/otp) is
# required, and a bare "code" only counts when a qualifier precedes it, so
# "error code: 550" and "status code: 404" are left alone. The value must also
# contain a digit, so "authentication token is invalid" survives intact.
_CREDENTIAL_QUALIFIER = (
    r"(?:verification|verify|confirmation|confirm|activation|activate|security"
    r"|login|sign[\s-]?in|access|one[\s-]?time|onetime|single[\s-]?use"
    r"|auth(?:entication)?|recovery|reset|invite|invitation|temporary|temp"
    r"|new|your)"
)
_CREDENTIAL_NOUN = r"(?:code|passcode|pin|password|token|otp)"

_CREDENTIAL_PHRASE_RE = re.compile(
    r"\b("
    r"(?:" + _CREDENTIAL_QUALIFIER + r"[\s-]+" + _CREDENTIAL_NOUN + r""
    r"|otp|passcode|one[\s-]?time\s+(?:code|password|pin))"
    r"(?:\s+(?:is|are|was|reads))?\s*[:=-]?\s*"
    r")"
    r"(\d{3}[\s-]\d{3}|(?=[A-Za-z0-9._-]*\d)[A-Za-z0-9][A-Za-z0-9._-]{3,})",
    re.IGNORECASE,
)

# Backstop for a bare high-entropy blob with no surrounding structure at all -
# a reset token pasted directly into a message body, or sitting in the path
# segment of a link rather than in a query parameter.
#
# `secrets.token_urlsafe(24)` (this repo's reset token) is 32 characters, hence
# the 28-character floor. Requiring both a digit and a letter, and excluding
# the UUID shape, keeps identifiers readable: `enforcement_start_time` and
# `HTTP_INTERNAL_SERVER_ERROR` have no digit, and record UUIDs are exempted
# outright because they are the main way a support engineer follows a trace.
_OPAQUE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?![0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{12}(?![A-Za-z0-9_-]))"
    r"(?=[A-Za-z0-9_-]*[0-9])"
    r"(?=[A-Za-z0-9_-]*[A-Za-z])"
    r"[A-Za-z0-9_-]{28,}"
    r"(?![A-Za-z0-9_-])"
)

# Upper bound on how much text is handed to the regex engine. Longer input is
# truncated first; nothing that is persisted is longer than this anyway.
_SCRUB_INPUT_LIMIT = 8000


def _redact_param(match: "re.Match[str]") -> str:
    """Replace a `name=value` pair's value when the name looks credential-bearing."""
    name, value = match.group(1), match.group(2)

    trailing = ""
    while value and value[-1] in _VALUE_TRAILING_PUNCTUATION:
        trailing = value[-1] + trailing
        value = value[:-1]

    if not value:
        return match.group(0)

    if _ALWAYS_SENSITIVE_PARAM_RE.search(name) or len(value) >= _PARAM_MIN_LENGTH:
        return f"{name}={REDACTED_MARKER}{trailing}"

    return match.group(0)


def scrub_credential_text(
    text: Optional[str], *, preserve_identifiers: bool = False
) -> Optional[str]:
    """
    Remove credential-shaped substrings from a free-text value.

    This is the value-level counterpart to the ``_SENSITIVE_KEY_PATTERNS``
    denylist. It is applied on the persist path only - the provider is always
    handed the original, unscrubbed content, or notifications would become
    undeliverable.

    Args:
        text: The text to scrub. ``None`` and empty strings pass through.
        preserve_identifiers: When True the bare high-entropy-blob backstop is
            skipped. Used for ``error_message``, where long opaque strings are
            usually provider message IDs (a Twilio SID is 34 characters) and
            are the main thing a support engineer needs. The structural
            patterns - ``token=``, ``Bearer``, JWT, "verification code is" -
            still apply there.

    Returns:
        The scrubbed text. Input is never mutated.
    """
    if not text:
        return text

    scrubbed = text[:_SCRUB_INPUT_LIMIT]

    # Order matters: collapse `token=<jwt>` to a single marker before the JWT
    # pattern gets a chance to rewrite only part of it.
    scrubbed = _PARAM_VALUE_RE.sub(_redact_param, scrubbed)
    scrubbed = _AUTH_SCHEME_RE.sub(rf"\1\2{REDACTED_MARKER}", scrubbed)
    scrubbed = _JWT_RE.sub(REDACTED_MARKER, scrubbed)
    scrubbed = _CREDENTIAL_PHRASE_RE.sub(rf"\1{REDACTED_MARKER}", scrubbed)

    if not preserve_identifiers:
        scrubbed = _OPAQUE_TOKEN_RE.sub(REDACTED_MARKER, scrubbed)

    return scrubbed


def prepare_body_preview(content: Optional[str]) -> Optional[str]:
    """
    Turn a rendered message body into the fragment that is safe to persist.

    Scrub first, then truncate: truncating first could sever a credential mid
    token and leave a usable prefix behind.
    """
    if not content:
        return content

    if BODY_PREVIEW_MAX_LENGTH <= 0:
        return None

    scrubbed = scrub_credential_text(content)
    return scrubbed[:BODY_PREVIEW_MAX_LENGTH] if scrubbed else scrubbed


def redact_notification_metadata(metadata: Any, _depth: int = 0) -> Any:
    """
    Strip sensitive values out of notification metadata before persisting it.

    Why this exists
    ---------------
    ``NotificationDispatcher.send_templated_notification`` seeds its metadata
    dict straight from the caller-supplied ``template_vars``. Those variables
    are exactly the values a template needs to render - which, for password
    reset, OTP, email verification and invitation notifications, means live
    reset tokens and one-time codes. That metadata is written to
    ``notification.extra_data`` and handed back verbatim by the notification
    API to any caller holding ``notifications:read``.

    Persisting it unredacted would turn the notification history into a
    long-lived, queryable store of valid credentials, readable by a much wider
    audience than the intended recipient. So values whose key matches the
    denylist are replaced with ``REDACTED_MARKER`` on the way into the
    database. Nothing here changes what is sent to the provider - only what is
    kept afterwards.

    The denylist is intentionally aggressive: when in doubt, redact. Losing a
    diagnostic value is recoverable; storing a credential is not.

    Two layers
    ----------
    1. Key denylist - the value of a credential-named key is dropped whole.
    2. Value scrubbing - every surviving string is passed through
       ``scrub_credential_text``, so a credential hiding in an innocuously
       named value (``{"action_url": "https://app/reset?token=LIVE"}``) is
       caught regardless of its key name. The surrounding URL stays readable;
       only the secret is replaced.

    Args:
        metadata: The metadata value to redact. Dicts and lists are walked
            recursively; anything else is returned unchanged.
        _depth: Internal recursion depth guard.

    Returns:
        A redacted copy of the input. The input is never mutated.
    """
    if _depth > _MAX_REDACTION_DEPTH:
        return REDACTED_MARKER

    if isinstance(metadata, dict):
        redacted: dict[Any, Any] = {}
        for key, value in metadata.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                redacted[key] = REDACTED_MARKER
            else:
                redacted[key] = redact_notification_metadata(value, _depth + 1)
        return redacted

    if isinstance(metadata, (list, tuple)):
        return [redact_notification_metadata(item, _depth + 1) for item in metadata]

    if isinstance(metadata, str):
        return scrub_credential_text(metadata)

    return metadata


async def create_notification(
    session: AsyncSession,
    organization_id: str,
    user_id: Optional[str],
    channel: str,
    recipient: str,
    data: dict[str, Any],
) -> Notification:
    """
    Create a notification record.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (optional - recipient user if known)
        channel: Notification channel ('email', 'sms', 'whatsapp', 'in_app')
        recipient: Recipient address (email or phone number)
        data: Additional notification data including:
            - provider: Provider name (optional)
            - template_id: Template UUID (optional)
            - subject: Email subject (optional). Scrubbed before persisting.
            - body_preview: Rendered message body (optional). Scrubbed, then
              truncated to BODY_PREVIEW_MAX_LENGTH before persisting - pass the
              body and let this function apply the policy.
            - status: Initial status (default: 'pending')
            - bulk_notification_id: Bulk notification UUID (optional)
            - provider_message_id: Message ID returned by the provider (optional)
            - error_message: Failure detail from the provider (optional).
              Scrubbed with preserve_identifiers=True so provider message IDs
              stay readable.
            - metadata: Additional metadata dict (optional). Persisted to the
              `extra_data` column after passing through
              redact_notification_metadata(), which strips tokens, OTPs and
              other credential-shaped values.

    Redaction applies to the PERSIST path only. Callers hand the provider the
    original content before calling this function; nothing here changes what is
    delivered.

    Returns:
        The created Notification instance
    """
    org_uuid = UUID(organization_id) if organization_id else None
    user_uuid = UUID(user_id) if user_id else None
    template_uuid = UUID(data.get("template_id")) if data.get("template_id") else None
    bulk_uuid = (
        UUID(data.get("bulk_notification_id"))
        if data.get("bulk_notification_id")
        else None
    )

    notification = Notification(
        organization_id=org_uuid,
        user_id=user_uuid,
        channel=channel,
        recipient=recipient,
        provider=data.get("provider"),
        template_id=template_uuid,
        # Every persisted free-text column is scrubbed. body_preview is the
        # one that actually carries live OTPs today - every OTP path in this
        # repo puts the code in the message body, not in metadata - but
        # subject and error_message are just as reachable through
        # GET /notifications, so all three get the same treatment.
        subject=scrub_credential_text(data.get("subject")),
        body_preview=prepare_body_preview(data.get("body_preview")),
        status=data.get("status", "pending"),
        bulk_notification_id=bulk_uuid,
        provider_message_id=data.get("provider_message_id"),
        error_message=scrub_credential_text(
            data.get("error_message"), preserve_identifiers=True
        ),
        # NOTE: the column is `extra_data`, not `metadata` - `metadata` is a
        # reserved attribute on SQLAlchemy declarative classes, so assigning it
        # here silently shadows the class attribute and stores NULL.
        extra_data=redact_notification_metadata(data.get("metadata")),
    )

    session.add(notification)
    try:
        await session.commit()
        await session.refresh(notification)
    except Exception as e:
        await session.rollback()
        raise e

    return notification


async def get_notification_by_id(
    session: AsyncSession,
    notification_id: str,
    organization_id: str,
) -> Optional[Notification]:
    """
    Get a single notification by ID within organization context.

    Args:
        session: Database session
        notification_id: Notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)

    Returns:
        The Notification or None if not found
    """
    org_uuid = UUID(organization_id)
    notif_uuid = UUID(notification_id)

    result = await session.execute(
        select(Notification).where(
            Notification.id == notif_uuid,
            Notification.organization_id == org_uuid,
            Notification.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_notifications(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notification], int]:
    """
    Get notifications for an organization with SDL filtering and sorting.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        filters: List of FilterSpec objects for filtering
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results (default: 50)
        offset: Number of results to skip (default: 0)

    Returns:
        Tuple of (list of notifications, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query with organization filter
    base_query = select(Notification).where(
        Notification.organization_id == org_uuid,
        Notification.deleted_time.is_(None),
    )

    # Apply SDL filters
    if filters:
        base_query = apply_filters(
            base_query, Notification, filters, NOTIFICATION_FIELD_MAPPING
        )

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to created_time desc)
    if sorts:
        base_query = apply_sort(
            base_query, Notification, sorts, NOTIFICATION_FIELD_MAPPING
        )
    else:
        base_query = base_query.order_by(Notification.created_time.desc())

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    notifications = result.scalars().all()

    return list(notifications), total_count


async def update_notification_status(
    session: AsyncSession,
    notification_id: str,
    status: str,
    provider_message_id: Optional[str] = None,
    error: Optional[str] = None,
) -> Optional[Notification]:
    """
    Update notification status after send attempt.

    This function does NOT require organization_id since it's called by background
    workers that already have the notification_id. The notification itself contains
    the organization_id for audit purposes.

    Args:
        session: Database session
        notification_id: Notification UUID string
        status: New status ('pending', 'queued', 'sent', 'delivered', 'failed', 'bounced')
        provider_message_id: Message ID from provider (optional)
        error: Error message if failed (optional)

    Returns:
        The updated Notification or None if not found
    """
    notif_uuid = UUID(notification_id)

    result = await session.execute(
        select(Notification).where(
            Notification.id == notif_uuid,
            Notification.deleted_time.is_(None),
        )
    )
    notification = result.scalars().first()

    if not notification:
        return None

    # Update status fields
    notification.status = status

    if provider_message_id:
        notification.provider_message_id = provider_message_id

    if error:
        notification.error_message = scrub_credential_text(
            error, preserve_identifiers=True
        )

    # Update retry tracking if this was a retry
    if status == "failed":
        notification.retry_count = (notification.retry_count or 0) + 1
        notification.last_retry_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(notification)
    except Exception as e:
        await session.rollback()
        raise e

    return notification


async def update_notification_status_by_provider_id(
    session: AsyncSession,
    provider_message_id: str,
    status: str,
    error: Optional[str] = None,
) -> Optional[Notification]:
    """
    Update notification status using the provider's message ID.

    This is used by webhook handlers when providers (like Twilio) send
    status callbacks with their message ID.

    Args:
        session: Database session
        provider_message_id: Message ID from the provider (e.g., Twilio SID)
        status: New status ('pending', 'queued', 'sent', 'delivered', 'failed', 'bounced')
        error: Error message if failed (optional)

    Returns:
        The updated Notification or None if not found
    """
    result = await session.execute(
        select(Notification).where(
            Notification.provider_message_id == provider_message_id,
            Notification.deleted_time.is_(None),
        )
    )
    notification = result.scalars().first()

    if not notification:
        return None

    # Update status fields
    notification.status = status

    if error:
        notification.error_message = scrub_credential_text(
            error, preserve_identifiers=True
        )

    # Update retry tracking if this was a failure
    if status == "failed":
        notification.retry_count = (notification.retry_count or 0) + 1
        notification.last_retry_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(notification)
    except Exception as e:
        await session.rollback()
        raise e

    return notification


async def get_notifications_for_retry(
    session: AsyncSession,
    organization_id: str,
    max_retries: int = 3,
    limit: int = 100,
) -> list[Notification]:
    """
    Get failed notifications eligible for retry.

    Args:
        session: Database session
        organization_id: Organization UUID string
        max_retries: Maximum retry count
        limit: Maximum number of results

    Returns:
        List of notifications eligible for retry
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(Notification)
        .where(
            Notification.organization_id == org_uuid,
            Notification.status == "failed",
            Notification.retry_count < max_retries,
            Notification.deleted_time.is_(None),
        )
        .order_by(Notification.created_time.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def soft_delete_notification(
    session: AsyncSession,
    notification_id: str,
    organization_id: str,
) -> Optional[Notification]:
    """
    Soft delete a notification by setting deleted_time.

    Args:
        session: Database session
        notification_id: Notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)

    Returns:
        The deleted Notification or None if not found
    """
    org_uuid = UUID(organization_id)
    notif_uuid = UUID(notification_id)

    result = await session.execute(
        select(Notification).where(
            Notification.id == notif_uuid,
            Notification.organization_id == org_uuid,
            Notification.deleted_time.is_(None),
        )
    )
    notification = result.scalars().first()

    if not notification:
        return None

    notification.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(notification)
    except Exception as e:
        await session.rollback()
        raise e

    return notification
