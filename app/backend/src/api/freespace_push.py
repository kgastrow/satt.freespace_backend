"""
Admin: test push (BF-74) and announcement (BF-75). OWNER: M8.

Prefix ``/admin/sites/{site_id}``. Permissions: ``site_push:test`` /
``site_push:announce``. Wording: "accepted by FCM", never "delivered" (BF-69).

The event (``TEST_PUSH`` / ``ANNOUNCEMENT``) is committed BEFORE an FCM
failure is raised, so a failed send is still logged with its outcome.
"""

from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.api.freespace_sites import internal_error, require_site
from src.constants.freespace import (
    PERM_SITE_PUSH_ANNOUNCE,
    PERM_SITE_PUSH_TEST,
    AdvisoryType,
    DeviceOutcome,
    EventType,
)
from src.core.exceptions import create_http_exception
from src.models.device import Device, DeviceSite
from src.models.site import Site
from src.serialisers.freespace_push import (
    AnnouncementRequest,
    PushResponse,
    TestPushRequest,
)
from src.services.freespace import admin_push, fanout
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.events import write_event
from src.services.freespace.fcm import (
    FcmClient,
    FcmResultKind,
    FcmSendResult,
    get_fcm_client,
)
from src.services.freespace.loaders import load_templates
from src.services.freespace.types import EventDraft


router = APIRouter(prefix="/admin/sites/{site_id}", tags=["freespace-admin-push"])

TestUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITE_PUSH_TEST))]
AnnounceUser = Annotated[
    CurrentUser, Depends(require_permission(PERM_SITE_PUSH_ANNOUNCE))
]
Session = Annotated[AsyncSession, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]

_SUFFIX_RE = re.compile(r"^[A-Za-z0-9_-]{6}$")


def _error(code: int, detail: str, detail_code: str) -> HTTPException:
    return create_http_exception(
        status_code=code, detail=detail, detail_code=detail_code
    )


def _require_topic_confirmation(site: Site, confirm_topic: str | None) -> None:
    if not confirm_topic:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Repeat the topic name to confirm",
            "site_push.confirmation_required",
        )
    if confirm_topic != site.fcm_topic:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Confirmation does not match the topic name",
            "site_push.confirmation_mismatch",
        )


def _fcm() -> FcmClient:
    try:
        return get_fcm_client()
    except RuntimeError:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "FCM is not configured",
            "site_push.fcm_not_configured",
        )


async def _find_device_token(
    session: AsyncSession, site: Site, suffix: str
) -> tuple[UUID, str]:
    """``(device id, token)`` of the ONE live device on this site whose id
    ends in ``suffix``.
    Zero matches (or a device that did not select this site) -> 404; more than
    one -> 409. Candidates are never listed."""
    rows = (
        (
            await session.execute(
                select(Device.id, Device.fcm_token)
                .join(DeviceSite, DeviceSite.device_id == Device.id)
                .where(
                    DeviceSite.site_id == site.id,
                    Device.id_suffix == suffix,
                    Device.deleted_time.is_(None),
                )
            )
        )
        .tuples()
        .all()
    )
    if not rows:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "No device with that id ending has selected this site",
            "site_push.device_not_found",
        )
    if len(rows) > 1:
        raise _error(
            status.HTTP_409_CONFLICT,
            "More than one device matches; the id ending is ambiguous",
            "site_push.device_ambiguous",
        )
    device_id, token = rows[0]
    if not token:
        raise _error(
            status.HTTP_409_CONFLICT,
            "The device has no push token",
            "site_push.device_no_token",
        )
    return device_id, str(token)


async def _log_and_finish(
    session: AsyncSession,
    *,
    site: Site,
    draft: EventDraft,
    outcome: admin_push.PushOutcome,
    target: str,
    ok_code: str,
    ok_message: str,
    fail_code: str,
    fail_message: str,
    result: FcmSendResult,
    device: tuple[UUID, str] | None = None,
) -> PushResponse:
    await write_event(
        session, site_id=site.id, organization_id=site.organization_id, draft=draft
    )
    # The fan-out's FCM error handling (BF-66, BF-67, BF-82).
    auth_failure = await admin_push.apply_fcm_error_handling(
        session,
        site=site,
        event_id=draft.id,
        result=result,
        now=draft.occurred_at,
        device=device,
        advisory_type=draft.advisory_type,
    )
    await session.commit()
    if auth_failure is not None:
        await fanout.record_fcm_auth_failure(auth_failure)
    if not outcome.accepted:
        code = (
            "site_push.fcm_auth_failure"
            if outcome.kind == FcmResultKind.AUTH_FAILURE
            else fail_code
        )
        raise _error(status.HTTP_502_BAD_GATEWAY, fail_message, code)
    return PushResponse(
        message=ok_message,
        message_code=ok_code,
        event_id=draft.id,
        target=target,  # type: ignore[arg-type]
        outcome=outcome.outcome,
        accepted_by_fcm=True,
        latency_ms=outcome.latency_ms,
    )


