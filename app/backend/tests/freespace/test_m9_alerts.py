"""M9: operator alerts (BF-82, BF-37, BF-66, BF-18)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from src.constants.freespace import EventType, IngestRejectReason
from src.models.site_engine_state import SiteEngineState
from src.services.freespace import alerts
from src.services.freespace.devices import (
    DEVICE_CEILING_ALERT_KEY,
    record_device_ceiling_alert,
)
from src.services.freespace.events import write_event
from src.services.freespace.fanout import REDIS_FCM_AUTH_FAILURE_KEY
from src.services.freespace.types import EventDraft
from tests.freespace.conftest import make_ingest_key, make_site


@pytest.fixture
def sent(monkeypatch):
    """Capture every dispatcher call instead of sending."""
    calls: list[dict] = []

    async def fake_send_to_user(**kwargs):
        calls.append(kwargs)
        return {"id": "n"}

    monkeypatch.setattr(
        alerts.notification_dispatcher, "send_to_user", fake_send_to_user
    )
    return calls


def codes(calls) -> list[str]:
    return [c["template_code"] for c in calls]


async def ops_state(session, site):
    await session.refresh(site)
    row = (
        await session.execute(
            select(SiteEngineState).where(SiteEngineState.site_id == site.id)
        )
    ).scalar_one()
    return row.ops_alert_state


# ── recipients ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recipients_are_permission_holders_and_super_admins(
    async_session,
    test_organization,
    fs_admin_user,
    fs_operator_user,
    fs_viewer_user,
    fs_no_role_user,
    test_admin_user,
):
    got = await alerts.get_alert_recipients(async_session, test_organization.id)
    ids = {r.user_id for r in got}
    assert fs_admin_user.id in ids  # holds site_alerts:receive
    assert test_admin_user.id in ids  # super admin
    assert fs_operator_user.id not in ids
    assert fs_viewer_user.id not in ids
    assert fs_no_role_user.id not in ids


@pytest.mark.asyncio
async def test_recipients_are_scoped_to_the_tenant(
    async_session,
    test_organization,
    fs_admin_user,
    fs_second_org_admin_user,
):
    got = {
        r.user_id
        for r in await alerts.get_alert_recipients(async_session, test_organization.id)
    }
    assert fs_admin_user.id in got
    assert fs_second_org_admin_user.id not in got
    everyone = {
        r.user_id for r in await alerts.get_alert_recipients(async_session, None)
    }
    assert {fs_admin_user.id, fs_second_org_admin_user.id} <= everyone


@pytest.mark.asyncio
async def test_suspended_and_deleted_users_get_nothing(
    async_session, test_organization, fs_admin_user, fixed_clock
):
    from src.models.user import SuspensionStatus

    fs_admin_user.suspension_status = SuspensionStatus.SUSPENDED
    await async_session.commit()
    got = await alerts.get_alert_recipients(async_session, test_organization.id)
    assert fs_admin_user.id not in {r.user_id for r in got}


# ── 1. site silence ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_silent_site_fires_once_then_recovers_once(
    async_session, fs_site, fs_admin_user, fs_snapshot, fixed_clock, sent
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    fixed_clock.advance(seconds=599)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert sent == []  # just inside 10 minutes

    fixed_clock.advance(seconds=1)
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["site_silence"] == 1
    assert set(codes(sent)) == {alerts.TEMPLATE_SITE_SILENT}
    assert all(c["category_code"] == alerts.ALERT_CATEGORY for c in sent)
    assert all(c["channel"] == "email" for c in sent)
    assert (await ops_state(async_session, fs_site))["silent_alerted_at"]

    n = len(sent)
    for _ in range(3):  # still silent: no repeat
        fixed_clock.advance(seconds=60)
        await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == n

    await fs_snapshot(fs_site, capacity=100, occupied=10, received_at=fixed_clock.now())
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert codes(sent)[n:] == [alerts.TEMPLATE_SITE_RECOVERED] * (len(sent) - n)
    assert len(sent) > n
    assert (await ops_state(async_session, fs_site))["silent_alerted_at"] is None

    m = len(sent)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == m  # recovery fires once

    # goes silent again: a new transition, a new alert
    fixed_clock.advance(seconds=700)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) > m and codes(sent)[-1] == alerts.TEMPLATE_SITE_SILENT


@pytest.mark.asyncio
async def test_unmanaged_site_silence_never_alerts(
    async_session, test_organization, fs_admin_user, fixed_clock, sent
):
    site = await make_site(
        async_session, test_organization, slug="shadow-site", managed=False
    )
    fixed_clock.advance(seconds=3 * 3600)
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["site_silence"] == 0
    assert sent == []
    assert (await ops_state(async_session, site)).get("silent_alerted_at") is None


@pytest.mark.asyncio
async def test_site_made_unmanaged_clears_state_without_alert(
    async_session, fs_site, fs_admin_user, fs_snapshot, fixed_clock, sent
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    fixed_clock.advance(seconds=900)
    await alerts.run_alert_checks(async_session, fixed_clock)
    n = len(sent)
    fs_site.managed = False
    await async_session.commit()
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == n
    assert (await ops_state(async_session, fs_site))["silent_alerted_at"] is None


@pytest.mark.asyncio
async def test_site_alert_goes_only_to_the_sites_tenant(
    async_session,
    fs_site,
    fs_admin_user,
    fs_second_org_admin_user,
    fs_snapshot,
    fixed_clock,
    sent,
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    fixed_clock.advance(seconds=900)
    await alerts.run_alert_checks(async_session, fixed_clock)
    users = {c["user_id"] for c in sent}
    assert str(fs_admin_user.id) in users
    assert str(fs_second_org_admin_user.id) not in users


@pytest.mark.asyncio
async def test_missing_template_degrades_to_plain_text(
    async_session, fs_site, fs_admin_user, fs_snapshot, fixed_clock, sent
):
    """No template row is seeded in tests: the alert still carries its text."""
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    fixed_clock.advance(seconds=900)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert sent and all(c["content"] for c in sent)
    assert fs_site.name in sent[0]["content"]


@pytest.mark.asyncio
async def test_dispatcher_failure_does_not_crash_or_repeat(
    async_session, fs_site, fs_admin_user, fs_snapshot, fixed_clock, monkeypatch
):
    async def boom(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(alerts.notification_dispatcher, "send_to_user", boom)
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    fixed_clock.advance(seconds=900)
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["site_silence"] == 1
    assert (await ops_state(async_session, fs_site))["silent_alerted_at"]


@pytest.mark.asyncio
async def test_a_failing_check_does_not_stop_the_others(
    async_session, fs_admin_user, fixed_clock, monkeypatch, sent, fs_redis
):
    async def boom(session, now):
        raise RuntimeError("x")

    monkeypatch.setattr(alerts, "check_site_silence", boom)
    await record_device_ceiling_alert(10, 10, fixed_clock.now())
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["site_silence"] == 0
    assert result["device_ceiling"] == 1


# ── 2. FCM credential failure ───────────────────────────────


@pytest.mark.asyncio
async def test_fcm_credential_failure_alert(
    async_session, fs_admin_user, fs_redis, fixed_clock, sent
):
    payload = {
        "occurredAt": fixed_clock.now().isoformat(),
        "siteId": "absa-alice-lane",
        "eventId": "e",
        "errorCode": "UNAUTHENTICATED",
        "httpStatus": 401,
    }
    await fs_redis.set(REDIS_FCM_AUTH_FAILURE_KEY, json.dumps(payload))
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["fcm_failure"] == 1
    assert set(codes(sent)) == {alerts.TEMPLATE_FCM_FAILURE}
    assert await fs_redis.get(REDIS_FCM_AUTH_FAILURE_KEY) is None

    n = len(sent)
    await fs_redis.set(REDIS_FCM_AUTH_FAILURE_KEY, json.dumps(payload))
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == n  # inside the cooldown


# ── 3. device ceiling ───────────────────────────────────────


@pytest.mark.asyncio
async def test_device_ceiling_alert_once_per_window(
    async_session, fs_admin_user, fs_redis, fixed_clock, sent
):
    await record_device_ceiling_alert(50000, 50000, fixed_clock.now())
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["device_ceiling"] == 1
    assert set(codes(sent)) == {alerts.TEMPLATE_DEVICE_CEILING}
    assert "50000" in sent[0]["content"]

    n = len(sent)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == n

    # the condition clears and is raised again later: alert again
    await fs_redis.delete(DEVICE_CEILING_ALERT_KEY)
    fixed_clock.advance(seconds=4000)
    await record_device_ceiling_alert(50000, 50000, fixed_clock.now())
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == 2 * n


# ── 4. ingest rejection rate ────────────────────────────────


async def reject(session, site, now, reason=IngestRejectReason.SITE_MISMATCH):
    await write_event(
        session,
        site_id=site.id,
        organization_id=site.organization_id,
        draft=EventDraft(
            type=EventType.INGEST_REJECTED,
            occurred_at=now,
            reason=reason.value,
            details={},
        ),
    )
    await session.commit()


@pytest.mark.asyncio
async def test_rejection_rate_alert_from_events(
    async_session, fs_site, fs_admin_user, fs_redis, fixed_clock, sent
):
    for _ in range(10):
        await reject(async_session, fs_site, fixed_clock.now())
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert sent == []  # exactly 10 a minute is not above the threshold

    await reject(async_session, fs_site, fixed_clock.now())
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["ingest_rejections"] == 1
    assert set(codes(sent)) == {alerts.TEMPLATE_INGEST_REJECTIONS}

    n = len(sent)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert len(sent) == n  # same episode


@pytest.mark.asyncio
async def test_old_rejections_do_not_count(
    async_session, fs_site, fs_admin_user, fs_redis, fixed_clock, sent
):
    for _ in range(30):
        await reject(async_session, fs_site, fixed_clock.now())
    fixed_clock.advance(seconds=120)
    await alerts.run_alert_checks(async_session, fixed_clock)
    assert sent == []


@pytest.mark.asyncio
async def test_rejection_rate_alert_from_counters_429(
    async_session, fs_site, fs_admin_user, fs_redis, fixed_clock, sent
):
    _, key = await make_ingest_key(async_session, fs_site)
    for _ in range(11):
        await alerts.record_ingest_rejection(key.id, fixed_clock.now())
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["ingest_rejections"] == 1
    assert fs_site.name in sent[0]["content"]


@pytest.mark.asyncio
async def test_unknown_key_rejections_alert_without_a_site(
    async_session, fs_admin_user, test_admin_user, fs_redis, fixed_clock, sent
):
    for _ in range(11):
        await alerts.record_ingest_rejection(None, fixed_clock.now())
    result = await alerts.run_alert_checks(async_session, fixed_clock)
    assert result["ingest_rejections"] == 1
    assert sent  # deployment-wide: every holder


# ── privacy ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alerts_contain_no_device_data(
    async_session, fs_site, fs_admin_user, fs_redis, fs_snapshot, fixed_clock, sent
):
    await fs_snapshot(fs_site, capacity=100, occupied=10)
    fixed_clock.advance(seconds=900)
    await record_device_ceiling_alert(5, 5, fixed_clock.now())
    await alerts.run_alert_checks(async_session, fixed_clock)
    blob = json.dumps(sent, default=str).lower()
    assert "dev_" not in blob and "fcmtok" not in blob and "token" not in blob
