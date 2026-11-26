"""
Freespace shared constants and enums.

Single source of truth for every string value that is stored in a Freespace
table or sent on the wire. Requirement ids (BF-x) refer to
``specs/BACKEND_FUNCTIONAL_DESCRIPTION.md``; design ids (Dx) to
``specs/freespace_backend_implementation_plan.md``.

All enums are ``StrEnum`` so a member compares equal to its stored string and
serialises as that string in JSON and Pydantic.
"""

from enum import StrEnum
import re
from typing import Any, Final


# ─────────────────────────────────────────────────────────────
# Engine / availability enums
# ─────────────────────────────────────────────────────────────


class EngineState(StrEnum):
    """Site state machine (BF-52)."""

    IDLE = "IDLE"
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"


class AdvisoryType(StrEnum):
    """Push message kinds that go to device tokens (spec §3, BF-60).

    ``ANNOUNCEMENT`` is deliberately NOT an advisory: it is a topic message,
    no limits apply and it is recorded as ``EventType.ANNOUNCEMENT``.
    """

    SITE_INITIAL = "SITE_INITIAL"
    SITE_CHANGE = "SITE_CHANGE"
    ZONE_ADVISORY = "ZONE_ADVISORY"
    RECOVERY = "RECOVERY"
    TEST = "TEST"


# Advisory types that have a per-site message template (BF-70). TEST has one
# too so the test-push wording is editable like the others.
TEMPLATED_ADVISORY_TYPES: Final[tuple[AdvisoryType, ...]] = (
    AdvisoryType.SITE_INITIAL,
    AdvisoryType.SITE_CHANGE,
    AdvisoryType.ZONE_ADVISORY,
    AdvisoryType.RECOVERY,
    AdvisoryType.TEST,
)

# Advisory types that count towards the per-phone cooldown and daily cap
# (BF-60: TEST does not count, RECOVERY does).
LIMIT_COUNTED_ADVISORY_TYPES: Final[frozenset[AdvisoryType]] = frozenset(
    {
        AdvisoryType.SITE_INITIAL,
        AdvisoryType.SITE_CHANGE,
        AdvisoryType.ZONE_ADVISORY,
        AdvisoryType.RECOVERY,
    }
)


class EventType(StrEnum):
    """``site_event.type`` (BF-62)."""

    STATE_CHANGE = "STATE_CHANGE"
    CANDIDATE = "CANDIDATE"
    ADVISORY = "ADVISORY"
    DATA_STALE = "DATA_STALE"
    DATA_RECOVERED = "DATA_RECOVERED"
    INGEST_REJECTED = "INGEST_REJECTED"
    INGEST_INCONSISTENT = "INGEST_INCONSISTENT"
    ZONE_DISCOVERED = "ZONE_DISCOVERED"
    FCM_ERROR = "FCM_ERROR"
    CONFIG_CHANGED = "CONFIG_CHANGED"
    TEST_PUSH = "TEST_PUSH"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class SuppressionReason(StrEnum):
    """Why a whole candidate was not fanned out (``site_event.reason`` on a
    ``CANDIDATE`` event). BF-52 (stale), BF-57 (usefulness), BF-61 (shadow)."""

    STALE_DATA = "STALE_DATA"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    NO_RECOMMENDATION = "NO_RECOMMENDATION"
    UNMANAGED = "UNMANAGED"
    # D10 in-flight guard: an identical advisory is still being fanned out.
    IN_FLIGHT = "IN_FLIGHT"


class DeviceOutcome(StrEnum):
    """``push_send.outcome`` and the keys of ``site_event.counts`` (BF-58, BF-66).

    ``PENDING`` is the at-most-once marker of D10: the row is committed before
    FCM is called and updated afterwards.
    """

    PENDING = "PENDING"
    OPTED_OUT = "OPTED_OUT"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    DUPLICATE = "DUPLICATE"
    COOLDOWN = "COOLDOWN"
    DAILY_CAP = "DAILY_CAP"
    SENT = "SENT"
    SEND_FAILED = "SEND_FAILED"
    TOKEN_INVALID = "TOKEN_INVALID"


