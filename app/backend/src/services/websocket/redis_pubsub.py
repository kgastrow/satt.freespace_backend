"""
Redis Pub/Sub service for cross-worker WebSocket message routing.
Enables message delivery to WebSocket clients across multiple worker processes.
"""

import asyncio
from collections.abc import Coroutine
import json
from typing import Any, Callable, Optional
from uuid import UUID

import redis.asyncio as redis

from src.logger.logger import Logger
from src.services.cache import cache_service


# Type alias for message callback
MessageCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


def _get_channel_namespace() -> str:
    """Derive a channel namespace from the Redis DB number.

    Redis pub/sub is global across all databases on the same server.
    To isolate pub/sub between different environments (e2e tests per
    codebase, ADW worktrees, main app), we prefix channel names with
    the Redis database number from REDIS_URL.

    Returns empty string for DB 0 (default, backward compatible).
    """
    from src.core.config import settings

    try:
        # Parse DB number from redis://host:port/DB
        url = settings.REDIS_URL
        path = url.rsplit("/", 1)[-1] if "/" in url else "0"
        db = int(path) if path.isdigit() else 0
    except Exception:
        db = 0

    return f"db{db}:" if db > 0 else ""


# Computed lazily on first use (settings may not be ready at import time)
_CHANNEL_NS: Optional[str] = None


def _ensure_ns() -> str:
    """Lazy-init the channel namespace. Cached after first call."""
    global _CHANNEL_NS
    if _CHANNEL_NS is None:
        _CHANNEL_NS = _get_channel_namespace()
    return _CHANNEL_NS


