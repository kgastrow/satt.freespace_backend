"""Back-office pushes: test push (BF-74) and announcement (BF-75). OWNER: M8.

Both bypass every per-phone check, are never counted against cooldown or caps
and write no ``push_send`` row. A topic send is ONE FCM call (BF-41), not a
fan-out. Wording (BF-69): ``ACCEPTED_BY_FCM``, never "delivered".

FCM errors are handled exactly as in the fan-out (BF-66, BF-67, BF-82), by the
fan-out's own functions (``apply_fcm_error_handling``): a token-invalid answer
to a device test push sets ``token_invalidated_at``; a 401/403 writes an
``FCM_ERROR / AUTH_FAILURE`` event and, after commit, is recorded for the
operator alert (``fanout.record_fcm_auth_failure``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import AdvisoryType
from src.crud import freespace_push_send as sends
from src.models.site import Site
from src.services.freespace import fanout, templates
from src.services.freespace.fcm import (
    FcmClient,
    FcmResultKind,
    FcmSendResult,
    build_data_payload,
    build_message,
    send_to_topic,
)
from src.services.freespace.types import MessageTemplate


ACCEPTED_BY_FCM = "ACCEPTED_BY_FCM"
ANNOUNCEMENT_MESSAGE_TYPE = "ANNOUNCEMENT"


@dataclass(frozen=True)
class PushOutcome:
    accepted: bool
    outcome: str  # ACCEPTED_BY_FCM or the FcmResultKind name
    kind: FcmResultKind
    error_code: str | None
    latency_ms: int


def outcome_of(result: FcmSendResult) -> PushOutcome:
    accepted = result.kind == FcmResultKind.ACCEPTED
    return PushOutcome(
        accepted=accepted,
        outcome=ACCEPTED_BY_FCM if accepted else result.kind.value,
        kind=result.kind,
        error_code=result.error_code,
        latency_ms=int(result.latency_ms or 0),
    )


def render_test_message(
    site: Site, template: MessageTemplate | None
) -> tuple[str, str]:
    """Title/body of the TEST template (site override, else the default)."""
    if template is None:
        title, body = templates.DEFAULT_TEMPLATES[AdvisoryType.TEST]
        template = MessageTemplate(AdvisoryType.TEST, title, body, "en")
    context = templates.build_context(
        site_name=site.name, zone_name=None, top_zone_names=(), occupancy_pct=None
    )
    rendered = templates.render(template, context)
    return rendered.title, rendered.body


async def send_test_to_device(
    fcm: FcmClient,
    *,
    site: Site,
    token: str,
    title: str,
    body: str,
    event_id: uuid.UUID,
    now: datetime,
) -> FcmSendResult:
    data = build_data_payload(
        message_type=AdvisoryType.TEST,
        site_slug=site.slug,
        recommended_zone_slug=None,
        occupancy_pct=None,
        event_id=str(event_id),
        sent_at=now,
    )
    message = build_message(
        title=title,
        body=body,
        data=data,
        site_slug=site.slug,
        sent_at=now,
        ttl_s=site.push_expiry_s,
        token=token,
    )
    return await fcm.send(message)


async def send_test_to_topic(
    fcm: FcmClient,
    *,
    site: Site,
    title: str,
    body: str,
    event_id: uuid.UUID,
    now: datetime,
) -> FcmSendResult:
    return await send_to_topic(
        fcm,
        topic=site.fcm_topic,
        title=title,
        body=body,
        message_type=AdvisoryType.TEST,
        site_slug=site.slug,
        event_id=str(event_id),
        sent_at=now,
        ttl_s=site.push_expiry_s,
    )


async def send_announcement(
    fcm: FcmClient,
    *,
    site: Site,
    title: str,
    body: str,
    event_id: uuid.UUID,
    now: datetime,
) -> FcmSendResult:
    return await send_to_topic(
        fcm,
        topic=site.fcm_topic,
        title=title,
        body=body,
        message_type=ANNOUNCEMENT_MESSAGE_TYPE,
        site_slug=site.slug,
        event_id=str(event_id),
        sent_at=now,
        ttl_s=site.push_expiry_s,
    )


async def apply_fcm_error_handling(
    session: AsyncSession,
    *,
    site: Site,
    event_id: uuid.UUID,
    result: FcmSendResult,
    now: datetime,
    device: tuple[uuid.UUID, str] | None = None,
    advisory_type: AdvisoryType | None = None,
) -> fanout.FcmAuthFailure | None:
    """BF-66 / BF-67 / BF-82 for one back-office send whose event
    ``event_id`` has been written (flush only; the caller commits).

    ``device`` = ``(device_id, token)`` of a device test push. Returns the
    auth failure to pass to ``fanout.record_fcm_auth_failure`` AFTER the
    commit, or None."""
    if result.kind == FcmResultKind.TOKEN_INVALID and device is not None:
        await sends.invalidate_tokens(session, [device], now)
        return None
    if result.kind != FcmResultKind.AUTH_FAILURE:
        return None
    fcm_error_event_id = await fanout.write_fcm_error_event(
        session,
        site_id=site.id,
        organization_id=site.organization_id,
        event_id=event_id,
        result=result,
        now=now,
        advisory_type=advisory_type,
    )
    return fanout.FcmAuthFailure(
        occurred_at=now,
        organization_id=site.organization_id,
        site_id=site.id,
        site_slug=site.slug,
        event_id=event_id,
        fcm_error_event_id=fcm_error_event_id,
        error_code=result.error_code,
        http_status=result.http_status,
    )


def event_details(
    target: str, outcome: PushOutcome, user_id: str | None
) -> dict[str, Any]:
    """Small, device-free ``details`` of a TEST_PUSH / ANNOUNCEMENT event."""
    return {
        "target": target,
        "outcome": outcome.outcome,
        "fcm_error_code": outcome.error_code,
        "latency_ms": outcome.latency_ms,
        "sent_by": user_id,
    }
