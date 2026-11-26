"""
FCM HTTP v1 client interface (BF-64 - BF-69, D10). OWNER: M7.

``FcmClient`` is the only thing fan-out, test push and announcements talk
to. Production uses ``HttpFcmClient`` (httpx HTTP/2 + google-auth service
account, M7 implements it); tests use ``FakeFcmClient`` (fully implemented
here) via ``set_fcm_client_override`` / the ``fake_fcm`` fixture.

Wording rule (BF-69): an accepted send means "accepted by FCM", never
"delivered".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
import time
from typing import Any, Protocol, runtime_checkable

import httpx

from src.constants.freespace import (
    ANDROID_CHANNEL_ID,
    FCM_MAX_IN_FLIGHT,
    SEND_ERROR_NO_RESPONSE_PREFIX,
    AdvisoryType,
)
from src.logger.logger import Logger as logger
from src.services.freespace.clock import ensure_utc
from src.services.freespace.fcm_auth import (
    AccessTokenProvider,
    FcmCredentialsError,
    ServiceAccountTokenProvider,
)


class FcmResultKind(StrEnum):
    """Classification of one ``messages:send`` call (BF-66)."""

    ACCEPTED = "ACCEPTED"  # 200: FCM accepted the message
    # UNREGISTERED, 404 on the token, INVALID_ARGUMENT naming the token,
    # SENDER_ID_MISMATCH -> invalidate the token, outcome TOKEN_INVALID
    TOKEN_INVALID = "TOKEN_INVALID"
    # 429 / 500 / 503 -> retry with backoff honouring retry_after_s
    RETRYABLE = "RETRYABLE"
    # 401 / 403 -> credential broken: stop the fan-out, FCM_ERROR, alert
    AUTH_FAILURE = "AUTH_FAILURE"
    # Any other non-retryable error (e.g. INVALID_ARGUMENT about the payload)
    FAILED = "FAILED"


@dataclass(frozen=True)
class FcmMessage:
    """One FCM v1 message. Exactly one of ``token`` / ``topic`` is set.

    ``payload`` is the full v1 ``message`` object EXCLUDING the target
    (``token``/``topic`` are added by the client), i.e.
    ``{"notification": {...}, "data": {...}, "android": {...}, "apns": {...}}``.
    """

    payload: Mapping[str, Any]
    token: str | None = None
    topic: str | None = None

    def __post_init__(self) -> None:
        if (self.token is None) == (self.topic is None):
            raise ValueError("FcmMessage needs exactly one of token or topic")

    def to_request_body(self) -> dict[str, Any]:
        """``{"message": {...payload, "token"|"topic": ...}}`` for messages:send."""
        message = dict(self.payload)
        if self.token is not None:
            message["token"] = self.token
        else:
            message["topic"] = self.topic
        return {"message": message}


@dataclass(frozen=True)
class FcmSendResult:
    """Outcome of one send. ``retry_after_s`` only for RETRYABLE (None = use
    backoff); ``error_code`` is FCM's error status / detail code, e.g.
    ``"UNREGISTERED"``; ``message_id`` is FCM's ``name`` on ACCEPTED."""

    kind: FcmResultKind
    message_id: str | None = None
    retry_after_s: float | None = None
    error_code: str | None = None
    http_status: int | None = None
    latency_ms: float = 0.0


@runtime_checkable
class FcmClient(Protocol):
    """Sends one FCM message. Must be safe for ``FCM_MAX_IN_FLIGHT``
    concurrent ``send`` calls. Must not raise for FCM error responses
    (classify them instead); may raise for programming errors."""

    async def send(self, message: FcmMessage) -> FcmSendResult: ...

    async def aclose(self) -> None: ...


def build_data_payload(
    *,
    message_type: AdvisoryType | str,
    site_slug: str,
    recommended_zone_slug: str | None,
    occupancy_pct: int | None,
    event_id: str,
    sent_at: datetime,
) -> dict[str, str]:
    """BF-65 ``data`` block; ALL values strings: ``type``, ``siteId``,
    ``recommendedZoneId`` ("" when None), ``occupancyPct`` ("" when None),
    ``eventId``, ``sentAt`` (ISO-8601 UTC with ``Z``)."""
    type_value = (
        message_type.value if isinstance(message_type, StrEnum) else str(message_type)
    )
    return {
        "type": type_value,
        "siteId": str(site_slug),
        "recommendedZoneId": recommended_zone_slug or "",
        "occupancyPct": "" if occupancy_pct is None else str(int(occupancy_pct)),
        "eventId": str(event_id),
        "sentAt": iso_z(sent_at),
    }