class RedisPubSub:
    """
    Redis Pub/Sub service for WebSocket message routing.

    Channel patterns (namespaced by Redis DB for multi-environment isolation):
    - [db{N}:]ws:user:{user_id} - Direct notifications to a specific user
    - [db{N}:]ws:org:{org_id} - Tenant-wide broadcasts to an organization
    - [db{N}:]ws:platform - System announcements to all connected users

    The db{N}: prefix is omitted for DB 0 (backward compatible).
    This ensures pub/sub isolation when multiple environments share the same
    Redis server but use different databases (e2e tests, ADW worktrees, etc.).
    """

    # Base channel patterns (namespace prepended at runtime)
    _USER_PREFIX = "ws:user:"
    _ORG_PREFIX = "ws:org:"
    _PLATFORM_BASE = "ws:platform"

    # Supervisor backoff bounds for the listener loop (seconds). Fast enough
    # that a blip costs realtime a second, bounded so a hard-down Redis is not
    # hammered by every worker at once.
    _LISTEN_BACKOFF_BASE = 0.5
    _LISTEN_BACKOFF_MAX = 30.0

    def __init__(self) -> None:
        self._pubsub: Optional[redis.client.PubSub] = None
        self._dedicated_redis: Optional[redis.Redis] = None
        # Map of channel -> {callback_id -> callback}
        # This allows multiple callbacks per channel (for shared channels like org/platform)
        self._subscriptions: dict[str, dict[str, MessageCallback]] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
        # Set by stop() so the listener watchdog does not resurrect the task
        # during an intentional shutdown.
        self._stopping = False
        # Serializes writes against the single PubSub socket. redis-py's
        # PubSub.execute_command lazily calls self.connect() without locking,
        # so concurrent subscribe() calls on a fresh PubSub race to pull
        # connections from the pool, leaving orphaned connections subscribed
        # in Redis that the listener never drains — Redis reports
        # subscribers>0 while the client sees no messages. Lazy-init so the
        # lock binds to the worker's running event loop.
        self._pubsub_lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """Return the pubsub serialization lock, creating it lazily."""
        if self._pubsub_lock is None:
            self._pubsub_lock = asyncio.Lock()
        return self._pubsub_lock

    def set_redis(self, client: redis.Redis) -> None:
        """
        Inject a dedicated Redis connection for pub/sub.

        This should be a connection NOT shared with the general pool,
        because pub/sub subscribers hold connections open indefinitely
        and must not compete with request-serving operations.

        This is also the service's START hook: the app lifespan calls it on
        every startup, so it is where a `_stopping` latch left by a previous
        `stop()` is cleared. `subscribe()` refuses while that latch is set —
        that is what stops a handshake racing shutdown from resurrecting the
        listener behind `stop()`'s back — so something has to lift it, and the
        arrival of a live Redis connection is exactly the right signal.
        """
        self._dedicated_redis = client
        self._stopping = False
        Logger.info("Pub/sub service using dedicated Redis connection")

    def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis client — dedicated connection preferred, cache fallback."""
        if self._dedicated_redis is not None:
            return self._dedicated_redis
        # Fallback to cache service for backward compatibility
        if cache_service._redis is not None:
            return cache_service._redis
        return None

    async def _is_available(self) -> bool:
        """Check if Redis is available."""
        redis_client = self._get_redis()
        if redis_client is None:
            return False
        try:
            await redis_client.ping()
            return True
        except redis.ConnectionError:
            return False

    @classmethod
    def get_user_channel(cls, user_id: UUID) -> str:
        """Get the channel name for a specific user."""
        return f"{_ensure_ns()}{cls._USER_PREFIX}{str(user_id)}"

    @classmethod
    def get_org_channel(cls, organization_id: UUID) -> str:
        """Get the channel name for a specific organization."""
        return f"{_ensure_ns()}{cls._ORG_PREFIX}{str(organization_id)}"

    @classmethod
    def get_platform_channel(cls) -> str:
        """Get the platform-wide channel name."""
        return f"{_ensure_ns()}{cls._PLATFORM_BASE}"

    async def subscribe(
        self,
        channel: str,
        callback: MessageCallback,
        callback_id: Optional[str] = None,
    ) -> bool:
        """
        Subscribe to a Redis pub/sub channel.

        Args:
            channel: The channel name to subscribe to
            callback: Async function to call when a message is received
            callback_id: Optional unique ID for this callback (for unsubscribing).
                         If not provided, uses id(callback) as the key.

        Returns:
            True if subscription succeeded, False otherwise
        """
        if not await self._is_available():
            Logger.warning(
                "Redis unavailable, skipping channel subscription: %s", channel
            )
            return False

        redis_client = self._get_redis()
        assert redis_client is not None

        async with self._get_lock():
            try:
                if self._stopping:
                    # The service is shutting down (or has shut down). Rebuilding
                    # the connection here is how a handshake in flight used to
                    # defeat `stop()`: subscribe took the lock inside stop()'s
                    # suspension, cleared `_stopping`, opened a fresh pub/sub
                    # connection and spawned a listener that outlived shutdown —
                    # and `main.py` then closed the Redis pool underneath it.
                    # Refusing is honest: the caller's socket is about to die
                    # with the process anyway, and `subscribe_for_connection`
                    # already logs and reports the failure.
                    Logger.warning(
                        "Pub/sub is shutting down, refusing subscription: %s",
                        channel,
                    )
                    return False

                if self._pubsub is None:
                    # Pubsub was reset (e.g. by an earlier stop() or connection
                    # error). Recreate it and replay every tracked channel so
                    # previously-registered callbacks keep firing — otherwise
                    # only the incoming channel would be re-subscribed and
                    # existing clients would go silent.
                    self._pubsub = redis_client.pubsub()
                    if self._subscriptions:
                        await self._pubsub.subscribe(*self._subscriptions.keys())
                        Logger.info(
                            "Pub/sub recreated; replayed %d channel subscription(s)",
                            len(self._subscriptions),
                        )

                # Only subscribe to Redis if this is a new channel
                is_new_channel = channel not in self._subscriptions
                if is_new_channel:
                    await self._pubsub.subscribe(channel)
                    self._subscriptions[channel] = {}

                # Add callback to the channel's callback dict
                cb_id = callback_id if callback_id else str(id(callback))
                self._subscriptions[channel][cb_id] = callback

                # Start listener if there is not already a live one. The guard
                # is on the TASK, not on `_running` — see `_listener_alive`.
                # `_stopping` is deliberately NOT cleared here any more: only
                # `set_redis()` (the lifespan start hook) lifts a shutdown latch.
                if not self._listener_alive():
                    self._spawn_listener()
                else:
                    # A listener task exists but the flag may have been cleared
                    # (a stop() that a subscriber overtook). Re-arm the pump so
                    # the live task keeps draining instead of exiting.
                    self._running = True

                Logger.debug(
                    "Subscribed to channel: %s (callback_id=%s, total_callbacks=%d)",
                    channel,
                    cb_id,
                    len(self._subscriptions[channel]),
                )
                return True

            except redis.RedisError as e:
                Logger.warning("Failed to subscribe to channel %s: %s", channel, str(e))
                return False

    async def unsubscribe(
        self,
        channel: str,
        callback_id: Optional[str] = None,
    ) -> bool:
        """
        Unsubscribe from a Redis pub/sub channel.

        Args:
            channel: The channel name to unsubscribe from
            callback_id: If provided, only removes this specific callback.
                         If None, removes all callbacks and unsubscribes from Redis.

        Returns:
            True if unsubscription succeeded, False otherwise
        """
        if self._pubsub is None:
            return True

        async with self._get_lock():
            try:
                if channel not in self._subscriptions:
                    return True

                if callback_id:
                    # Remove specific callback
                    self._subscriptions[channel].pop(callback_id, None)
                    Logger.debug(
                        "Removed callback %s from channel: %s (remaining=%d)",
                        callback_id,
                        channel,
                        len(self._subscriptions[channel]),
                    )

                    # Only unsubscribe from Redis if no more callbacks for this channel
                    if not self._subscriptions[channel]:
                        if self._pubsub is not None:
                            await self._pubsub.unsubscribe(channel)
                        self._subscriptions.pop(channel, None)
                        Logger.debug("Unsubscribed from Redis channel: %s", channel)
                else:
                    # Remove all callbacks and unsubscribe
                    if self._pubsub is not None:
                        await self._pubsub.unsubscribe(channel)
                    self._subscriptions.pop(channel, None)
                    Logger.debug("Unsubscribed from channel: %s", channel)

                # Intentionally do NOT stop the listener when subscriptions drop
                # to zero. stop() awaits listener cancellation and closes the
                # shared pubsub client — during that suspension a concurrent
                # subscribe() from a reconnecting client can register on state
                # that stop() then wipes, leaving a dead listener and no
                # callbacks. The listener is cheap to keep idle; shutdown still
                # calls stop() explicitly from the app lifespan.
                return True

            except redis.RedisError as e:
                Logger.warning(
                    "Failed to unsubscribe from channel %s: %s", channel, str(e)
                )
                return False

    async def publish(self, channel: str, message: dict[str, Any]) -> bool:
        """
        Publish a message to a Redis pub/sub channel.

        Args:
            channel: The channel name to publish to
            message: The message dict to publish (will be JSON serialized)

        Returns:
            True if publish succeeded, False otherwise
        """
        if not await self._is_available():
            Logger.warning(
                "Redis unavailable, skipping message publish to: %s", channel
            )
            return False

        redis_client = self._get_redis()
        assert redis_client is not None

        try:
            message_json = json.dumps(message, default=str)
            await redis_client.publish(channel, message_json)
            Logger.debug("Published message to channel: %s", channel)
            return True

        except redis.RedisError as e:
            Logger.warning("Failed to publish to channel %s: %s", channel, str(e))
            return False

    async def publish_to_user(self, user_id: UUID, message: dict[str, Any]) -> bool:
        """
        Publish a message to a specific user's channel.

        Args:
            user_id: The target user ID
            message: The message dict to publish

        Returns:
            True if publish succeeded, False otherwise
        """
        channel = self.get_user_channel(user_id)
        return await self.publish(channel, message)

    async def publish_to_org(
        self, organization_id: UUID, message: dict[str, Any]
    ) -> bool:
        """
        Publish a message to an organization's channel.

        Args:
            organization_id: The target organization ID
            message: The message dict to publish

        Returns:
            True if publish succeeded, False otherwise
        """
        channel = self.get_org_channel(organization_id)
        return await self.publish(channel, message)

    async def publish_to_platform(self, message: dict[str, Any]) -> bool:
        """
        Publish a message to the platform-wide channel.

        Args:
            message: The message dict to publish

        Returns:
            True if publish succeeded, False otherwise
        """
        channel = self.get_platform_channel()
        return await self.publish(channel, message)

    async def broadcast_maintenance_mode(
        self, enabled: bool, message: Optional[str] = None
    ) -> bool:
        """
        Broadcast maintenance mode change to all connected clients.

        This publishes a maintenance notification to the platform channel,
        which will be received by all connected WebSocket clients.

        Args:
            enabled: Whether maintenance mode is being enabled or disabled
            message: Optional maintenance message

        Returns:
            True if broadcast succeeded, False otherwise
        """
        from datetime import datetime, timezone

        notification = {
            "type": "maintenance",
            "payload": {
                "enabled": enabled,
                "message": message or "System is under maintenance",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self.publish_to_platform(notification)

    async def _pump(self) -> None:
        """Drain pub/sub messages until ``_running`` goes false.

        Raises on any transport failure — recovery is the supervisor's job
        (``_listen``), not this loop's. Callback failures are contained here
        because one broken consumer must not cost every other subscriber its
        realtime feed.
        """
        pubsub = self._pubsub
        if pubsub is None:
            raise RuntimeError("pub/sub listener has no connection")

        while self._running:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message is None:
                continue

            if message["type"] != "message":
                continue

            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            try:
                parsed_message = json.loads(data)
            except json.JSONDecodeError:
                Logger.warning("Invalid JSON message on channel %s", channel)
                continue

            # Iterate a SNAPSHOT, not the live dict. `await callback(...)`
            # yields, and `subscribe`/`unsubscribe` mutate
            # `self._subscriptions[channel]` under a lock this listener
            # does not hold — so any WebSocket connecting or disconnecting
            # mid-broadcast changed the dict during iteration. The resulting
            # RuntimeError is raised by the iterator itself, NOT by the
            # callback, so it escaped the per-callback handler below.
            callbacks = list(self._subscriptions.get(channel, {}).items())
            for cb_id, callback in callbacks:
                try:
                    await callback(parsed_message)
                except Exception as e:
                    Logger.error(
                        "Error in message callback %s for channel %s: %s",
                        cb_id,
                        channel,
                        str(e),
                    )

            # Yield once per frame so the per-connection writer tasks get to
            # run. This used to happen implicitly: the callback awaited
            # send_json, which was real socket I/O. Now the callback normally
            # only enqueues, and hiredis returns straight from its buffer
            # without suspending whenever a single socket read produced several
            # messages — so without this the whole burst is enqueued before any
            # writer drains.
            #
            # This is FAIRNESS ONLY; it is not the backpressure mechanism and
            # must never be mistaken for one. One scheduling slot per frame is
            # exactly one step of each writer's coroutine, so any client whose
            # send costs more than one event-loop iteration — which is what a
            # transport drain above the 64 KB high-water mark costs, i.e. the
            # slow-but-still-reading client this whole design exists for — falls
            # behind monotonically no matter how many yields go here. The real
            # bound lives in `ConnectionSender.deliver()`, which waits for the
            # writer to free a slot and only closes a connection that frees
            # nothing at all within its stall grace.
            await asyncio.sleep(0)

    async def _reconnect(self) -> bool:
        """Rebuild the pub/sub connection and replay every tracked channel.

        Returns True when the connection is usable again. Re-subscribing the
        WHOLE tracked set matters: a fresh PubSub object knows nothing about
        the channels the old one held, so anything short of a full replay
        leaves already-connected clients silently unserved. Nothing but
        ``stop()`` used to clear ``_pubsub``, so the connection-error branch
        span forever on a dead socket after a Redis restart.
        """
        async with self._get_lock():
            old = self._pubsub
            self._pubsub = None
            if old is not None:
                try:
                    await old.aclose()
                except Exception:  # pragma: no cover - teardown is best-effort
                    pass

            redis_client = self._get_redis()
            if redis_client is None:
                Logger.warning("Pub/sub reconnect: no Redis client available")
                return False

            try:
                pubsub = redis_client.pubsub()
                channels = list(self._subscriptions.keys())
                if channels:
                    await pubsub.subscribe(*channels)
                self._pubsub = pubsub
                Logger.info(
                    "Pub/sub reconnected; replayed %d channel subscription(s)",
                    len(channels),
                )
                return True
            except Exception as e:
                Logger.error("Pub/sub reconnect failed: %s", str(e))
                self._pubsub = None
                return False

    async def _listen(self) -> None:
        """Supervise the message pump for the lifetime of the service.

        The pump used to BE the listener, and it caught only ``CancelledError``
        and ``redis.ConnectionError``. Anything else — a ``redis.TimeoutError``
        on a slow socket, a ``RuntimeError`` from a subscription dict mutated
        mid-broadcast, an attribute error on a malformed frame — unwound the
        task. ``_running`` stayed True, so ``subscribe``'s ``if not
        self._running`` guard never restarted it: realtime went permanently
        dead for the whole worker process, with nothing surfaced to any client,
        until the backend was restarted by hand.

        So: catch everything that is not a cancellation, back off (bounded
        exponential), rebuild the connection, replay the subscriptions, and
        keep pumping. Only ``stop()`` (or cancellation) ends this loop.
        """
        Logger.info("Pub/sub listener started")
        backoff = self._LISTEN_BACKOFF_BASE
        try:
            while self._running:
                try:
                    await self._pump()
                    # A clean return means _running went false — we are done.
                    backoff = self._LISTEN_BACKOFF_BASE
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    Logger.error(
                        "Pub/sub listener error (%s: %s); reconnecting in %.1fs",
                        type(e).__name__,
                        str(e),
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self._LISTEN_BACKOFF_MAX)
                    if not self._running:
                        break
                    await self._reconnect()
        except asyncio.CancelledError:
            # Honour cancellation rather than swallowing it: `stop()` awaits
            # this task, and a task that ends "finished" instead of "cancelled"
            # would look to the watchdog like a crash worth restarting.
            raise
        finally:
            # Whatever ended this task, the flag must reflect reality or
            # `subscribe()` will never start a replacement.
            self._running = False
            Logger.info("Pub/sub listener stopped")

    def _listener_alive(self) -> bool:
        """True while a listener TASK exists and has not finished.

        ``_running`` is a request ("the pump should keep draining"), not a fact
        ("a listener exists"), and the two are not the same thing for the whole
        window between ``stop()`` clearing the flag and the task actually
        unwinding, or between a crash and the watchdog firing. Spawning off the
        flag therefore started a SECOND listener on top of a live one, and two
        ``_listen`` tasks then call ``get_message`` on the same PubSub socket
        concurrently — redis-py's PubSub is not safe for that, every frame is
        delivered by whichever task wins the read, and ``stop()`` only ever
        awaits the one task it happens to hold in ``_listener_task``. Measured:
        301 concurrent ``_listen`` tasks across 300 kill/resubscribe rounds.

        Gating on the task itself makes a second listener structurally
        impossible rather than merely unreachable.
        """
        task = self._listener_task
        return task is not None and not task.done()

    def _spawn_listener(self) -> None:
        """Start the listener task under a watchdog that restarts it."""
        if self._listener_alive():
            # Never stack a second reader on the same PubSub socket. The caller
            # wanted the pump running; it already is.
            self._running = True
            return
        self._running = True
        task = asyncio.create_task(self._listen())
        self._listener_task = task
        task.add_done_callback(self._on_listener_done)

    def _on_listener_done(self, task: "asyncio.Task[None]") -> None:
        """Watchdog: resurrect a listener that ended while clients still need it.

        ``_listen`` should only end on ``stop()``, but a task can also die on
        something no handler anticipated (an ``asyncio.CancelledError`` raised
        into it from elsewhere, a loop shutdown race). Belt-and-braces: if
        subscriptions remain and we are not shutting down, start a new one.
        """
        if self._listener_task is not task:
            return
        self._listener_task = None
        self._running = False
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:  # pragma: no cover - _listen swallows its own
            Logger.error("Pub/sub listener task crashed: %s", str(exc))
        if self._stopping or not self._subscriptions:
            return
        Logger.warning(
            "Pub/sub listener exited with %d channel(s) still subscribed — restarting",
            len(self._subscriptions),
        )
        try:
            self._spawn_listener()
        except RuntimeError:  # pragma: no cover - loop already closed
            self._running = False

    # Belt-and-braces bound on the "a listener reappeared while we were tearing
    # the old one down" retry. `_stopping` already keeps the watchdog from
    # respawning, so one pass is the norm; the bound exists so a pathological
    # case can never make shutdown unbounded.
    _STOP_MAX_PASSES = 3

    async def stop(self) -> None:
        """Stop the pub/sub listener and clean up.

        Every mutation happens UNDER THE LOCK, and the listener task is
        re-checked after the await instead of being assigned unconditionally.

        This method used to be the only one that touched ``_pubsub``,
        ``_subscriptions`` and ``_listener_task`` without holding the lock —
        while also suspending half-way through, at ``await self._listener_task``.
        A ``subscribe()`` landing in that window took the lock, reset
        ``_stopping`` and spawned a fresh listener; ``stop()`` then resumed and
        blindly assigned ``_listener_task = None``, dropping the reference, and
        the identity guard in ``_on_listener_done`` guaranteed the orphan was
        never noticed. Measured across every interleaving: ``stop()`` returned
        with ``_running`` True, a live ``_listen`` task, a Redis pub/sub
        connection opened AFTER shutdown and never closed, and subscriptions
        still registered — and ``main.py`` then tore the Redis connection out
        from under that live listener. A rolling restart with a handshake in
        flight is exactly the reconnect storm this code exists to survive.

        The cancel deliberately happens BEFORE the lock is taken. The listener
        acquires the same lock inside ``_reconnect()``, so cancelling first
        guarantees the lock is released promptly instead of making shutdown wait
        out a reconnect against a dead socket.
        """
        # Set before anything else: the watchdog reads `_stopping` to tell an
        # intentional shutdown from a crash it must restart.
        self._stopping = True
        self._running = False

        for _ in range(self._STOP_MAX_PASSES):
            task = self._listener_task
            if task is not None:
                task.cancel()

            async with self._get_lock():
                if task is not None:
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception:  # pragma: no cover - _listen contains its own
                        pass

                # Re-check rather than assign: `_listener_task` may no longer be
                # the task we just awaited.
                if self._listener_task is task:
                    self._listener_task = None

                pubsub, self._pubsub = self._pubsub, None
                self._subscriptions.clear()
                self._running = False

                if pubsub is not None:
                    try:
                        await pubsub.unsubscribe()
                        await pubsub.aclose()
                    except redis.RedisError:
                        pass
                    except Exception:  # pragma: no cover - teardown is best-effort
                        pass

                if not self._listener_alive():
                    self._listener_task = None
                    Logger.debug("Pub/sub service stopped")
                    return

            Logger.warning(
                "Pub/sub stop() found a listener that reappeared mid-shutdown; "
                "tearing it down again"
            )

        Logger.error(
            "Pub/sub stop() gave up after %d passes with a listener still alive",
            self._STOP_MAX_PASSES,
        )

    async def subscribe_for_connection(
        self,
        user_id: UUID,
        organization_id: UUID,
        callback: MessageCallback,
        connection_id: Optional[str] = None,
    ) -> bool:
        """
        Subscribe to all relevant channels for a connection.

        This subscribes to:
        - User-specific channel
        - Organization channel
        - Platform-wide channel

        Args:
            user_id: The user ID
            organization_id: The organization ID
            callback: Async function to call when a message is received
            connection_id: Unique connection ID used to track this subscription

        Returns:
            True if all subscriptions succeeded, False otherwise
        """
        user_channel = self.get_user_channel(user_id)
        org_channel = self.get_org_channel(organization_id)
        platform_channel = self.get_platform_channel()

        # Serialize the three subscribes rather than gather(). A shared
        # PubSub holds one TCP connection and redis-py's execute_command
        # acquires it without locking — three racing coroutines could each
        # trip the "self.connection is None" branch in PubSub.connect() and
        # each acquire a separate pool connection. Redis would then report
        # subscribers>0 per channel while the listener drains only one of
        # those connections. The lock in subscribe() already serializes
        # these; sequential awaits make that explicit.
        r1 = await self.subscribe(user_channel, callback, callback_id=connection_id)
        r2 = await self.subscribe(org_channel, callback, callback_id=connection_id)
        r3 = await self.subscribe(platform_channel, callback, callback_id=connection_id)

        success = r1 and r2 and r3
        if not success:
            Logger.warning(
                "Some subscriptions failed for user %s org %s",
                user_id,
                organization_id,
            )

        return success

    async def unsubscribe_for_connection(
        self,
        user_id: UUID,
        organization_id: UUID,
        connection_id: Optional[str] = None,
    ) -> bool:
        """
        Unsubscribe from all channels for a connection.

        Args:
            user_id: The user ID
            organization_id: The organization ID
            connection_id: The connection ID to unsubscribe (removes only this callback)

        Returns:
            True if all unsubscriptions succeeded, False otherwise
        """
        user_channel = self.get_user_channel(user_id)
        org_channel = self.get_org_channel(organization_id)
        platform_channel = self.get_platform_channel()

        # Serialized for the same reason as subscribe_for_connection.
        r1 = await self.unsubscribe(user_channel, callback_id=connection_id)
        r2 = await self.unsubscribe(org_channel, callback_id=connection_id)
        r3 = await self.unsubscribe(platform_channel, callback_id=connection_id)

        return r1 and r2 and r3


# Singleton instance
redis_pubsub = RedisPubSub()
