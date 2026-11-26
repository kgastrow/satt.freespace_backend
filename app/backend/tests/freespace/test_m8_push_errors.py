"""M8 review fixes: announcements only for managed sites (BF-61, BF-75) and
the fan-out's FCM error handling on the back-office push path (BF-66, BF-67,
BF-82)."""

from __future__ import annotations

from sqlalchemy import select

from src.constants.freespace import EventType, FcmErrorReason
from src.models.device import Device
from src.models.site_event import SiteEvent
from src.services.freespace.fanout import (
    FcmAuthFailure,
    register_fcm_auth_failure_hook,
    unregister_fcm_auth_failure_hook,
)
from src.services.freespace.fcm import FcmResultKind, FcmSendResult
from src.services.freespace.keys import device_id_suffix
from tests.freespace.conftest import make_site
from tests.freespace.test_m8_admin_ops import BASE, DEVICE_ID, h, make_device


def push_url(site) -> str:
    return f"{BASE}/{site.id}/test-push"


def announce_url(site) -> str:
    return f"{BASE}/{site.id}/announcements"


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


class _Hook:
    def __init__(self) -> None:
        self.failures: list[FcmAuthFailure] = []

    async def __call__(self, failure: FcmAuthFailure) -> None:
        self.failures.append(failure)


async def test_announcement_refused_for_unmanaged_site(
    client, async_session, test_organization, fs_admin_token, fake_fcm
):
    site = await make_site(
        async_session, test_organization, slug="shadow-ann", managed=False
    )
    r = await client.post(
        announce_url(site),
        headers=h(fs_admin_token),
        json={"message": "Hi", "confirm_topic": site.fcm_topic},
    )
    assert r.status_code == 409
    assert r.json()["detail_code"] == "site_push.site_unmanaged"
    assert fake_fcm.sent == []
    assert await _events(async_session, EventType.ANNOUNCEMENT) == []
    # a TEST push to the same unmanaged site still works (BF-74)
    r = await client.post(
        push_url(site),
        headers=h(fs_admin_token),
        json={"target": "topic", "confirm_topic": site.fcm_topic},
    )
    assert r.status_code == 200
    assert len(fake_fcm.sent) == 1


async def test_test_push_auth_failure_writes_fcm_error_and_alerts(
    client, async_session, fs_site, fs_admin_token, fake_fcm
):
    hook = _Hook()
    register_fcm_auth_failure_hook(hook)
    try:
        fake_fcm.default_result = FcmSendResult(
            kind=FcmResultKind.AUTH_FAILURE, http_status=401, error_code="UNAUTH"
        )
        r = await client.post(
            push_url(fs_site),
            headers=h(fs_admin_token),
            json={"target": "topic", "confirm_topic": fs_site.fcm_topic},
        )
    finally:
        unregister_fcm_auth_failure_hook(hook)
    assert r.status_code == 502
    assert r.json()["detail_code"] == "site_push.fcm_auth_failure"
    (test_event,) = await _events(async_session, EventType.TEST_PUSH)
    (error,) = await _events(async_session, EventType.FCM_ERROR)
    assert error.reason == FcmErrorReason.AUTH_FAILURE.value
    assert error.details["eventId"] == str(test_event.id)
    assert error.details["httpStatus"] == 401
    (failure,) = hook.failures
    assert failure.event_id == test_event.id
    assert failure.fcm_error_event_id == error.id
    assert failure.site_id == fs_site.id


async def test_announcement_auth_failure_writes_fcm_error_and_alerts(
    client, async_session, fs_site, fs_admin_token, fake_fcm
):
    hook = _Hook()
    register_fcm_auth_failure_hook(hook)
    try:
        fake_fcm.default_result = FcmSendResult(
            kind=FcmResultKind.AUTH_FAILURE, http_status=403
        )
        r = await client.post(
            announce_url(fs_site),
            headers=h(fs_admin_token),
            json={"message": "Hi", "confirm_topic": fs_site.fcm_topic},
        )
    finally:
        unregister_fcm_auth_failure_hook(hook)
    assert r.json()["detail_code"] == "site_push.fcm_auth_failure"
    (announcement,) = await _events(async_session, EventType.ANNOUNCEMENT)
    (error,) = await _events(async_session, EventType.FCM_ERROR)
    assert error.details["eventId"] == str(announcement.id)
    assert [f.fcm_error_event_id for f in hook.failures] == [error.id]


async def test_device_test_push_token_invalid_invalidates_token(
    client, async_session, fs_site, fs_admin_token, fake_fcm, fixed_clock
):
    device = await make_device(
        async_session, fixed_clock.now(), device_id=DEVICE_ID, sites=[fs_site]
    )
    fake_fcm.default_result = FcmSendResult(
        kind=FcmResultKind.TOKEN_INVALID, error_code="UNREGISTERED", http_status=404
    )
    r = await client.post(
        push_url(fs_site),
        headers=h(fs_admin_token),
        json={"target": "device", "device_suffix": device_id_suffix(DEVICE_ID)},
    )
    assert r.status_code == 502
    assert r.json()["detail_code"] == "site_push.test_failed"
    row = (
        await async_session.execute(
            select(Device)
            .where(Device.id == device.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.token_invalidated_at is not None
    assert await _events(async_session, EventType.FCM_ERROR) == []