def iso_z(value: datetime) -> str:
    """ISO-8601 UTC with ``Z`` and whole seconds (BN-2)."""
    return (
        ensure_utc(value)
        .astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_message(
    *,
    title: str,
    body: str,
    data: Mapping[str, str],
    site_slug: str,
    sent_at: datetime,
    ttl_s: int,
    token: str | None = None,
    topic: str | None = None,
) -> FcmMessage:
    """BF-65 message with BOTH platform blocks set explicitly:
    android ``priority HIGH``, ``ttl "<ttl_s>s"``, ``collapse_key site_slug``,
    ``notification.channel_id ANDROID_CHANNEL_ID``, ``notification.tag
    site_slug``; apns headers ``apns-priority 10``, ``apns-push-type alert``,
    ``apns-expiration <sent_at + ttl_s as epoch>``, ``apns-collapse-id
    site_slug``. Exactly one of ``token`` / ``topic``."""
    ttl = max(0, int(ttl_s))
    expiration = int(ensure_utc(sent_at).timestamp()) + ttl
    payload: dict[str, Any] = {
        "notification": {"title": title, "body": body},
        "data": {str(k): str(v) for k, v in data.items()},
        "android": {
            "priority": "HIGH",
            "ttl": f"{ttl}s",
            "collapse_key": site_slug,
            "notification": {"channel_id": ANDROID_CHANNEL_ID, "tag": site_slug},
        },
        "apns": {
            "headers": {
                "apns-priority": "10",
                "apns-push-type": "alert",
                "apns-expiration": str(expiration),
                "apns-collapse-id": site_slug,
            },
            "payload": {"aps": {"alert": {"title": title, "body": body}}},
        },
    }
    return FcmMessage(payload=payload, token=token, topic=topic)


async def send_to_topic(
    fcm: FcmClient,
    *,
    topic: str,
    title: str,
    body: str,
    message_type: AdvisoryType | str,
    site_slug: str,
    event_id: str,
    sent_at: datetime,
    ttl_s: int,
    recommended_zone_slug: str | None = None,
    occupancy_pct: int | None = None,
) -> FcmSendResult:
    """One topic message (BF-41: test push to a topic, announcements). The
    caller logs the ``TEST_PUSH`` / ``ANNOUNCEMENT`` event; a topic send is
    never subject to per-phone limits. ``message_type`` is e.g.
    ``AdvisoryType.TEST`` or ``"ANNOUNCEMENT"``. ACCEPTED means "accepted by
    FCM" (BF-69), not delivered."""
    data = build_data_payload(
        message_type=message_type,
        site_slug=site_slug,
        recommended_zone_slug=recommended_zone_slug,
        occupancy_pct=occupancy_pct,
        event_id=event_id,
        sent_at=sent_at,
    )
    message = build_message(
        title=title,
        body=body,
        data=data,
        site_slug=site_slug,
        sent_at=sent_at,
        ttl_s=ttl_s,
        topic=topic,
    )
    return await fcm.send(message)


# ─────────────────────────────────────────────────────────────
# Response classification (BF-66)
# ─────────────────────────────────────────────────────────────

_FCM_ERROR_TYPE = "type.googleapis.com/google.firebase.fcm.v1.FcmError"
_BAD_REQUEST_TYPE = "type.googleapis.com/google.rpc.BadRequest"
_TOKEN_INVALID_CODES = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})
_RETRYABLE_STATUSES = frozenset({429, 500, 503})


