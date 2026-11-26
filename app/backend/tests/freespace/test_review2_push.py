"""Review round 2: FCM token-refresh transport errors are RETRYABLE (F1), and
back-office pushes commit their event BEFORE calling FCM (F2)."""

from __future__ import annotations

from datetime import timedelta

import google.auth.exceptions
import httpx
import pytest
from sqlalchemy import select

from src.api import freespace_push
from src.constants.freespace import DeviceOutcome, EventType, FanoutStatus
from src.models.site_event import SiteEvent
from src.services.freespace import admin_push
from src.services.freespace.fanout import recover_stuck_fanouts
from src.services.freespace.fcm import (
    TOKEN_UNAVAILABLE_ERROR_CODE,
    FcmMessage,
    FcmResultKind,
    FcmSendResult,
    HttpFcmClient,
)
from src.services.freespace.fcm_auth import (
    FcmCredentialsError,
    FcmTokenUnavailableError,
    ServiceAccountTokenProvider,
)
from src.services.freespace.keys import device_id_suffix
from tests.freespace.test_m7_support import (
    drive_fanout,
    install_engine_recorder,
    make_advisory_event,
    make_devices,
    reload_event,
    session_factory_for,
)
from tests.freespace.test_m8_admin_ops import BASE, DEVICE_ID, h, make_device


# ─────────────────────────────────────────────────────────────
# F1: token refresh transport errors
# ─────────────────────────────────────────────────────────────


class _Creds:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.valid = False
        self.token = None

    def refresh(self, request) -> None:
        raise self.exc


@pytest.mark.parametrize(
    "exc",
    [
        google.auth.exceptions.TransportError("dns failure"),
        google.auth.exceptions.TimeoutError("timed out"),
        TimeoutError("timed out"),
    ],
)
def test_refresh_transport_error_is_transient(exc):
    with pytest.raises(FcmTokenUnavailableError):
        ServiceAccountTokenProvider._refresh(_Creds(exc))


def test_refresh_refusal_is_credentials_error():
    with pytest.raises(FcmCredentialsError):
        ServiceAccountTokenProvider._refresh(
            _Creds(google.auth.exceptions.RefreshError("invalid_grant"))
        )


