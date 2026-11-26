"""M5: a deviceId and an FCM token never reach logs, request_log, metrics or
Redis keys (BF-35, D5)."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import fakeredis
import pytest
from sqlalchemy import select

from src.middleware import request_response_logging as rrl
from src.middleware.request_response_logging import (
    loggable_path,
    sanitize_data,
)
from src.models.device import Device
from src.models.request_log import RequestLog
from src.services.config_cache import RequestLoggingConfig
from tests.conftest import _fake_redis_server


DEVICE_ID = "leakcheckDEVICEid_0123456789abcdef"
TOKEN = "leakcheckTOKEN:" + "qW3rTy9u" * 20


class _Session:
    """Async context manager handing out the shared test session."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def captured_logs(monkeypatch, async_session):
    """Capture the request log stream and force file + DB request logging on."""

    async def config():
        return RequestLoggingConfig(
            enabled=True, db_enabled=True, max_body_size=10240, retention_days=30
        )

    monkeypatch.setattr("src.services.config_cache.get_request_logging_config", config)
    monkeypatch.setattr("src.database.AsyncSessionLocal", _Session(async_session))

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    # httpx/httpcore are the TEST CLIENT logging its own outgoing URL, not the server.
    handler.addFilter(lambda r: not r.name.startswith(("httpx", "httpcore")))
    root = logging.getLogger()
    req_logger = logging.getLogger("request_response_logger")
    old_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    req_logger.addHandler(handler)
    yield stream
    root.removeHandler(handler)
    req_logger.removeHandler(handler)
    root.setLevel(old_level)


def _log_file_text() -> str:
    text = ""
    for handler in logging.getLogger("request_response_logger").handlers:
        name = getattr(handler, "baseFilename", None)
        if name and Path(name).exists():
            handler.flush()
            text += Path(name).read_text(errors="ignore")
    return text


def _redis_dump() -> str:
    redis = fakeredis.FakeRedis(server=_fake_redis_server)
    parts = []
    for key in redis.keys("*"):
        parts.append(key.decode(errors="ignore"))
        try:
            value = redis.get(key)
        except Exception:
            value = None
        if isinstance(value, bytes):
            parts.append(value.decode(errors="ignore"))
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_put_and_delete_leave_no_trace(
    client, async_session, fs_app_headers, fs_site, captured_logs, caplog, fs_redis
):
    caplog.set_level(logging.INFO)
    payload = {
        "fcmToken": TOKEN,
        "platform": "IOS",
        "siteIds": [fs_site.slug],
        "notificationsEnabled": True,
        "appVersion": "1.0",
    }
    put = await client.put(
        f"/v1/devices/{DEVICE_ID}", json=payload, headers=fs_app_headers
    )
    assert put.status_code == 200
    # Invalid body: FastAPI's 422 path must not log the secrets either.
    bad = await client.put(
        f"/v1/devices/{DEVICE_ID}",
        json={**payload, "platform": "PALM"},
        headers=fs_app_headers,
    )
    assert bad.status_code == 422

    # While registered: the DB holds the token but never the raw id.
    async_session.expire_all()
    for device in (await async_session.execute(select(Device))).scalars().all():
        row = " ".join(str(getattr(device, c.name)) for c in Device.__table__.columns)
        assert DEVICE_ID not in row

    delete = await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
    assert delete.status_code == 204

    # Somewhere to be sure the logs were really written.
    async_session.expire_all()
    logs = (await async_session.execute(select(RequestLog))).scalars().all()
    device_logs = [r for r in logs if r.path.startswith("/v1/devices")]
    assert len(device_logs) == 3
    assert {r.path for r in device_logs} == {"/v1/devices/{device_id}"}

    request_log_dump = "\n".join(
        f"{r.path} {r.request_body} {r.response_body} {r.error_traceback} {r.user_agent}"
        for r in logs
    )
    outputs = {
        "captured log stream": captured_logs.getvalue(),
        "caplog": "\n".join(
            r.getMessage()
            for r in caplog.records
            if not r.name.startswith(("httpx", "httpcore"))
        ),
        "log file": _log_file_text(),
        "request_log table": request_log_dump,
        "redis/limiter keys": _redis_dump()
        + "\n"
        + "\n".join(k.decode() for k in await fs_redis.keys("*")),
    }
    for name, text in outputs.items():
        assert DEVICE_ID not in text, f"deviceId leaked into {name}"
        assert TOKEN not in text, f"fcmToken leaked into {name}"
        assert "qW3rTy9u" not in text, f"part of the fcmToken leaked into {name}"

    assert "/v1/devices/{device_id}" in outputs["captured log stream"]

    # After DELETE nothing in the device tables carries either secret.
    async_session.expire_all()
    for device in (await async_session.execute(select(Device))).scalars().all():
        row = " ".join(str(getattr(device, c.name)) for c in Device.__table__.columns)
        assert DEVICE_ID not in row and TOKEN not in row


