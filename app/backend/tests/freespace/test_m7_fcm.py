"""M7 FCM message builder and HTTP v1 client (BF-64 - BF-66, BF-41)."""

from __future__ import annotations

from datetime import datetime, timezone
import json

import httpx
import pytest

from src.constants.freespace import AdvisoryType
from src.services.freespace.fcm import (
    FakeFcmClient,
    FcmResultKind,
    HttpFcmClient,
    build_data_payload,
    build_message,
    classify_response,
    parse_retry_after,
    send_to_topic,
)
from src.services.freespace.fcm_auth import (
    ServiceAccountTokenProvider,
    StaticTokenProvider,
)


SENT_AT = datetime(2026, 11, 24, 6, 20, 0, tzinfo=timezone.utc)
EVENT_ID = "6f1c2a8e-0000-4000-8000-000000000001"


def _message(**target):
    data = build_data_payload(
        message_type=AdvisoryType.SITE_CHANGE,
        site_slug="absa-alice-lane",
        recommended_zone_slug="b4",
        occupancy_pct=95,
        event_id=EVENT_ID,
        sent_at=SENT_AT,
    )
    return build_message(
        title="Alice Lane",
        body="Parking availability has changed. Basement 4 is now the recommended "
        "parking area. Open Freespace for the latest information.",
        data=data,
        site_slug="absa-alice-lane",
        sent_at=SENT_AT,
        ttl_s=1800,
        **target,
    )


def test_payload_snapshot_both_platforms():
    """BF-65 snapshot: data all strings; Android AND APNs set explicitly."""
    body = _message(token="TOKEN-1").to_request_body()
    assert body == {
        "message": {
            "token": "TOKEN-1",
            "notification": {
                "title": "Alice Lane",
                "body": "Parking availability has changed. Basement 4 is now the "
                "recommended parking area. Open Freespace for the latest information.",
            },
            "data": {
                "type": "SITE_CHANGE",
                "siteId": "absa-alice-lane",
                "recommendedZoneId": "b4",
                "occupancyPct": "95",
                "eventId": EVENT_ID,
                "sentAt": "2026-11-24T06:20:00Z",
            },
            "android": {
                "priority": "HIGH",
                "ttl": "1800s",
                "collapse_key": "absa-alice-lane",
                "notification": {
                    "channel_id": "freespace_default",
                    "tag": "absa-alice-lane",
                },
            },
            "apns": {
                "headers": {
                    "apns-priority": "10",
                    "apns-push-type": "alert",
                    "apns-expiration": str(int(SENT_AT.timestamp()) + 1800),
                    "apns-collapse-id": "absa-alice-lane",
                },
                "payload": {
                    "aps": {
                        "alert": {
                            "title": "Alice Lane",
                            "body": "Parking availability has changed. Basement 4 is "
                            "now the recommended parking area. Open Freespace for the "
                            "latest information.",
                        }
                    }
                },
            },
        }
    }
    assert (
        body["message"]["apns"]["headers"]["apns-expiration"] == "1795503000"
    )  # 2026-11-24T06:50:00Z
    assert all(isinstance(v, str) for v in body["message"]["data"].values())


def test_data_payload_empty_values_are_empty_strings():
    data = build_data_payload(
        message_type="ANNOUNCEMENT",
        site_slug="s",
        recommended_zone_slug=None,
        occupancy_pct=None,
        event_id="e",
        sent_at=SENT_AT,
    )
    assert data["recommendedZoneId"] == "" and data["occupancyPct"] == ""
    assert data["type"] == "ANNOUNCEMENT"


def test_topic_message():
    body = _message(topic="freespace-absa").to_request_body()["message"]
    assert body["topic"] == "freespace-absa" and "token" not in body


async def test_send_to_topic_helper():
    fake = FakeFcmClient()
    result = await send_to_topic(
        fake,
        topic="ABSA-270RR",
        title="Alice Lane",
        body="Lift B is out of service today.",
        message_type="ANNOUNCEMENT",
        site_slug="absa-alice-lane",
        event_id=EVENT_ID,
        sent_at=SENT_AT,
        ttl_s=1800,
    )
    assert result.kind == FcmResultKind.ACCEPTED
    assert fake.sent_topics == ["ABSA-270RR"]
    assert fake.sent[0].payload["data"]["type"] == "ANNOUNCEMENT"


def _error(code: int, status: str, fcm_code: str | None = None, fields=(), message=""):
    details = []
    if fcm_code:
        details.append(
            {
                "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
                "errorCode": fcm_code,
            }
        )
    if fields:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.BadRequest",
                "fieldViolations": [{"field": f, "description": "bad"} for f in fields],
            }
        )
    return {
        "error": {
            "code": code,
            "message": message,
            "status": status,
            "details": details,
        }
    }