@router.post("/test-push", response_model=PushResponse)
async def test_push(
    site_id: UUID,
    request: TestPushRequest,
    http_request: Request,
    current_user: TestUser,
    session: Session,
    clock: ClockDep,
):
    """BF-74. Works for unmanaged sites; bypasses per-phone checks; not
    counted against limits (type ``TEST``)."""
    try:
        site = await require_site(session, site_id, current_user)
        device: tuple[UUID, str] | None = None
        if request.target == "device":
            if not request.device_suffix or not _SUFFIX_RE.match(request.device_suffix):
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "A 6-character device id ending is required",
                    "site_push.invalid_target",
                )
            device = await _find_device_token(session, site, request.device_suffix)
        else:
            if request.device_suffix:
                raise _error(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "A topic test push takes no device id ending",
                    "site_push.invalid_target",
                )
            _require_topic_confirmation(site, request.confirm_topic)

        fcm = _fcm()
        template = (await load_templates(session, site.id)).get(AdvisoryType.TEST)
        title, body = admin_push.render_test_message(site, template)
        now = clock.now()
        event_id = EventDraft(type=EventType.TEST_PUSH, occurred_at=now).id
        if device is not None:
            result = await admin_push.send_test_to_device(
                fcm,
                site=site,
                token=device[1],
                title=title,
                body=body,
                event_id=event_id,
                now=now,
            )
        else:
            result = await admin_push.send_test_to_topic(
                fcm, site=site, title=title, body=body, event_id=event_id, now=now
            )
        outcome = admin_push.outcome_of(result)
        draft = EventDraft(
            id=event_id,
            type=EventType.TEST_PUSH,
            occurred_at=now,
            reason=outcome.outcome,
            advisory_type=AdvisoryType.TEST,
            rendered_title=title,
            rendered_body=body,
            counts=(
                {DeviceOutcome.SENT.value: 1}
                if device is not None and outcome.accepted
                else None
            ),
            details=admin_push.event_details(
                request.target, outcome, str(current_user.id)
            ),
        )
        return await _log_and_finish(
            session,
            site=site,
            draft=draft,
            outcome=outcome,
            target=request.target,
            ok_code="site_push.test_sent",
            ok_message="Test push accepted by FCM",
            fail_code="site_push.test_failed",
            fail_message="Test push was not accepted by FCM",
            result=result,
            device=device,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "test_push", exc)


@router.post("/announcements", response_model=PushResponse)
async def announce(
    site_id: UUID,
    request: AnnouncementRequest,
    http_request: Request,
    current_user: AnnounceUser,
    session: Session,
    clock: ClockDep,
):
    """BF-75. Free text to the site's topic: ONE FCM call, logged as
    ``ANNOUNCEMENT``. Administrator only. Refused (409) for an unmanaged
    site: nothing but a TEST is ever sent for one (BF-61), and its topic may
    still belong to ParkIT's legacy notifier (spec §15.1)."""
    try:
        site = await require_site(session, site_id, current_user)
        if not site.managed:
            raise _error(
                status.HTTP_409_CONFLICT,
                "Announcements can only be sent for a managed site",
                "site_push.site_unmanaged",
            )
        _require_topic_confirmation(site, request.confirm_topic)
        fcm = _fcm()
        title = (request.title or "").strip() or site.name[:65]
        now = clock.now()
        event_id = EventDraft(type=EventType.ANNOUNCEMENT, occurred_at=now).id
        result = await admin_push.send_announcement(
            fcm,
            site=site,
            title=title,
            body=request.message,
            event_id=event_id,
            now=now,
        )
        outcome = admin_push.outcome_of(result)
        draft = EventDraft(
            id=event_id,
            type=EventType.ANNOUNCEMENT,
            occurred_at=now,
            reason=outcome.outcome,
            rendered_title=title,
            rendered_body=request.message,
            details=admin_push.event_details("topic", outcome, str(current_user.id)),
        )
        return await _log_and_finish(
            session,
            site=site,
            draft=draft,
            outcome=outcome,
            target="topic",
            ok_code="site_push.announcement_sent",
            ok_message="Announcement accepted by FCM",
            fail_code="site_push.announcement_failed",
            fail_message="Announcement was not accepted by FCM",
            result=result,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "announce", exc)
