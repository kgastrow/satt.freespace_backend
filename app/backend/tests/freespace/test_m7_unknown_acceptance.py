"""M7 regression (BF-58, BF-63, BF-52): a send whose acceptance by FCM is
UNKNOWN (client exception, read timeout / no response, crash) counts towards
the per-phone limits exactly like a SENT one and is never retried; a send FCM
definitely did not accept (connection refused before sending, explicit
non-retryable error, retry window exhausted, expired without a call, token
invalid) does not count."""

from __future__ import annotations

import httpx
import pytest

from src.constants.freespace import (
    SEND_ERROR_CLIENT,
    DeviceOutcome,
    send_counts_towards_limits,
)
from src.services.freespace.fanout import ERROR_EXPIRED, ERROR_RETRY_WINDOW
from src.services.freespace.fcm import (
    FcmMessage,
    FcmResultKind,
    FcmSendResult,
    HttpFcmClient,
)
from tests.freespace.test_m7_support import (
    drive_fanout,
    install_engine_recorder,
    make_advisory_event,
    make_devices,
    reload_event,
    send_rows,
    session_factory_for,
    use_deployment_settings,
)


@pytest.fixture(autouse=True)
def _engine(monkeypatch):
    return install_engine_recorder(monkeypatch)


# ── the rule itself ───────────────────────────────────────────


@pytest.mark.parametrize(
    "outcome,error_code,counted",
    [
        ("SENT", None, True),
        ("PENDING", None, True),
        ("PENDING", "RETRY:QUOTA_EXCEEDED", True),
        ("SEND_FAILED", "UNKNOWN_AFTER_CRASH", True),
        ("SEND_FAILED", "CLIENT_ERROR", True),
        ("SEND_FAILED", "NO_RESPONSE_ReadTimeout", True),
        ("SEND_FAILED", "NO_RESPONSE_RemoteProtocolError", True),
        ("SEND_FAILED", "NETWORK_ConnectError", False),
        ("SEND_FAILED", "NETWORK_ConnectTimeout", False),
        ("SEND_FAILED", "INVALID_ARGUMENT", False),
        ("SEND_FAILED", "RETRY_WINDOW_EXHAUSTED", False),
        ("SEND_FAILED", "EXPIRED", False),
        ("SEND_FAILED", "FANOUT_STOPPED", False),
        ("SEND_FAILED", "CREDENTIALS_ERROR", False),
        ("SEND_FAILED", None, False),
        ("TOKEN_INVALID", "UNREGISTERED", False),
        ("COOLDOWN", None, False),
        ("DUPLICATE", None, False),
        ("DAILY_CAP", None, False),
        ("OPTED_OUT", None, False),
        ("OUTSIDE_WINDOW", None, False),
    ],
)
def test_counting_rule(outcome, error_code, counted):
    assert send_counts_towards_limits(outcome, error_code) is counted


# ── the HTTP client classifies transport errors by "did it leave?" ─────


def _client(handler) -> HttpFcmClient:
    class _Tokens:
        async def get_token(self) -> str:
            return "access"

        def invalidate(self) -> None:
            pass

    return HttpFcmClient(
        credentials_path="/nonexistent",
        project_id="p",
        token_provider=_Tokens(),
        transport=httpx.MockTransport(handler),
    )


def _raise(exc_type):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("boom", request=request)

    return handler


async def test_read_timeout_is_unknown_and_counted():
    result = await _client(_raise(httpx.ReadTimeout)).send(
        FcmMessage(payload={}, token="t")
    )
    assert result.kind == FcmResultKind.FAILED
    assert send_counts_towards_limits("SEND_FAILED", result.error_code)


async def test_connect_error_is_retryable_and_not_counted():
    result = await _client(_raise(httpx.ConnectError)).send(
        FcmMessage(payload={}, token="t")
    )
    assert result.kind == FcmResultKind.RETRYABLE
    assert not send_counts_towards_limits("SEND_FAILED", result.error_code)


# ── end to end through the fan-out ────────────────────────────