@pytest.mark.asyncio
async def test_unmatched_device_path_is_not_logged_raw(
    client, async_session, fs_app_headers, captured_logs
):
    resp = await client.get(
        f"/v1/devices/{DEVICE_ID}/nothing-here", headers=fs_app_headers
    )
    assert resp.status_code in (404, 405)
    assert DEVICE_ID not in captured_logs.getvalue()
    assert "/v1/devices/{unmatched}" in captured_logs.getvalue()
    async_session.expire_all()
    logs = (await async_session.execute(select(RequestLog))).scalars().all()
    assert all(DEVICE_ID not in r.path for r in logs)


@pytest.mark.asyncio
async def test_rate_limited_requests_do_not_expose_the_id(
    client, fs_app_headers, captured_logs
):
    for _ in range(11):
        resp = await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
    assert resp.status_code == 429
    assert DEVICE_ID not in captured_logs.getvalue()
    assert DEVICE_ID not in _redis_dump()
    from prometheus_client import REGISTRY, generate_latest

    # http_requests_* labels use the route template (metrics.py, fixed by M5).
    http_lines = [
        line
        for line in generate_latest(REGISTRY).decode().splitlines()
        if line.startswith("http_")
    ]
    assert DEVICE_ID not in "\n".join(http_lines)


@pytest.mark.asyncio
async def test_rate_limit_metrics_do_not_expose_the_id(client, fs_app_headers):
    for _ in range(11):
        await client.delete(f"/v1/devices/{DEVICE_ID}", headers=fs_app_headers)
    from prometheus_client import REGISTRY, generate_latest

    assert DEVICE_ID not in generate_latest(REGISTRY).decode()


def test_fcm_token_is_fully_masked_in_every_casing():
    data = {
        "fcmToken": TOKEN,
        "FCMTOKEN": TOKEN,
        "fcm_token": TOKEN,
        "FcmToken": TOKEN,
        "nested": {"fcmToken": TOKEN, "deviceId": DEVICE_ID},
        "list": [{"fcmToken": TOKEN}],
        "password": "hunter2hunter2",
        "platform": "IOS",
    }
    out = sanitize_data(data)
    text = str(out)
    assert TOKEN not in text and "leak" not in text and DEVICE_ID not in text
    for key in ("fcmToken", "FCMTOKEN", "fcm_token", "FcmToken"):
        assert out[key] == "********"
    assert out["nested"]["fcmToken"] == "********"
    assert out["list"][0]["fcmToken"] == "********"
    assert out["password"] == "hunt****"  # unchanged behaviour for other keys
    assert out["platform"] == "IOS"


def test_loggable_path_prefers_template_and_redacts_unmatched():
    class R:
        def __init__(self, path, route=None):
            self.scope = {"route": route} if route else {}
            self.url = type("U", (), {"path": path})()

    class Route:
        path = "/v1/devices/{device_id}"

    assert (
        loggable_path(R(f"/v1/devices/{DEVICE_ID}", Route()))
        == "/v1/devices/{device_id}"
    )
    assert loggable_path(R(f"/v1/devices/{DEVICE_ID}/x")) == rrl.UNMATCHED_DEVICE_PATH
    assert loggable_path(R("/nope")) == "/nope"