class _FlakyTokens:
    """Fails ``failures`` times with a transient error, then yields a token."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self.invalidated = 0

    async def get_token(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise FcmTokenUnavailableError("OAuth endpoint unreachable")
        return "ya29.ok"

    def invalidate(self) -> None:
        self.invalidated += 1


def _accepting_client(tokens: _FlakyTokens) -> tuple[HttpFcmClient, list]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json={"name": f"projects/p/messages/{len(requests)}"}
        )

    client = HttpFcmClient(
        "/unused.json",
        "p",
        token_provider=tokens,
        transport=httpx.MockTransport(handler),
    )
    return client, requests


async def test_http_client_token_transport_error_is_retryable():
    tokens = _FlakyTokens(failures=1)
    client, requests = _accepting_client(tokens)
    result = await client.send(FcmMessage(payload={}, token="T"))
    assert result.kind == FcmResultKind.RETRYABLE
    assert result.error_code == TOKEN_UNAVAILABLE_ERROR_CODE
    assert requests == []  # nothing reached FCM
    assert tokens.invalidated == 0  # not treated as a broken credential
    assert (await client.send(FcmMessage(payload={}, token="T"))).kind == (
        FcmResultKind.ACCEPTED
    )


async def test_fanout_retries_after_token_transport_error(
    async_session, fs_site, fixed_clock, monkeypatch
):
    """Every send of the chunk RETRYABLE -> re-enqueued with backoff, then
    COMPLETED; never FAILED, no FCM_ERROR event."""
    install_engine_recorder(monkeypatch)
    await make_devices(async_session, [fs_site], 2, now=fixed_clock.now())
    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    tokens = _FlakyTokens(failures=2)  # both devices of the first chunk
    client, requests = _accepting_client(tokens)

    results = await drive_fanout(
        session_factory_for(async_session), event.id, fixed_clock, client
    )

    first = results[0]
    assert first.status == FanoutStatus.RUNNING
    assert first.reenqueue_in_s is not None and first.reenqueue_in_s > 0
    assert results[-1].status == FanoutStatus.COMPLETED
    row = await reload_event(async_session, event.id)
    assert row.fanout_status == FanoutStatus.COMPLETED.value
    assert row.counts == {DeviceOutcome.SENT.value: 2}
    assert len(requests) == 2
    errors = (
        (
            await async_session.execute(
                select(SiteEvent).where(SiteEvent.type == EventType.FCM_ERROR.value)
            )
        )
        .scalars()
        .all()
    )
    assert errors == []


# ─────────────────────────────────────────────────────────────
# F2: event committed before the FCM call
# ─────────────────────────────────────────────────────────────


async def _events(session, event_type: EventType) -> list[SiteEvent]:
    return list(
        (
            await session.execute(
                select(SiteEvent)
                .where(SiteEvent.type == event_type.value)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def _trace_commits_and_sends(monkeypatch, session, fake_fcm) -> list[str]:
    trace: list[str] = []
    real_commit = session.commit
    real_send = fake_fcm.send

    async def commit() -> None:
        trace.append("commit")
        await real_commit()

    async def send(message: FcmMessage) -> FcmSendResult:
        trace.append("send")
        return await real_send(message)

    monkeypatch.setattr(session, "commit", commit)
    monkeypatch.setattr(fake_fcm, "send", send)
    return trace


def _announce(client, site, token):
    return client.post(
        f"{BASE}/{site.id}/announcements",
        headers=h(token),
        json={"message": "Car park closes early", "confirm_topic": site.fcm_topic},
    )


async def test_announcement_event_committed_before_send(
    client, async_session, fs_site, fs_admin_token, fake_fcm, monkeypatch
):
    trace = _trace_commits_and_sends(monkeypatch, async_session, fake_fcm)
    r = await _announce(client, fs_site, fs_admin_token)
    assert r.status_code == 200
    assert trace.index("commit") < trace.index("send")
    assert trace[-1] == "commit"  # result recorded afterwards
    (event,) = await _events(async_session, EventType.ANNOUNCEMENT)
    assert str(event.id) == r.json()["event_id"]
    assert event.reason == admin_push.ACCEPTED_BY_FCM
    assert event.details["outcome"] == admin_push.ACCEPTED_BY_FCM


async def test_device_test_push_event_committed_before_send(
    client, async_session, fs_site, fs_admin_token, fake_fcm, fixed_clock, monkeypatch
):
    await make_device(
        async_session, fixed_clock.now(), device_id=DEVICE_ID, sites=[fs_site]
    )
    trace = _trace_commits_and_sends(monkeypatch, async_session, fake_fcm)
    r = await client.post(
        f"{BASE}/{fs_site.id}/test-push",
        headers=h(fs_admin_token),
        json={"target": "device", "device_suffix": device_id_suffix(DEVICE_ID)},
    )
    assert r.status_code == 200
    assert trace.index("commit") < trace.index("send")
    (event,) = await _events(async_session, EventType.TEST_PUSH)
    assert event.reason == admin_push.ACCEPTED_BY_FCM
    assert event.counts == {DeviceOutcome.SENT.value: 1}
    assert event.fanout_status is None


async def test_db_failure_before_send_sends_nothing(
    client, async_session, fs_site, fs_admin_token, fake_fcm, monkeypatch
):
    async def broken(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(freespace_push, "write_event", broken)
    r = await _announce(client, fs_site, fs_admin_token)
    assert r.status_code == 500
    assert fake_fcm.sent == []


async def test_post_send_db_failure_keeps_pending_event_and_no_resend(
    client, async_session, fs_site, fs_admin_token, fake_fcm, fixed_clock, monkeypatch
):
    async def broken(*args, **kwargs):
        raise RuntimeError("db down after send")

    monkeypatch.setattr(admin_push, "apply_fcm_error_handling", broken)
    r = await _announce(client, fs_site, fs_admin_token)
    # FCM accepted it: report that, so the caller has no reason to retry.
    assert r.status_code == 200
    assert r.json()["accepted_by_fcm"] is True
    assert len(fake_fcm.sent) == 1
    (event,) = await _events(async_session, EventType.ANNOUNCEMENT)
    assert str(event.id) == r.json()["event_id"]
    assert event.reason == freespace_push.PENDING_OUTCOME
    assert event.details["outcome"] == freespace_push.PENDING_OUTCOME
    assert event.fanout_status is None
    # Not picked up by the fan-out recovery sweep, however old it gets.
    later = fixed_clock.now() + timedelta(days=1)
    assert event.id not in await recover_stuck_fanouts(async_session, later)