@pytest.mark.parametrize(
    ("status", "body", "headers", "kind", "code"),
    [
        (200, {"name": "projects/p/messages/1"}, {}, FcmResultKind.ACCEPTED, None),
        (
            404,
            _error(404, "NOT_FOUND", "UNREGISTERED"),
            {},
            FcmResultKind.TOKEN_INVALID,
            "UNREGISTERED",
        ),
        (404, None, {}, FcmResultKind.TOKEN_INVALID, "HTTP_404"),
        (
            403,
            _error(403, "PERMISSION_DENIED", "SENDER_ID_MISMATCH"),
            {},
            FcmResultKind.TOKEN_INVALID,
            "SENDER_ID_MISMATCH",
        ),
        (
            400,
            _error(
                400, "INVALID_ARGUMENT", "INVALID_ARGUMENT", fields=["message.token"]
            ),
            {},
            FcmResultKind.TOKEN_INVALID,
            "INVALID_ARGUMENT",
        ),
        (
            400,
            _error(
                400,
                "INVALID_ARGUMENT",
                "INVALID_ARGUMENT",
                message="The registration token is not a valid FCM registration token",
            ),
            {},
            FcmResultKind.TOKEN_INVALID,
            "INVALID_ARGUMENT",
        ),
        (
            400,
            _error(
                400,
                "INVALID_ARGUMENT",
                "INVALID_ARGUMENT",
                fields=["message.android.ttl"],
            ),
            {},
            FcmResultKind.FAILED,
            "INVALID_ARGUMENT",
        ),
        (
            429,
            _error(429, "RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED"),
            {"Retry-After": "30"},
            FcmResultKind.RETRYABLE,
            "QUOTA_EXCEEDED",
        ),
        (
            500,
            _error(500, "INTERNAL", "INTERNAL"),
            {},
            FcmResultKind.RETRYABLE,
            "INTERNAL",
        ),
        (
            503,
            _error(503, "UNAVAILABLE", "UNAVAILABLE"),
            {},
            FcmResultKind.RETRYABLE,
            "UNAVAILABLE",
        ),
        (
            401,
            _error(401, "UNAUTHENTICATED"),
            {},
            FcmResultKind.AUTH_FAILURE,
            "UNAUTHENTICATED",
        ),
        (
            403,
            _error(403, "PERMISSION_DENIED"),
            {},
            FcmResultKind.AUTH_FAILURE,
            "PERMISSION_DENIED",
        ),
        (
            401,
            _error(401, "UNAUTHENTICATED", "THIRD_PARTY_AUTH_ERROR"),
            {},
            FcmResultKind.FAILED,
            "THIRD_PARTY_AUTH_ERROR",
        ),
        (502, None, {}, FcmResultKind.FAILED, "HTTP_502"),
    ],
)
def test_classify_response(status, body, headers, kind, code):
    result = classify_response(status, body, headers)
    assert result.kind == kind
    assert result.error_code == code
    assert result.http_status == status
    if status == 429:
        assert result.retry_after_s == 30


def test_parse_retry_after():
    assert parse_retry_after("12") == 12
    assert parse_retry_after(None) is None
    assert parse_retry_after("nan") is None
    assert (
        parse_retry_after(
            "Tue, 24 Nov 2026 06:21:00 GMT", "Tue, 24 Nov 2026 06:20:00 GMT"
        )
        == 60
    )


def _client(handler) -> tuple[HttpFcmClient, StaticTokenProvider]:
    tokens = StaticTokenProvider("ya29.test-access-token")
    client = HttpFcmClient(
        "/nonexistent/sa.json",
        "freespace-test",
        token_provider=tokens,
        transport=httpx.MockTransport(handler),
    )
    return client, tokens


async def test_http_client_sends_one_v1_request_per_token():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"name": "projects/freespace-test/messages/42"})

    client, _ = _client(handler)
    result = await client.send(_message(token="TOKEN-1"))
    await client.aclose()

    assert result.kind == FcmResultKind.ACCEPTED
    assert result.message_id == "projects/freespace-test/messages/42"
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == (
        "https://fcm.googleapis.com/v1/projects/freespace-test/messages:send"
    )
    assert request.headers["Authorization"] == "Bearer ya29.test-access-token"
    assert json.loads(request.content)["message"]["token"] == "TOKEN-1"


async def test_http_client_classifies_and_invalidates_token_on_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json=_error(401, "UNAUTHENTICATED"))

    client, tokens = _client(handler)
    result = await client.send(_message(token="T"))
    assert result.kind == FcmResultKind.AUTH_FAILURE
    assert tokens.invalidated == 1


async def test_http_client_retry_after_header():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"Retry-After": "17"},
            json=_error(503, "UNAVAILABLE", "UNAVAILABLE"),
        )

    client, _ = _client(handler)
    result = await client.send(_message(token="T"))
    assert result.kind == FcmResultKind.RETRYABLE and result.retry_after_s == 17


async def test_http_client_network_errors():
    """Connect failure: never reached FCM -> retryable. Read timeout: FCM may
    have accepted it -> FAILED, never retried (at-most-once)."""

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    def hang(request):
        raise httpx.ReadTimeout("timeout", request=request)

    client, _ = _client(refuse)
    assert (await client.send(_message(token="T"))).kind == FcmResultKind.RETRYABLE
    client, _ = _client(hang)
    assert (await client.send(_message(token="T"))).kind == FcmResultKind.FAILED


async def test_missing_credentials_file_is_auth_failure():
    client = HttpFcmClient(
        "/nonexistent/freespace-sa.json",
        "p",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
    )
    result = await client.send(_message(token="T"))
    assert result.kind == FcmResultKind.AUTH_FAILURE
    assert result.error_code == "CREDENTIALS_ERROR"


async def test_service_account_provider_caches_until_invalid(monkeypatch):
    class Creds:
        def __init__(self):
            self.token = None
            self.valid = False
            self.refreshes = 0

    creds = Creds()
    provider = ServiceAccountTokenProvider("/somewhere/sa.json")
    monkeypatch.setattr(provider, "_load", lambda: creds)

    def refresh(c):
        c.refreshes += 1
        c.token = f"tok-{c.refreshes}"
        c.valid = True

    monkeypatch.setattr(ServiceAccountTokenProvider, "_refresh", staticmethod(refresh))
    assert await provider.get_token() == "tok-1"
    assert await provider.get_token() == "tok-1"
    creds.valid = False  # google-auth: near expiry -> no longer valid
    assert await provider.get_token() == "tok-2"
    assert creds.refreshes == 2