# BF-58 check order; the first failing check is the device's reason.
DEVICE_CHECK_ORDER: Final[tuple[DeviceOutcome, ...]] = (
    DeviceOutcome.OPTED_OUT,
    DeviceOutcome.OUTSIDE_WINDOW,
    DeviceOutcome.DUPLICATE,
    DeviceOutcome.COOLDOWN,
    DeviceOutcome.DAILY_CAP,
)


# ─────────────────────────────────────────────────────────────
# Which push_send rows count towards the per-phone limits (BF-58, BF-63)
# ─────────────────────────────────────────────────────────────
#
# THE rule, in one place (the SQL form is ``_counted_outcome`` in
# ``src/crud/freespace_push_send.py``, built from these constants):
#
# A row counts for DUPLICATE / COOLDOWN / DAILY_CAP when FCM accepted the
# message OR acceptance is UNKNOWN - when in doubt, protect the phone:
#   * outcome SENT                                   (accepted)
#   * outcome PENDING                                (claimed / in flight / retry
#                                                     pending: may still arrive)
#   * outcome SEND_FAILED with an "acceptance unknown" error code:
#       - UNKNOWN_AFTER_CRASH  run died between claim commit and FCM answer
#       - CLIENT_ERROR         the FCM client raised after the request may
#                              have left
#       - NO_RESPONSE_*        request sent, no answer (read timeout, reset)
#     These rows are also NEVER retried (BF-52 at-most-once).
#
# A row does NOT count when FCM definitely did not accept it: SEND_FAILED
# with any other code (connection refused / connect timeout before sending,
# explicit non-retryable 4xx/5xx, RETRY_WINDOW_EXHAUSTED after 429/5xx,
# EXPIRED without a call, FANOUT_STOPPED, CREDENTIALS_ERROR), TOKEN_INVALID,
# and every suppression outcome (OPTED_OUT ... DAILY_CAP).

SEND_ERROR_UNKNOWN_AFTER_CRASH: Final = "UNKNOWN_AFTER_CRASH"
SEND_ERROR_CLIENT: Final = "CLIENT_ERROR"
SEND_ERROR_NO_RESPONSE_PREFIX: Final = "NO_RESPONSE_"
SEND_ACCEPTANCE_UNKNOWN_CODES: Final[frozenset[str]] = frozenset(
    {SEND_ERROR_UNKNOWN_AFTER_CRASH, SEND_ERROR_CLIENT}
)
LIMIT_COUNTED_OUTCOMES: Final[tuple[str, ...]] = (
    DeviceOutcome.SENT.value,
    DeviceOutcome.PENDING.value,
)


def send_acceptance_unknown(error_code: str | None) -> bool:
    """True when a SEND_FAILED ``error_code`` means FCM MAY have accepted."""
    if error_code is None:
        return False
    return error_code in SEND_ACCEPTANCE_UNKNOWN_CODES or error_code.startswith(
        SEND_ERROR_NO_RESPONSE_PREFIX
    )


def send_counts_towards_limits(outcome: str, error_code: str | None) -> bool:
    """Python form of the BF-58/BF-63 counting rule above."""
    if outcome in LIMIT_COUNTED_OUTCOMES:
        return True
    return outcome == DeviceOutcome.SEND_FAILED.value and send_acceptance_unknown(
        error_code
    )


class StateChangeReason(StrEnum):
    """``site_event.reason`` on a ``STATE_CHANGE`` event (BF-52, BF-72)."""

    TRIGGER_CROSSED = "TRIGGER_CROSSED"  # IDLE -> PENDING
    NOT_STABLE = "NOT_STABLE"  # PENDING -> IDLE (AT-02)
    STABILISED = "STABILISED"  # PENDING -> ACTIVE (AT-03)
    RESET = "RESET"  # ACTIVE -> IDLE below reset level (AT-06)
    CYCLE_RESTARTED = "CYCLE_RESTARTED"  # managed switched off and on (BF-72)


