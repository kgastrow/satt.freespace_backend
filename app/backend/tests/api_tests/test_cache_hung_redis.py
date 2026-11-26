"""
A hung Redis must not turn authenticated requests into 500s.

``src/api/deps.py`` calls ``cache_service.get_jwt_claims(token)`` on the
authentication path. Inside the cache service, ``await self._is_available()``
sits OUTSIDE each operation's ``try``, so anything it raised escaped the cache
service and reached the request handler.

``_is_available`` used to catch only ``redis.ConnectionError``. redis-py's
``TimeoutError`` subclasses ``RedisError``, not ``ConnectionError``, and the
cache client is created with ``socket_timeout=1`` - so a Redis that accepts
connections but stops answering (a failover, a blocked event loop, a SWAP
storm) raised ``redis.TimeoutError`` out of ``ping()`` and every authenticated
request became a 500. Bare ``OSError`` behaved the same way.
"""

import asyncio

import pytest
import redis.asyncio as redis

from src.services.cache import cache_service


class HungRedis:
    """Accepts the connection, then never answers - every call raises."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def ping(self):
        raise self.exc

    async def get(self, *args, **kwargs):
        raise self.exc

    async def setex(self, *args, **kwargs):
        raise self.exc

    async def sadd(self, *args, **kwargs):
        raise self.exc

    async def smembers(self, *args, **kwargs):
        raise self.exc

    async def delete(self, *args, **kwargs):
        raise self.exc


@pytest.mark.parametrize(
    "exc",
    [
        redis.TimeoutError("no reply within socket_timeout"),
        redis.ConnectionError("connection reset by peer"),
        OSError("broken pipe"),
        asyncio.TimeoutError(),
    ],
    ids=["redis-timeout", "connection-error", "oserror", "asyncio-timeout"],
)
@pytest.mark.asyncio
async def test_hung_redis_does_not_500_authenticated_requests(
    client, test_jwt_token, monkeypatch, exc
):
    """Authentication degrades to the database instead of failing the request."""
    monkeypatch.setattr(cache_service, "_enabled", True)
    monkeypatch.setattr(cache_service, "_redis", HungRedis(exc))
    monkeypatch.setattr(cache_service, "_unavailable_until", 0.0)

    response = await client.get(
        "/api/v1/user/me", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 200, (
        f"a hung Redis ({type(exc).__name__}) escaped the cache service and "
        f"failed the request: {response.status_code} {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_hung_redis_does_not_latch_caching_off(
    client, test_jwt_token, monkeypatch
):
    """After the outage, ``_enabled`` is untouched - only a cooldown was set."""
    monkeypatch.setattr(cache_service, "_enabled", True)
    monkeypatch.setattr(cache_service, "_redis", HungRedis(redis.TimeoutError("hung")))
    monkeypatch.setattr(cache_service, "_unavailable_until", 0.0)

    response = await client.get(
        "/api/v1/user/me", headers={"Authorization": test_jwt_token}
    )
    assert response.status_code == 200

    assert cache_service._enabled is True
    assert cache_service._unavailable_until > 0.0
