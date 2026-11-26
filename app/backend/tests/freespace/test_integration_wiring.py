"""Integration wiring: cron/seed registration, alert hooks, /health, fan-out
without FCM credentials, mock tick isolation, event collapse tie-break,
public rate-limit shape and log privacy in ``main.py``."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest
import yaml

from src.api.freespace_deps import IngestAuth
from src.constants.freespace import (
    REDIS_ENGINE_TICK_KEY,
    SITE_SETTING_BOUNDS,
    AdvisoryType,
    EventType,
    FanoutStatus,
    FcmErrorReason,
    SuppressionReason,
)
from src.database import get_async_session
from src.models.site_event import SiteEvent
from src.services.freespace import alerts, health
from src.services.freespace.events import write_event
from src.services.freespace.ingest_rate_limit import enforce_ingest_rate_limit
from src.services.freespace.types import EventDraft
from tests.freespace.test_m7_support import (
    make_advisory_event,
    reload_event,
    session_factory_for,
)


SEED_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_data"
DEVICE_ID = "Zx9_secretDeviceId-AbC"  # 22 chars, base64url


def _yaml(name: str):
    return yaml.safe_load((SEED_DIR / name).read_text())


# ─────────────────────────────────────────────────────────────
# 1-4: cron, category, templates
# ─────────────────────────────────────────────────────────────


def test_cron_handlers_registered():
    from src.services.cron.freespace_purge import (
        cleanup_old_request_logs_configured_handler,
        freespace_daily_purge_handler,
    )
    from src.services.cron_scheduler import get_all_cron_handlers

    handlers = get_all_cron_handlers()
    assert handlers["freespace_daily_purge"] is freespace_daily_purge_handler
    assert (
        handlers["cleanup_old_request_logs"]
        is cleanup_old_request_logs_configured_handler
    )
    codes = {job["code"] for job in _yaml("cron_jobs.yaml")}
    assert codes <= set(handlers)


def test_purge_cron_job_seeded():
    job = next(
        j for j in _yaml("cron_jobs.yaml") if j["code"] == "freespace_daily_purge"
    )
    assert job["name"] == "Freespace Daily Purge"
    assert job["schedule_expression"] == "30 3 * * *"
    assert job["is_active"] and job["is_enabled_by_default_for_new_orgs"]
    assert job["parameters"] == {} and "BF-73" in job["description"]


def test_site_operations_category():
    from src.services.organization_seeding import DEFAULT_NOTIFICATION_CATEGORIES

    cat = next(
        c for c in DEFAULT_NOTIFICATION_CATEGORIES if c["code"] == alerts.ALERT_CATEGORY
    )
    assert cat["name"] == "Site Operations Alerts"
    assert cat["default_enabled"] is True and cat["user_configurable"] is False
    assert cat["display_order"] == 50


EXPECTED_ALERT_VARS = {
    alerts.TEMPLATE_SITE_SILENT: {"site_name", "silent_minutes", "last_ingest_at"},
    alerts.TEMPLATE_SITE_RECOVERED: {"site_name", "last_ingest_at"},
    alerts.TEMPLATE_FCM_FAILURE: {"occurred_at", "http_status"},
    alerts.TEMPLATE_DEVICE_CEILING: {"registered", "ceiling"},
    alerts.TEMPLATE_INGEST_REJECTIONS: {
        "site_name",
        "rejections_per_minute",
        "threshold",
    },
}


def test_alert_templates_match_the_code():
    templates = {
        t["code"]: t
        for t in _yaml("notification_templates.yaml")
        if t["code"].startswith("freespace_")
    }
    assert set(templates) == set(alerts.ALERT_TEMPLATE_CODES)
    for code, template in templates.items():
        assert template["channel"] == "email" and template["is_active"] is True
        assert "body_html" not in template
        declared = set(template["variables"])
        assert declared == EXPECTED_ALERT_VARS[code] | {"user_name"}, code
        used = set(
            re.findall(r"\{(\w+)\}", template["subject"] + template["body_text"])
        )
        assert used <= declared and EXPECTED_ALERT_VARS[code] <= used, code
        assert template["body_text"].startswith("Hello {user_name},")


async def test_reference_seeders_are_idempotent(async_session):
    from src.services.organization_seeding import (
        seed_reference_cron_jobs,
        seed_reference_notification_categories,
        seed_reference_notification_templates,
    )

    for seeder in (
        seed_reference_notification_categories,
        seed_reference_notification_templates,
        seed_reference_cron_jobs,
    ):
        await seeder(async_session)
        second = await seeder(async_session)
        assert second.created == 0, seeder.__name__


# ─────────────────────────────────────────────────────────────
# 5: alert checks from the tick
# ─────────────────────────────────────────────────────────────


async def test_tick_runs_alert_checks_and_survives_their_failure(
    async_session, fs_site, fixed_clock, fs_redis, monkeypatch
):
    from src.services.freespace.evaluator import run_engine_tick

    calls = []

    async def fake_checks(session, clock):
        calls.append(clock.now())
        return {}

    monkeypatch.setattr(alerts, "run_alert_checks", fake_checks)
    result = await run_engine_tick(session_factory_for(async_session), fixed_clock)
    assert calls == [fixed_clock.now()] and result.sites_evaluated >= 1
    assert await fs_redis.get(REDIS_ENGINE_TICK_KEY) is not None

    async def broken(session, clock):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(alerts, "run_alert_checks", broken)
    result = await run_engine_tick(session_factory_for(async_session), fixed_clock)
    assert result.sites_evaluated >= 1
    assert any(e.startswith("alerts:") for e in result.errors)


# ─────────────────────────────────────────────────────────────
# 6: ingest rejections that write no event
# ─────────────────────────────────────────────────────────────


async def _counter(fs_redis, subject: str) -> int:
    return int(await fs_redis.zcard(alerts.REDIS_REJECTION_KEY_PREFIX + subject))


async def test_unknown_key_401_is_counted(client, fs_redis):
    bad = {"Authorization": "Bearer fsk_" + "A" * 43}
    assert (await client.get("/v1/ingest/ping", headers=bad)).status_code == 401
    assert (await client.get("/v1/ingest/ping")).status_code == 401
    assert await _counter(fs_redis, alerts.UNKNOWN_KEY_ID) == 2


async def test_rate_limited_429_is_counted(async_session, fs_ingest_key, fs_redis):
    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def _flatten(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code, content={}, headers=exc.headers
        )

    @app.get("/ingest")
    async def ingest(auth: Annotated[IngestAuth, Depends(enforce_ingest_rate_limit)]):
        return {}

    async def _session():
        yield async_session

    app.dependency_overrides[get_async_session] = _session
    headers = {"Authorization": f"Bearer {fs_ingest_key[0]}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        codes = [
            (await c.get("/ingest", headers=headers)).status_code for _ in range(13)
        ]
    assert codes[-1] == 429
    assert await _counter(fs_redis, str(fs_ingest_key[1].id)) == 1


# ─────────────────────────────────────────────────────────────
# 7: /health and /health/live
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def health_factory(async_session, monkeypatch):
    import src.database

    class _Ctx:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(src.database, "AsyncSessionLocal", lambda: _Ctx())
    health.reset_health_state()
    yield
    health.reset_health_state()


async def test_health_reports_engine_tick(
    client, health_factory, fixed_clock, fs_redis
):
    await fs_redis.set(REDIS_ENGINE_TICK_KEY, fixed_clock.now().isoformat())
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "healthy" and body["engine"]["status"] == "ok"

    old = fixed_clock.now() - timedelta(seconds=health.TICK_STALE_AFTER_S + 60)
    await fs_redis.set(REDIS_ENGINE_TICK_KEY, old.isoformat())
    response = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["engine"]["status"] == "stale"
    assert response.headers["cache-control"] == "no-store"


async def test_health_live_is_constant(client, fixed_clock, fs_redis):
    old = fixed_clock.now() - timedelta(hours=1)
    await fs_redis.set(REDIS_ENGINE_TICK_KEY, old.isoformat())
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert response.headers["cache-control"] == "no-store"


def test_health_routes_exempt_from_global_limit():
    from src.core.rate_limit import limiter

    assert {"main.health_check", "main.health_live"} <= limiter._exempt_routes


def test_live_probe_excluded_from_request_logging():
    from src.core.config import Settings

    paths = Settings.model_fields["REQUEST_LOGGING_EXCLUDED_PATHS"].default
    assert "/health/live" in paths.split(",")


def test_probes_use_the_liveness_url():
    root = Path(__file__).resolve().parents[2]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "Dockerfile"):
        text = (root / name).read_text()
        assert "8000/health/live" in text, name
        assert not re.search(r"8000/health[\"' ]", text), name
    assert "8000/health/live" in (root / "deploy" / "deploy.sh").read_text()


# ─────────────────────────────────────────────────────────────
# 10: one source of truth for the stale limit
# ─────────────────────────────────────────────────────────────


def test_stale_limit_minimum_is_120():
    from src.services.freespace.site_config import STALE_LIMIT_MIN_S

    assert SITE_SETTING_BOUNDS["stale_limit_s"][0] == 120 == STALE_LIMIT_MIN_S


# ─────────────────────────────────────────────────────────────
# 11: fan-out without FCM credentials
# ─────────────────────────────────────────────────────────────


async def test_fanout_without_fcm_credentials_fails_and_releases_engine(
    async_session, fs_site, fixed_clock, fs_redis, monkeypatch
):
    from src.core.config import settings
    from src.services.freespace import fcm
    from src.services.freespace.fanout import REDIS_FCM_AUTH_FAILURE_KEY
    from src.services.freespace.loaders import load_engine_state_row
    from src.workers.freespace_tasks import fanout_advisory_task

    fcm.set_fcm_client_override(None)
    monkeypatch.setattr(fcm, "_default_client", None)
    monkeypatch.setattr(settings, "FREESPACE_FCM_CREDENTIALS_PATH", "")
    with pytest.raises(RuntimeError):
        fcm.get_fcm_client()

    event = await make_advisory_event(async_session, fs_site, now=fixed_clock.now())
    result = await fanout_advisory_task(
        {"session_factory": session_factory_for(async_session)}, str(event.id)
    )
    assert result["status"] == FanoutStatus.FAILED.value and not result["reenqueued"]

    row = await reload_event(async_session, event.id)
    assert row.fanout_status == FanoutStatus.FAILED.value
    errors = (
        (await async_session.execute(select_fcm_errors(fs_site.id))).scalars().all()
    )
    assert [e.reason for e in errors] == [FcmErrorReason.CREDENTIALS_MISSING.value]
    state = await load_engine_state_row(async_session, fs_site.id)
    await async_session.refresh(state)
    assert state.inflight_event_id is None
    assert await fs_redis.get(REDIS_FCM_AUTH_FAILURE_KEY) is not None

    # A second delivery of the same job (ARQ retry, tick recovery) is a no-op.
    again = await fanout_advisory_task(
        {"session_factory": session_factory_for(async_session)}, str(event.id)
    )
    assert again["status"] == FanoutStatus.FAILED.value
    assert len((await async_session.execute(select_fcm_errors(fs_site.id))).all()) == 1

    # The FCM alert consumes the record.
    sent = []

    async def fake_send(session, alert):
        sent.append(alert)
        return 1

    monkeypatch.setattr(alerts, "send_alert", fake_send)
    assert await alerts.check_fcm_failure(async_session, fixed_clock.now()) == 1
    assert sent[0].variables["http_status"] == "none"


def select_fcm_errors(site_id):
    from sqlalchemy import select

    return select(SiteEvent).where(
        SiteEvent.site_id == site_id, SiteEvent.type == EventType.FCM_ERROR.value
    )


# ─────────────────────────────────────────────────────────────
# 12: mock tick over the request session
# ─────────────────────────────────────────────────────────────


async def test_mock_tick_rolls_back_a_failed_site(
    async_session, fs_site, fixed_clock, monkeypatch
):
    from src.api.freespace_public import mock
    from src.services.freespace import evaluator

    original_name = fs_site.name

    async def failing(session, site_id, clock):
        fs_site.name = "half-done evaluation"
        await session.flush()
        raise RuntimeError("boom")

    monkeypatch.setattr(evaluator, "evaluate_site", failing)
    summary = await mock._run_tick(async_session, fixed_clock)
    assert summary.ran and summary.sites_failed >= 1
    await async_session.refresh(fs_site)
    assert fs_site.name == original_name


# ─────────────────────────────────────────────────────────────
# 13: collapse tie-break for events of one evaluation
# ─────────────────────────────────────────────────────────────


def _cand(at):
    return EventDraft(
        type=EventType.CANDIDATE,
        occurred_at=at,
        reason=SuppressionReason.STALE_DATA,
        advisory_type=AdvisoryType.SITE_CHANGE,
        fingerprint="f1",
    )


async def _write(session, site, draft):
    return await write_event(
        session, site_id=site.id, organization_id=site.organization_id, draft=draft
    )


async def test_candidate_after_same_evaluation_state_event_collapses(
    async_session, fs_site, fixed_clock
):
    t0 = fixed_clock.now()
    first = await _write(async_session, fs_site, _cand(t0))
    t1 = t0 + timedelta(minutes=1)
    # One evaluation at t1: DATA_STALE first, then the identical candidate,
    # which must NOT collapse into the t0 one (a state event lies between).
    await _write(
        async_session, fs_site, EventDraft(type=EventType.DATA_STALE, occurred_at=t1)
    )
    second = await _write(async_session, fs_site, _cand(t1))
    assert second.id != first.id
    await async_session.commit()
    # Next evaluation: the identical candidate collapses into the t1 one,
    # whatever order the database returns the tied t1 rows in.
    third = await _write(async_session, fs_site, _cand(t1 + timedelta(minutes=1)))
    assert third.id == second.id and third.repeat_count == 2


# ─────────────────────────────────────────────────────────────
# 14: template limits
# ─────────────────────────────────────────────────────────────


def test_template_limits_have_one_source():
    from src.serialisers.freespace_templates import TemplateInput
    from src.services.freespace.templates import (
        MAX_BODY_LENGTH,
        MAX_TITLE_LENGTH,
        TemplateValidationError,
        validate_template,
    )

    # The serialiser does not cap length; the validator does, with its code.
    TemplateInput(title="t" * (MAX_TITLE_LENGTH + 1), body="b")
    with pytest.raises(TemplateValidationError):
        validate_template(AdvisoryType.TEST, "t" * (MAX_TITLE_LENGTH + 1), "{site}")
    with pytest.raises(TemplateValidationError):
        validate_template(AdvisoryType.TEST, "t", "b" * (MAX_BODY_LENGTH + 1))


# ─────────────────────────────────────────────────────────────
# 22-23: main.py log privacy and the /v1 429 shape
# ─────────────────────────────────────────────────────────────


async def test_unhandled_exception_logs_route_template(monkeypatch):
    import main

    printed = []
    monkeypatch.setattr(
        main, "print_exception_with_trace", lambda exc, msg: printed.append(msg)
    )
    handler = main.app.exception_handlers[Exception]
    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "path": f"/v1/devices/{DEVICE_ID}",
            "headers": [],
            "query_string": b"",
            "route": SimpleNamespace(path="/v1/devices/{device_id}"),
        }
    )
    response = await handler(request, RuntimeError("x"))
    assert response.status_code == 500
    assert printed and DEVICE_ID not in printed[0]
    assert "/v1/devices/{device_id}" in printed[0]


async def test_v1_rate_limit_uses_standard_shape(client, fs_app_headers):
    responses = [
        await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
        for _ in range(11)
    ]
    limited = responses[-1]
    assert limited.status_code == 429
    assert limited.json() == {
        "detail": "Too many requests for this device",
        "detail_code": "device.rate_limited",
    }
    retry_after = limited.headers["retry-after"]
    assert retry_after.isdigit() and 1 <= int(retry_after) <= 600
    from prometheus_client import REGISTRY, generate_latest

    assert DEVICE_ID not in generate_latest(REGISTRY).decode()