class IngestRejectReason(StrEnum):
    """``site_event.reason`` on an ``INGEST_REJECTED`` event (BF-10, BF-13, BF-18)."""

    SITE_MISMATCH = "SITE_MISMATCH"
    CLOCK_SKEW = "CLOCK_SKEW"
    RATE_LIMITED = "RATE_LIMITED"
    OUT_OF_ORDER = "OUT_OF_ORDER"


class IngestInconsistencyReason(StrEnum):
    """``site_event.reason`` on an ``INGEST_INCONSISTENT`` event (BF-12)."""

    SUM_MISMATCH = "SUM_MISMATCH"


class FcmErrorReason(StrEnum):
    """``site_event.reason`` on an ``FCM_ERROR`` event (BF-66)."""

    AUTH_FAILURE = "AUTH_FAILURE"  # 401/403: credential broken, fan-out stopped
    CREDENTIALS_MISSING = "CREDENTIALS_MISSING"  # no service-account file
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"  # retries exhausted on 429


class ConfigChangeReason(StrEnum):
    """``site_event.reason`` on a ``CONFIG_CHANGED`` event (BF-77)."""

    SITE_SETTINGS = "SITE_SETTINGS"
    ZONE_SETTINGS = "ZONE_SETTINGS"
    TEMPLATES = "TEMPLATES"
    MANAGED_ON = "MANAGED_ON"
    MANAGED_OFF = "MANAGED_OFF"
    KEYS = "KEYS"


class Health(StrEnum):
    """Per-zone / per-site data health reported by ParkIT (§5.2)."""

    OK = "OK"
    PARTIAL = "PARTIAL"
    OFFLINE = "OFFLINE"


class ZoneStatus(StrEnum):
    """Zone status shown to the app (BF-23)."""

    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    FULL = "FULL"
    UNKNOWN = "UNKNOWN"


class Platform(StrEnum):
    """Device platform (BF-6)."""

    ANDROID = "ANDROID"
    IOS = "IOS"


class LimitScope(StrEnum):
    """Deployment limit scope (BF-63)."""

    DEVICE = "DEVICE"
    DEVICE_PER_SITE = "DEVICE_PER_SITE"


class ChangeDirection(StrEnum):
    """Which occupancy movements count against Δ (BF-55)."""

    RISING = "RISING"
    BOTH = "BOTH"