class _Raises:
    """FCM client whose send raises for listed tokens (after "sending")."""

    def __init__(self, inner, tokens):
        self.inner = inner
        self.tokens = set(tokens)
        self.calls: list[str | None] = []

    async def send(self, message):
        self.calls.append(message.token)
        if message.token in self.tokens:
            raise RuntimeError("socket closed after write")
        return await self.inner.send(message)

    async def aclose(self):
        await self.inner.aclose()


async def _second_advisory_outcome(async_session, fs_site, fixed_clock, fcm):
    factory = session_factory_for(async_session)
    fixed_clock.advance(60)
    second = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(factory, second.id, fixed_clock, fcm)
    return (await reload_event(async_session, second.id)).counts


async def test_client_exception_counts_for_cooldown_and_is_not_retried(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    use_deployment_settings(monkeypatch, cooldown_s=1800, daily_cap=5)
    (device,) = await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    fcm = _Raises(fake_fcm, [device.fcm_token])
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(session_factory_for(async_session), first.id, fixed_clock, fcm)

    (row,) = await send_rows(async_session, first.id)
    assert row.outcome == DeviceOutcome.SEND_FAILED.value
    assert row.error_code == SEND_ERROR_CLIENT
    assert fcm.calls == [device.fcm_token]  # exactly once: never retried

    counts = await _second_advisory_outcome(async_session, fs_site, fixed_clock, fcm)
    assert counts == {DeviceOutcome.COOLDOWN.value: 1}
    assert fcm.calls == [device.fcm_token]  # no second push inside the cooldown


async def test_client_exception_counts_for_daily_cap(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    use_deployment_settings(monkeypatch, cooldown_s=0, daily_cap=1)
    (device,) = await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    fcm = _Raises(fake_fcm, [device.fcm_token])
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(session_factory_for(async_session), first.id, fixed_clock, fcm)
    counts = await _second_advisory_outcome(async_session, fs_site, fixed_clock, fcm)
    assert counts == {DeviceOutcome.DAILY_CAP.value: 1}


async def test_no_response_counts_for_cooldown(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch
):
    use_deployment_settings(monkeypatch, cooldown_s=1800, daily_cap=5)
    (device,) = await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    fake_fcm.results_by_token[device.fcm_token] = [
        FcmSendResult(kind=FcmResultKind.FAILED, error_code="NO_RESPONSE_ReadTimeout"),
        FcmSendResult(kind=FcmResultKind.ACCEPTED, message_id="m"),
    ]
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(
        session_factory_for(async_session), first.id, fixed_clock, fake_fcm
    )
    assert len(fake_fcm.sent) == 1
    counts = await _second_advisory_outcome(
        async_session, fs_site, fixed_clock, fake_fcm
    )
    assert counts == {DeviceOutcome.COOLDOWN.value: 1}
    assert len(fake_fcm.sent) == 1


@pytest.mark.parametrize(
    "result",
    [
        FcmSendResult(
            kind=FcmResultKind.FAILED, error_code="INVALID_ARGUMENT", http_status=400
        ),
        FcmSendResult(kind=FcmResultKind.FAILED, error_code="NETWORK_ConnectError"),
        FcmSendResult(kind=FcmResultKind.FAILED, error_code=ERROR_RETRY_WINDOW),
        FcmSendResult(kind=FcmResultKind.FAILED, error_code=ERROR_EXPIRED),
    ],
    ids=["explicit-400", "refused-before-send", "retry-window", "expired"],
)
async def test_definite_failure_does_not_count(
    async_session, fs_site, fixed_clock, fake_fcm, monkeypatch, result
):
    use_deployment_settings(monkeypatch, cooldown_s=1800, daily_cap=1)
    (device,) = await make_devices(async_session, [fs_site], 1, now=fixed_clock.now())
    fake_fcm.results_by_token[device.fcm_token] = [
        result,
        FcmSendResult(kind=FcmResultKind.ACCEPTED, message_id="m"),
    ]
    first = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    await drive_fanout(
        session_factory_for(async_session), first.id, fixed_clock, fake_fcm
    )
    counts = await _second_advisory_outcome(
        async_session, fs_site, fixed_clock, fake_fcm
    )
    assert counts == {DeviceOutcome.SENT.value: 1}