def parse_retry_after(
    value: str | None, date_header: str | None = None
) -> float | None:
    """``Retry-After`` as seconds: delta-seconds, or an HTTP date measured
    against the response ``Date`` header (no local wall clock). None when
    absent or unparseable."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
        if seconds != seconds or seconds in (float("inf"), float("-inf")):
            return None
        return max(0.0, seconds)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        if date_header:
            base = parsedate_to_datetime(date_header)
            return max(0.0, (when - base).total_seconds())
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _error_details(body: Any) -> tuple[str | None, str | None, list[str], str]:
    """(fcm error code, google status, bad-request fields, message)."""
    if not isinstance(body, Mapping):
        return None, None, [], ""
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None, None, [], ""
    fcm_code: str | None = None
    fields: list[str] = []
    for detail in error.get("details") or []:
        if not isinstance(detail, Mapping):
            continue
        if detail.get("@type") == _FCM_ERROR_TYPE and detail.get("errorCode"):
            fcm_code = str(detail["errorCode"])
        if detail.get("@type") == _BAD_REQUEST_TYPE:
            for violation in detail.get("fieldViolations") or []:
                if isinstance(violation, Mapping) and violation.get("field"):
                    fields.append(str(violation["field"]))
    status = error.get("status")
    return (
        fcm_code,
        str(status) if status else None,
        fields,
        str(error.get("message") or ""),
    )


def classify_response(
    http_status: int,
    body: Any,
    headers: Mapping[str, str] | None = None,
    *,
    latency_ms: float = 0.0,
) -> FcmSendResult:
    """Map one ``messages:send`` HTTP response to an ``FcmSendResult`` (BF-66).

    * 200 -> ACCEPTED ("accepted by FCM").
    * FCM ``UNREGISTERED``, ``SENDER_ID_MISMATCH`` (403!), a 404, or
      ``INVALID_ARGUMENT`` whose field violation / message names the token
      -> TOKEN_INVALID.
    * 429 / 500 / 503 -> RETRYABLE with ``Retry-After``.
    * 401 / 403 without a per-registration FCM code -> AUTH_FAILURE (our
      OAuth credential is broken).
    * Everything else (other INVALID_ARGUMENT, ``THIRD_PARTY_AUTH_ERROR`` =
      APNs key of the Firebase project, ``THIRD_PARTY_PERMISSION_DENIED``)
      -> FAILED.
    """
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    if http_status == 200:
        message_id = body.get("name") if isinstance(body, Mapping) else None
        return FcmSendResult(
            kind=FcmResultKind.ACCEPTED,
            message_id=str(message_id) if message_id else None,
            http_status=200,
            latency_ms=latency_ms,
        )
    fcm_code, status, fields, message = _error_details(body)
    code = fcm_code or status or f"HTTP_{http_status}"

    def result(kind: FcmResultKind, retry_after: float | None = None) -> FcmSendResult:
        return FcmSendResult(
            kind=kind,
            error_code=code[:64],
            http_status=http_status,
            retry_after_s=retry_after,
            latency_ms=latency_ms,
        )

    if fcm_code in _TOKEN_INVALID_CODES or http_status == 404:
        return result(FcmResultKind.TOKEN_INVALID)
    if http_status == 400 or fcm_code == "INVALID_ARGUMENT":
        names_token = any(f.endswith("token") or f.endswith("fid") for f in fields) or (
            "registration token" in message.lower()
        )
        return result(
            FcmResultKind.TOKEN_INVALID if names_token else FcmResultKind.FAILED
        )
    if http_status in _RETRYABLE_STATUSES:
        return result(
            FcmResultKind.RETRYABLE,
            parse_retry_after(headers.get("retry-after"), headers.get("date")),
        )
    if fcm_code in ("THIRD_PARTY_AUTH_ERROR", "THIRD_PARTY_PERMISSION_DENIED"):
        return result(FcmResultKind.FAILED)
    if http_status in (401, 403):
        return result(FcmResultKind.AUTH_FAILURE)
    if 500 <= http_status < 600:
        # 502/504 from a proxy: FCM may or may not have accepted it; never
        # retry what might have been accepted (at-most-once, BF-52).
        return result(FcmResultKind.FAILED)
    return result(FcmResultKind.FAILED)


FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


class HttpFcmClient:
    """Production client: ``httpx.AsyncClient(http2=True)`` against
    ``https://fcm.googleapis.com/v1/projects/{project_id}/messages:send``,
    OAuth token from google-auth service-account credentials at
    ``credentials_path`` (cached until near expiry).

    One request per message (BF-64: HTTP v1 has no multi-token endpoint; the
    legacy batch endpoint was shut down in 2024). Concurrency is bounded by
    the caller (fan-out semaphore); the connection pool allows
    ``FCM_MAX_IN_FLIGHT`` streams. ``token_provider`` / ``transport`` are
    test seams.
    """

    def __init__(
        self,
        credentials_path: str,
        project_id: str,
        *,
        token_provider: AccessTokenProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.credentials_path = credentials_path
        self.project_id = project_id
        self.url = FCM_SEND_URL.format(project_id=project_id)
        self._tokens: AccessTokenProvider = (
            token_provider or ServiceAccountTokenProvider(credentials_path)
        )
        self._transport = transport
        self._timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self._timeout_s, connect=5.0),
                "limits": httpx.Limits(
                    max_connections=FCM_MAX_IN_FLIGHT,
                    max_keepalive_connections=FCM_MAX_IN_FLIGHT,
                ),
            }
            if self._transport is not None:
                kwargs["transport"] = self._transport
            else:
                kwargs["http2"] = True
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def send(self, message: FcmMessage) -> FcmSendResult:
        try:
            access_token = await self._tokens.get_token()
        except FcmCredentialsError as exc:
            logger.error(f"Freespace FCM: credentials unusable: {exc}")
            return FcmSendResult(
                kind=FcmResultKind.AUTH_FAILURE, error_code="CREDENTIALS_ERROR"
            )
        started = time.perf_counter()
        try:
            response = await self._http().post(
                self.url,
                json=message.to_request_body(),
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # The request never reached FCM: safe to retry.
            return FcmSendResult(
                kind=FcmResultKind.RETRYABLE,
                error_code=f"NETWORK_{type(exc).__name__}"[:64],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except httpx.HTTPError as exc:
            # Sent, but no answer (read timeout, reset): FCM may have accepted
            # it. Never retry what might have been accepted (BF-52).
            return FcmSendResult(
                kind=FcmResultKind.FAILED,
                error_code=f"{SEND_ERROR_NO_RESPONSE_PREFIX}{type(exc).__name__}"[:64],
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            body: Any = response.json()
        except ValueError:
            body = None
        result = classify_response(
            response.status_code, body, response.headers, latency_ms=latency_ms
        )
        if result.kind == FcmResultKind.AUTH_FAILURE:
            # Maybe just a revoked token: re-read the file next time.
            self._tokens.invalidate()
        return result

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


@dataclass
class FakeFcmClient:
    """In-memory FCM for tests. Fully implemented.

    * ``sent`` records every message passed to ``send``, in order.
    * ``results_by_token[token]`` / ``results_by_topic[topic]``: the result
      to return for that target - a single ``FcmSendResult`` (returned every
      time) or a list consumed one per call (the last one repeats).
    * Otherwise ``default_result`` (ACCEPTED with a generated message id).
    """

    results_by_token: dict[str, FcmSendResult | list[FcmSendResult]] = field(
        default_factory=dict
    )
    results_by_topic: dict[str, FcmSendResult | list[FcmSendResult]] = field(
        default_factory=dict
    )
    default_result: FcmSendResult | None = None
    sent: list[FcmMessage] = field(default_factory=list)
    closed: bool = False

    def _next(self, script: FcmSendResult | list[FcmSendResult]) -> FcmSendResult:
        if isinstance(script, list):
            if len(script) > 1:
                return script.pop(0)
            return script[0]
        return script

    async def send(self, message: FcmMessage) -> FcmSendResult:
        self.sent.append(message)
        script: FcmSendResult | list[FcmSendResult] | None = None
        if message.token is not None:
            script = self.results_by_token.get(message.token)
        elif message.topic is not None:
            script = self.results_by_topic.get(message.topic)
        if script is not None:
            return self._next(script)
        if self.default_result is not None:
            return self.default_result
        return FcmSendResult(
            kind=FcmResultKind.ACCEPTED,
            message_id=f"projects/fake/messages/{len(self.sent)}",
            http_status=200,
        )

    async def aclose(self) -> None:
        self.closed = True

    # Convenience for assertions
    @property
    def sent_tokens(self) -> list[str]:
        return [m.token for m in self.sent if m.token is not None]

    @property
    def sent_topics(self) -> list[str]:
        return [m.topic for m in self.sent if m.topic is not None]

    def reset(self) -> None:
        self.sent.clear()


_override: FcmClient | None = None
_default_client: FcmClient | None = None


def set_fcm_client_override(client: FcmClient | None) -> None:
    """Make ``get_fcm_client`` return ``client`` (None restores). Tests only."""
    global _override
    _override = client


def get_fcm_client() -> FcmClient:
    """FastAPI dependency and module accessor for the process-wide FCM client.

    Override (tests) > lazily created ``HttpFcmClient`` from
    ``settings.FREESPACE_FCM_CREDENTIALS_PATH`` / ``FREESPACE_FCM_PROJECT_ID``.
    Raises ``RuntimeError`` when no credentials are configured (callers log
    ``FCM_ERROR / CREDENTIALS_MISSING``).
    """
    global _default_client
    if _override is not None:
        return _override
    if _default_client is None:
        from src.core.config import settings

        if (
            not settings.FREESPACE_FCM_CREDENTIALS_PATH
            or not settings.FREESPACE_FCM_PROJECT_ID
        ):
            raise RuntimeError("FCM is not configured (freespace.fcm_credentials_path)")
        _default_client = HttpFcmClient(
            settings.FREESPACE_FCM_CREDENTIALS_PATH, settings.FREESPACE_FCM_PROJECT_ID
        )
    return _default_client