class FanoutStatus(StrEnum):
    """``site_event.fanout_status``; NULL for events that never fan out (D7, D10)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ─────────────────────────────────────────────────────────────
# Defaults (spec §10.1 / §10.2, BF-71, BF-73)
# ─────────────────────────────────────────────────────────────

DEFAULT_TIME_ZONE: Final = "Africa/Johannesburg"
DEFAULT_LOCALE: Final = "en"

# Notification window rule JSON shape (stored in site.notification_window):
#   {"weekdays": [1, 2, 3, 4, 5], "start": "06:00", "end": "10:00"}
# weekdays are ISO numbers (1 = Monday ... 7 = Sunday); start/end are site
# local "HH:MM", start < end, no overnight span. An empty list = any time.
DEFAULT_NOTIFICATION_WINDOW: Final[list[dict[str, Any]]] = [
    {"weekdays": [1, 2, 3, 4, 5], "start": "06:00", "end": "10:00"}
]


def default_notification_window() -> list[dict[str, Any]]:
    """Fresh copy of the default window (Mon-Fri 06:00-10:00, §15 Q4)."""
    return [
        dict(rule, weekdays=list(rule["weekdays"]))
        for rule in DEFAULT_NOTIFICATION_WINDOW
    ]


# Site settings defaults (§10.1)
SITE_DEFAULTS: Final[dict[str, Any]] = {
    "managed": False,
    "listed": False,
    "trigger_pct": 90,
    "reset_pct": 80,
    "change_points": 5,
    "change_direction": ChangeDirection.RISING.value,
    "stabilisation_s": 300,
    "recommendation_margin": 10,
    "stale_limit_s": 120,
    "partial_is_stale": True,
    "recovery_push": False,
    "zone_advisory": False,
    "zone_reset_gap": 10,
    "cooldown_s": 1800,
    "daily_cap": 2,
    "push_expiry_s": 1800,
    "time_zone": DEFAULT_TIME_ZONE,
}

# Zone settings defaults (§10.2). ``enabled`` is False for DISCOVERED zones;
# a zone created by an administrator through the API is enabled by M1.
ZONE_DEFAULTS: Final[dict[str, Any]] = {
    "enabled": False,
    "recommendable": True,
    "preferred": False,
    "priority": 100,
    "limited_pct": 80,
    "full_pct": 95,
    "full_min_free": 5,
    "unknown_limit_pct": 25,
    "advisory_pct": None,
    "note": "",
    "display_order": 0,
}

# Validation bounds (BF-71). M1 enforces them; listed here so the engine
# loader and tests can share them.
# (min, max) of the integer site settings; max None = unbounded. The single
# source of truth for ``site_config.validate_site_settings``.
SITE_SETTING_BOUNDS: Final[dict[str, tuple[int, int | None]]] = {
    "trigger_pct": (1, 100),
    "change_points": (1, 50),
    "stabilisation_s": (0, 3600),
    "recommendation_margin": (0, None),
    "stale_limit_s": (120, None),  # BF-71 / spec 10.1: >= 2 x 60 s post interval
    "zone_reset_gap": (1, 50),
    "push_expiry_s": (60, 86400),
    "cooldown_s": (0, None),
    "daily_cap": (0, None),
}

# Deployment-level defaults (BF-63, BF-37, BF-73). Read through
# src/services/freespace/deployment_settings.py, never directly.
DEPLOYMENT_DEFAULTS: Final[dict[str, Any]] = {
    "limit_scope": LimitScope.DEVICE.value,
    "cooldown_s": 1800,
    "daily_cap": 2,
    "time_zone": DEFAULT_TIME_ZONE,
    "device_ceiling": 50000,
    "retention_devices_days": 90,
    "retention_send_history_days": 35,
    "retention_events_days": 365,
    "retention_occupancy_history_days": 180,
    "retention_request_logs_days": 30,
}

# ─────────────────────────────────────────────────────────────
# Wire / protocol constants
# ─────────────────────────────────────────────────────────────

# BF-13: measuredAt more than this many seconds in the future -> 422 CLOCK_SKEW
MAX_FUTURE_SKEW_S: Final = 120
# BF-19: keep intake/ping responses well under ParkIT's 64 KB read limit
MAX_INGEST_WARNINGS: Final = 10
MAX_INGEST_WARNING_LENGTH: Final = 200
# BF-18 Retry-After clamp
RETRY_AFTER_MIN_S: Final = 1
RETRY_AFTER_MAX_S: Final = 600
# BF-32
AVAILABILITY_CACHE_MAX_AGE_S: Final = 5

# Slugs (siteId / zoneId). Lowercase so URLs and topics stay predictable.
SLUG_PATTERN: Final = r"^[a-z0-9][a-z0-9_-]{0,63}$"
SLUG_RE: Final = re.compile(SLUG_PATTERN)
# FCM topic names: [a-zA-Z0-9-_.~%]+
FCM_TOPIC_PATTERN: Final = r"^[a-zA-Z0-9\-_.~%]{1,900}$"

# BF-33 device id
DEVICE_ID_PATTERN: Final = r"^[A-Za-z0-9_-]{22,64}$"
DEVICE_ID_RE: Final = re.compile(DEVICE_ID_PATTERN)
DEVICE_ID_SUFFIX_LENGTH: Final = 6  # BF-74

# BF-10a / D3 keys
INGEST_KEY_PREFIX: Final = "fsk_"
APP_KEY_PREFIX: Final = "fsa_"
KEY_HINT_LENGTH: Final = 4
INGEST_KEY_FORMAT_PATTERN: Final = r"^[\x21-\x7e]{1,512}$"
INGEST_KEY_FORMAT_RE: Final = re.compile(INGEST_KEY_FORMAT_PATTERN)
APP_KEY_HEADER: Final = "X-Freespace-App-Key"

# BF-65 FCM message constants
ANDROID_CHANNEL_ID: Final = "freespace_default"
FCM_MAX_IN_FLIGHT: Final = 20  # BF-64 bounded concurrency
FCM_RETRY_WINDOW_S: Final = 300  # BF-66 retry for at most 5 minutes
FANOUT_CHUNK_SIZE: Final = 500  # D10 devices per ARQ job
# A fan-out still PENDING/RUNNING this long after its event is re-enqueued by
# the engine tick (D7).
FANOUT_STUCK_AFTER_S: Final = 360

# ─────────────────────────────────────────────────────────────
# Redis keys (all Freespace keys share the "freespace:" prefix)
# ─────────────────────────────────────────────────────────────

REDIS_PREFIX: Final = "freespace:"
REDIS_MOCK_CLOCK_OFFSET_KEY: Final = "freespace:mock:clock_offset_s"
REDIS_APP_KEYS_KEY: Final = "freespace:app_keys:valid"
REDIS_DEPLOYMENT_SETTINGS_KEY: Final = "freespace:deployment_settings"
# The engine tick (M6) writes the ISO-8601 UTC time of its last run here;
# /health (M9) reads it (BF-80).
REDIS_ENGINE_TICK_KEY: Final = "freespace:engine_tick:last"
# Per-site availability response cache (M4, BF-32): format with the site slug.
REDIS_AVAILABILITY_KEY_FMT: Final = "freespace:availability:{slug}"
# Ingest limiter window (M2, BF-18): format with the ingest key id.
REDIS_INGEST_RATE_KEY_FMT: Final = "freespace:ingest_rate:{key_id}"

APP_KEYS_CACHE_TTL_S: Final = 60
DEPLOYMENT_SETTINGS_CACHE_TTL_S: Final = 60

# ─────────────────────────────────────────────────────────────
# Permissions (D16) - seeded by the shared seeder
# ─────────────────────────────────────────────────────────────

PERM_SITES_READ: Final = "sites:read"
PERM_SITES_WRITE: Final = "sites:write"
PERM_SITE_KEYS_WRITE: Final = "site_keys:write"
PERM_SITE_PUSH_TEST: Final = "site_push:test"
PERM_SITE_PUSH_ANNOUNCE: Final = "site_push:announce"
PERM_SITE_EVENTS_READ: Final = "site_events:read"
PERM_SITE_ALERTS_RECEIVE: Final = "site_alerts:receive"

FREESPACE_PERMISSION_CODES: Final[tuple[str, ...]] = (
    PERM_SITES_READ,
    PERM_SITES_WRITE,
    PERM_SITE_KEYS_WRITE,
    PERM_SITE_PUSH_TEST,
    PERM_SITE_PUSH_ANNOUNCE,
    PERM_SITE_EVENTS_READ,
    PERM_SITE_ALERTS_RECEIVE,
)

OPERATOR_ROLE_NAME: Final = "operator"

# ARQ job names (registered in src/workers/worker.py)
JOB_FANOUT_ADVISORY: Final = "fanout_advisory_task"
JOB_ENGINE_TICK: Final = "engine_tick"
