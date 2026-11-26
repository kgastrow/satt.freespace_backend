"""
Operator alerts by email (BF-82, BF-37, BF-66, BF-18). OWNER: M9.

Entry point: ``run_alert_checks(session, clock)``, called once a minute from
the engine tick. It checks four conditions and sends each alert through the
template's notification dispatcher to every user holding permission
``site_alerts:receive`` plus super admins:

1. A managed site has had no accepted ingest for ``SILENCE_THRESHOLD_S`` and,
   later, recovers. Fires once per transition; the state lives in
   ``site_engine_state.ops_alert_state["silent_alerted_at"]``. Unmanaged sites
   never alert (shadow mode).
2. FCM credential failure: Redis key ``REDIS_FCM_AUTH_FAILURE_KEY`` written by
   ``fanout.record_fcm_auth_failure``. At most one email per
   ``FCM_ALERT_COOLDOWN_S``.
3. Device ceiling reached: Redis key ``DEVICE_CEILING_ALERT_KEY`` written by
   ``devices.record_device_ceiling_alert``. One email per raised window.
4. Ingest rejection rate above ``REJECTION_THRESHOLD_PER_MIN`` a minute. Counted
   from ``INGEST_REJECTED`` events of the last minute plus the Redis counters
   written by ``record_ingest_rejection`` (for requests that write no event:
   429 and unknown-key 401). One email per episode (re-armed once the rate has
   stayed below the threshold for ``REJECTION_EPISODE_TTL_S``).

Alerts carry site names and counts only: never a device id, a token, an ingest
key or a request path. A missing template falls back to the plain-text body.
One failing check never stops the others and never raises into the tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Final
import uuid

from sqlalchemy import ColumnElement, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    PERM_SITE_ALERTS_RECEIVE,
    EventType,
)
from src.logger.logger import Logger as logger
from src.models.ingest_key import IngestKey
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.models.site_snapshot import SiteSnapshot
from src.models.user import SuspensionStatus, User
from src.models.user_role import UserRole
from src.services.freespace.clock import Clock, ensure_utc
from src.services.freespace.devices import DEVICE_CEILING_ALERT_KEY
from src.services.freespace.redis_client import get_redis
from src.services.notifications.dispatcher import notification_dispatcher


ALERT_CATEGORY: Final = "site_operations"

TEMPLATE_SITE_SILENT: Final = "freespace_site_silent"
TEMPLATE_SITE_RECOVERED: Final = "freespace_site_recovered"
TEMPLATE_FCM_FAILURE: Final = "freespace_fcm_credential_failure"
TEMPLATE_DEVICE_CEILING: Final = "freespace_device_ceiling_reached"
TEMPLATE_INGEST_REJECTIONS: Final = "freespace_ingest_rejection_rate"
ALERT_TEMPLATE_CODES: Final = (
    TEMPLATE_SITE_SILENT,
    TEMPLATE_SITE_RECOVERED,
    TEMPLATE_FCM_FAILURE,
    TEMPLATE_DEVICE_CEILING,
    TEMPLATE_INGEST_REJECTIONS,
)

SILENCE_THRESHOLD_S: Final = 600  # BF-82: 10 minutes
REJECTION_THRESHOLD_PER_MIN: Final = 10  # BF-82: more than 10 a minute
REJECTION_WINDOW_S: Final = 60
REJECTION_EPISODE_TTL_S: Final = 900
REJECTION_COUNTER_TTL_S: Final = 300
# Hard cap on one rejection sorted set (review F5). The alert only needs to know
# the rate exceeds REJECTION_THRESHOLD_PER_MIN, so keeping the newest entries
# is enough; trimming on write bounds memory between once-a-minute ticks.
REJECTION_COUNTER_MAX_ENTRIES: Final = 1000
FCM_ALERT_COOLDOWN_S: Final = 3600
CEILING_MARKER_TTL_S: Final = 7200

# Redis keys owned by M9
REDIS_REJECTION_KEY_PREFIX: Final = "freespace:alerts:ingest_rejects:"
REDIS_REJECTION_EPISODE_FMT: Final = "freespace:alerts:ingest_rejects_active:{subject}"
REDIS_FCM_COOLDOWN_KEY: Final = "freespace:alerts:fcm_sent"
REDIS_CEILING_MARKER_KEY: Final = "freespace:alerts:device_ceiling_notified"
UNKNOWN_KEY_ID: Final = "unknown"


def _fcm_failure_key() -> str:
    from src.services.freespace.fanout import REDIS_FCM_AUTH_FAILURE_KEY

    return REDIS_FCM_AUTH_FAILURE_KEY


# ─────────────────────────────────────────────────────────────
# Recipients and delivery
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AlertRecipient:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class Alert:
    template_code: str
    subject: str
    content: str
    variables: dict[str, str]
    # Tenant the alert concerns; None = deployment-wide (every organization).
    organization_id: uuid.UUID | None = None


async def get_alert_recipients(
    session: AsyncSession, organization_id: uuid.UUID | None
) -> list[AlertRecipient]:
    """Live, non-suspended users holding ``site_alerts:receive`` through a role
    (in ``organization_id`` when given, else in any organization), plus every
    super admin."""
    holders = (
        select(UserRole.user_id)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            Permission.code == PERM_SITE_ALERTS_RECEIVE,
            Permission.deleted_time.is_(None),
            RolePermission.deleted_time.is_(None),
            UserRole.deleted_time.is_(None),
        )
    )
    if organization_id is not None:
        holders = holders.where(UserRole.organization_id == organization_id)
    condition: ColumnElement[bool] = User.id.in_(holders)
    if organization_id is not None:
        condition = and_(User.organization_id == organization_id, condition)
    rows = (
        (
            await session.execute(
                select(User)
                .where(
                    User.deleted_time.is_(None),
                    User.suspension_status == SuspensionStatus.ACTIVE,
                    (condition) | (User.is_admin.is_(True)),
                )
                .order_by(User.email)
            )
        )
        .scalars()
        .all()
    )
    return [
        AlertRecipient(
            user_id=user.id,
            organization_id=user.organization_id,
            name=" ".join(part for part in (user.first_name, user.last_name) if part)
            or "Operator",
        )
        for user in rows
    ]


async def _warn_if_template_missing(
    session: AsyncSession, alert: Alert, recipient: AlertRecipient
) -> None:
    try:
        from src.crud.notification_template import get_template_by_code

        template = await get_template_by_code(
            session, str(recipient.organization_id), alert.template_code, "email"
        )
        if template is None:
            logger.warning(
                f"Freespace alert: template '{alert.template_code}' is not seeded; "
                "sending the plain-text fallback"
            )
    except Exception as exc:
        logger.warning(f"Freespace alert: template lookup failed: {type(exc).__name__}")


async def send_alert(session: AsyncSession, alert: Alert) -> int:
    """Email ``alert`` to every recipient; returns how many sends succeeded.
    Never raises."""
    try:
        recipients = await get_alert_recipients(session, alert.organization_id)
    except Exception as exc:
        logger.error(
            f"Freespace alert: cannot resolve recipients: {type(exc).__name__}"
        )
        return 0
    if not recipients:
        logger.warning(
            f"Freespace alert '{alert.template_code}': no recipient holds "
            f"{PERM_SITE_ALERTS_RECEIVE}"
        )
        return 0
    await _warn_if_template_missing(session, alert, recipients[0])
    sent = 0
    for recipient in recipients:
        try:
            result = await notification_dispatcher.send_to_user(
                session=session,
                user_id=str(recipient.user_id),
                organization_id=str(recipient.organization_id),
                channel="email",
                content=alert.content,
                category_code=ALERT_CATEGORY,
                is_urgent=True,
                template_code=alert.template_code,
                template_vars={**alert.variables, "user_name": recipient.name},
                subject=alert.subject,
            )
            if result is not None:
                sent += 1
        except Exception as exc:
            logger.error(
                f"Freespace alert '{alert.template_code}': send failed: "
                f"{type(exc).__name__}"
            )
    return sent


def _iso(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────
# 1. Site silent / recovered
# ─────────────────────────────────────────────────────────────

SILENT_KEY: Final = "silent_alerted_at"


async def _set_ops_state(
    session: AsyncSession, site_id: uuid.UUID, state: dict[str, Any]
) -> None:
    await session.execute(
        update(SiteEngineState)
        .where(SiteEngineState.site_id == site_id)
        .values(ops_alert_state=state)
    )
    await session.commit()


async def check_site_silence(session: AsyncSession, now: datetime) -> int:
    """Fire the silent / recovered alerts; returns the number of alerts fired.

    A site that was never heard from counts its silence from its creation.
    The state is saved after the alert is attempted, so a delivery problem
    cannot turn into one email a minute.
    """
    rows = (
        await session.execute(
            select(
                Site.id,
                Site.organization_id,
                Site.name,
                Site.managed,
                Site.created_time,
                SiteSnapshot.received_at,
                SiteEngineState.ops_alert_state,
            )
            .join(SiteEngineState, SiteEngineState.site_id == Site.id)
            .outerjoin(SiteSnapshot, SiteSnapshot.site_id == Site.id)
            .where(Site.deleted_time.is_(None))
            .order_by(Site.id)
        )
    ).all()
    fired = 0
    for site_id, org_id, name, managed, created, received, ops_state in rows:
        state = dict(ops_state or {})
        alerted_at = state.get(SILENT_KEY)
        if not managed:
            if alerted_at:  # shadow mode: no alert, forget the old one
                state[SILENT_KEY] = None
                await _set_ops_state(session, site_id, state)
            continue
        reference = received or created
        if reference is None:
            continue
        reference = ensure_utc(reference)
        silent_for = (now - reference).total_seconds()
        silent = silent_for >= SILENCE_THRESHOLD_S
        if silent and not alerted_at:
            minutes = int(silent_for // 60)
            alert = Alert(
                template_code=TEMPLATE_SITE_SILENT,
                subject=f"Freespace: no data from {name}",
                content=(
                    f"Site {name} has sent no accepted occupancy update for "
                    f"{minutes} minutes (last accepted: {_iso(reference)}). "
                    "Advisories for this site use stale data until it recovers."
                ),
                variables={
                    "site_name": name,
                    "silent_minutes": str(minutes),
                    "last_ingest_at": _iso(reference),
                },
                organization_id=org_id,
            )
            await send_alert(session, alert)
            state[SILENT_KEY] = _iso(now)
            await _set_ops_state(session, site_id, state)
            fired += 1
        elif not silent and alerted_at:
            alert = Alert(
                template_code=TEMPLATE_SITE_RECOVERED,
                subject=f"Freespace: {name} is sending data again",
                content=(
                    f"Site {name} is sending occupancy updates again "
                    f"(last accepted: {_iso(reference)})."
                ),
                variables={"site_name": name, "last_ingest_at": _iso(reference)},
                organization_id=org_id,
            )
            await send_alert(session, alert)
            state[SILENT_KEY] = None
            await _set_ops_state(session, site_id, state)
            fired += 1
    return fired


# ─────────────────────────────────────────────────────────────
# 2. FCM credential failure, 3. device ceiling
# ─────────────────────────────────────────────────────────────


async def check_fcm_failure(session: AsyncSession, now: datetime) -> int:
    redis = get_redis()
    if redis is None:
        return 0
    raw = await redis.get(_fcm_failure_key())
    if raw is None:
        return 0
    # Consume the record; a repeat failure writes it again.
    await redis.delete(_fcm_failure_key())
    if not await redis.set(
        REDIS_FCM_COOLDOWN_KEY, "1", nx=True, ex=FCM_ALERT_COOLDOWN_S
    ):
        return 0  # already alerted within the cooldown
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {}
    http_status = payload.get("httpStatus")
    occurred = str(payload.get("occurredAt") or _iso(now))
    alert = Alert(
        template_code=TEMPLATE_FCM_FAILURE,
        subject="Freespace: push credentials rejected by FCM",
        content=(
            "Firebase Cloud Messaging rejected the server credentials"
            + (f" (HTTP {http_status})" if http_status else "")
            + f" at {occurred}. Advisory fan-out is stopped until the credentials "
            "are fixed. Check the service account file and project id."
        ),
        variables={
            "occurred_at": occurred,
            "http_status": str(http_status) if http_status else "none",
        },
    )
    await send_alert(session, alert)
    return 1


async def check_device_ceiling(session: AsyncSession, now: datetime) -> int:
    redis = get_redis()
    if redis is None:
        return 0
    raw = await redis.get(DEVICE_CEILING_ALERT_KEY)
    if raw is None:
        return 0
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {}
    raised_at = str(payload.get("raised_at") or "")
    marker = await redis.get(REDIS_CEILING_MARKER_KEY)
    if isinstance(marker, bytes):
        marker = marker.decode()
    if marker is not None and marker == raised_at:
        return 0
    await redis.set(REDIS_CEILING_MARKER_KEY, raised_at, ex=CEILING_MARKER_TTL_S)
    registered = payload.get("registered", "")
    ceiling = payload.get("ceiling", "")
    alert = Alert(
        template_code=TEMPLATE_DEVICE_CEILING,
        subject="Freespace: device registration ceiling reached",
        content=(
            f"The deployment holds {registered} registered devices, which is the "
            f"configured ceiling ({ceiling}). New registrations are refused with "
            "503 until devices are purged or the ceiling is raised."
        ),
        variables={"registered": str(registered), "ceiling": str(ceiling)},
    )
    await send_alert(session, alert)
    return 1


# ─────────────────────────────────────────────────────────────
# 4. Ingest rejection rate
# ─────────────────────────────────────────────────────────────


async def record_ingest_rejection(
    key_id: uuid.UUID | str | None, now: datetime
) -> None:
    """Count a rejected ingest request that writes no ``site_event`` (429 rate
    limited, unknown-key 401). ``key_id`` is the ingest key id when the key is
    known, else None. Fails open; stores no key material, only a timestamp."""
    redis = get_redis()
    if redis is None:
        return
    subject = str(key_id) if key_id is not None else UNKNOWN_KEY_ID
    key = REDIS_REJECTION_KEY_PREFIX + subject
    ts = ensure_utc(now).timestamp()
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {f"{ts}:{uuid.uuid4().hex}": ts})
            # Trim on write: drop entries outside the alert window, then keep
            # only the newest REJECTION_COUNTER_MAX_ENTRIES.
            pipe.zremrangebyscore(key, "-inf", ts - REJECTION_WINDOW_S)
            pipe.zremrangebyrank(key, 0, -(REJECTION_COUNTER_MAX_ENTRIES + 1))
            pipe.expire(key, REJECTION_COUNTER_TTL_S)
            await pipe.execute()
    except Exception as exc:
        logger.warning(
            f"Freespace: cannot count ingest rejection: {type(exc).__name__}"
        )


async def _event_rejections_by_site(
    session: AsyncSession, now: datetime
) -> dict[uuid.UUID, float]:
    """Rejections per site in the last minute from collapsed ``INGEST_REJECTED``
    rows. A row collapsed over a longer span contributes its average rate."""
    start = now.timestamp() - REJECTION_WINDOW_S
    rows = (
        await session.execute(
            select(
                SiteEvent.site_id,
                SiteEvent.occurred_at,
                SiteEvent.last_seen_at,
                SiteEvent.repeat_count,
            ).where(
                SiteEvent.type == EventType.INGEST_REJECTED.value,
                SiteEvent.last_seen_at >= datetime.fromtimestamp(start, now.tzinfo),
            )
        )
    ).all()
    totals: dict[uuid.UUID, float] = {}
    for site_id, occurred, last_seen, repeat in rows:
        first = ensure_utc(occurred).timestamp()
        last = ensure_utc(last_seen).timestamp()
        count = float(repeat or 1)
        if first < start:
            span = max(last - first, float(REJECTION_WINDOW_S))
            count = count * REJECTION_WINDOW_S / span
        totals[site_id] = totals.get(site_id, 0.0) + count
    return totals


async def _counter_rejections(now: datetime) -> dict[str, int]:
    """Redis counters per key id (or ``unknown``) over the last minute."""
    redis = get_redis()
    if redis is None:
        return {}
    ts = ensure_utc(now).timestamp()
    out: dict[str, int] = {}
    try:
        async for raw_key in redis.scan_iter(match=REDIS_REJECTION_KEY_PREFIX + "*"):
            key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            await redis.zremrangebyscore(key, "-inf", ts - REJECTION_WINDOW_S)
            count = await redis.zcard(key)
            if count:
                out[key[len(REDIS_REJECTION_KEY_PREFIX) :]] = int(count)
    except Exception as exc:
        logger.warning(
            f"Freespace: cannot read rejection counters: {type(exc).__name__}"
        )
    return out


async def check_ingest_rejections(session: AsyncSession, now: datetime) -> int:
    redis = get_redis()
    if redis is None:
        return 0
    per_site: dict[str, float] = {
        str(site_id): count
        for site_id, count in (await _event_rejections_by_site(session, now)).items()
    }
    by_key = await _counter_rejections(now)
    real_key_ids = []
    for key_id in by_key:
        try:
            real_key_ids.append(uuid.UUID(key_id))
        except ValueError:
            continue
    key_to_site: dict[str, uuid.UUID] = {}
    if real_key_ids:
        for key_id, site_id in (
            await session.execute(
                select(IngestKey.id, IngestKey.site_id).where(
                    IngestKey.id.in_(real_key_ids)
                )
            )
        ).all():
            key_to_site[str(key_id)] = site_id
    for key_id, count in by_key.items():
        subject = str(key_to_site[key_id]) if key_id in key_to_site else UNKNOWN_KEY_ID
        per_site[subject] = per_site.get(subject, 0.0) + count

    names: dict[str, tuple[str, uuid.UUID]] = {}
    site_ids = []
    for subject in per_site:
        try:
            site_ids.append(uuid.UUID(subject))
        except ValueError:
            continue
    if site_ids:
        for site_id, name, org_id in (
            await session.execute(
                select(Site.id, Site.name, Site.organization_id).where(
                    Site.id.in_(site_ids)
                )
            )
        ).all():
            names[str(site_id)] = (name, org_id)

    fired = 0
    for subject, rate in per_site.items():
        if rate <= REJECTION_THRESHOLD_PER_MIN:
            continue
        episode_key = REDIS_REJECTION_EPISODE_FMT.format(subject=subject)
        is_new = await redis.set(episode_key, "1", nx=True, ex=REJECTION_EPISODE_TTL_S)
        if not is_new:
            await redis.expire(episode_key, REJECTION_EPISODE_TTL_S)
            continue
        site_name, org_id = names.get(subject, ("an unrecognised ingest key", None))
        alert = Alert(
            template_code=TEMPLATE_INGEST_REJECTIONS,
            subject="Freespace: ingest requests are being rejected",
            content=(
                f"More than {REJECTION_THRESHOLD_PER_MIN} ingest requests a minute "
                f"are being rejected for {site_name} (about {int(rate)} in the last "
                "minute). Check the ParkIT publisher configuration, clock and key."
            ),
            variables={
                "site_name": site_name,
                "rejections_per_minute": str(int(rate)),
                "threshold": str(REJECTION_THRESHOLD_PER_MIN),
            },
            organization_id=org_id,
        )
        await send_alert(session, alert)
        fired += 1
    return fired


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────


async def run_alert_checks(session: AsyncSession, clock: Clock) -> dict[str, int]:
    """Run all four alert checks once. Safe to call every minute; never raises.

    Returns the number of alerts fired per check (for logging and tests).
    """
    now = ensure_utc(clock.now())
    result: dict[str, int] = {}
    for name, check in (
        ("site_silence", check_site_silence),
        ("fcm_failure", check_fcm_failure),
        ("device_ceiling", check_device_ceiling),
        ("ingest_rejections", check_ingest_rejections),
    ):
        try:
            result[name] = await check(session, now)
        except Exception as exc:
            try:
                await session.rollback()
            except Exception:
                pass
            result[name] = 0
            logger.error(f"Freespace alert check '{name}' failed: {type(exc).__name__}")
    return result
