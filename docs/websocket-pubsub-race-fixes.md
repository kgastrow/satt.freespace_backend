# WebSocket Pub/Sub Race Condition Fixes

Three distinct race conditions in `src/services/websocket/redis_pubsub.py` that together produce the symptom: **a WebSocket is connected, `ping/pong` works, Redis reports `subscribers>0`, but the client never receives pushed messages on some workers**. Whether events arrive depends on which worker caught the WS and whether that worker has been poisoned by an earlier race. No errors in logs — state just gets stomped.

All three should be applied together. None depends on codebase-specific structure beyond a `RedisPubSub` class with `subscribe()`, `unsubscribe()`, a listener task, and a `subscribe_for_connection()` fan-out.

---

## Race 1 — `unsubscribe()` auto-stops the listener during a refresh

### Sequence that breaks

1. Old WS closes. In `finally`, `unsubscribe_for_connection()` runs. When the last subscription is removed, `unsubscribe()` calls `await self.stop()`.
2. `stop()` awaits `self._listener_task` cancellation — **a suspension point**.
3. New WS (same user, page refresh) hits the backend during that suspension. `subscribe_for_connection()` runs. It reads `self._pubsub` (still non-None — `stop()` hasn't closed it yet), calls `await self._pubsub.subscribe(new_channel)`. **Another suspension point.**
4. `stop()` resumes: calls `self._pubsub.unsubscribe()` / `aclose()`, sets `_pubsub = None`, then `self._subscriptions.clear()` — **wiping the new client's just-registered callback**.
5. The new `subscribe()` resumes, adds its callback to `_subscriptions`, sees `_running = False`, flips it to `True`, starts a new listener task.
6. New listener hits `if self._pubsub is None: return` and exits immediately. `_running` stays `True`, so no subsequent `subscribe()` ever starts another listener. **That worker is permanently broken for pub/sub until process restart.**

### Fix

Remove the auto-stop. The listener + dedicated Redis connection are cheap to keep idle; `stop()` is only called explicitly on app shutdown.

```python
# In unsubscribe(), replace:
if not self._subscriptions:
    await self.stop()

# with (just delete the branch; comment explains why):
# Intentionally do NOT stop the listener when subscriptions drop
# to zero. stop() awaits listener cancellation and closes the
# shared pubsub client — during that suspension a concurrent
# subscribe() from a reconnecting client can register on state
# that stop() then wipes, leaving a dead listener and no
# callbacks. The listener is cheap to keep idle; shutdown still
# calls stop() explicitly from the app lifespan.
```

### Companion change — call `stop()` from lifespan shutdown

If your lifespan shutdown doesn't already call `await redis_pubsub.stop()`, add it **before** tearing down the shared Redis pool, otherwise the listener task is orphaned on shutdown:

```python
# In main.py lifespan, in the shutdown block:
try:
    from src.services.websocket.redis_pubsub import redis_pubsub
    await redis_pubsub.stop()
except Exception as e:
    logger.warning(f"Failed to stop pub/sub service cleanly: {e}")

# THEN close the Redis pool
```

### Test update

Any test asserting "`unsubscribing the last channel stops the listener`" encodes the bug as spec. Flip it:

```python
async def test_unsubscribe_keeps_listener_running_when_empty(self, fake_redis):
    pubsub = RedisPubSub()
    # ... setup ...
    await pubsub.subscribe("test:channel", callback)
    assert pubsub._running is True

    await pubsub.unsubscribe("test:channel")

    assert pubsub._running is True          # was: is False
    assert pubsub._subscriptions == {}

    await pubsub.stop()                      # explicit cleanup
    assert pubsub._running is False
```

---

## Race 2 — `subscribe()` recreates `_pubsub` but drops tracked channels

### Sequence that breaks

Only applies if anything in your codebase can null `self._pubsub` **without** also clearing `self._subscriptions` (e.g. a `_reset_connection()` called from `publish()` on a connection error). Template codebase doesn't have that today; downstream variants do.

1. `publish()` hits a connection error, calls `_reset_connection()`, which sets `self._pubsub = None` but leaves `self._subscriptions` populated.
2. Next `subscribe(new_channel)` call: `self._pubsub is None` → recreate via `redis_client.pubsub()`. Code then only re-subscribes **the new incoming channel** because `is_new_channel = channel not in self._subscriptions` is False for the pre-existing ones.
3. The old channels are in `self._subscriptions` but NOT subscribed on the new `_pubsub`. Redis sends nothing for them. Callbacks go silent without any error.

### Fix

When recreating `_pubsub`, replay every tracked channel:

```python
try:
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
    # ... rest of subscribe unchanged ...
```

Apply even if your repo doesn't have `_reset_connection()` — defense in depth, cost is one conditional branch.

---

## Race 3 — concurrent `subscribe()` fan-out races inside `PubSub.execute_command`

### Sequence that breaks

`redis-py`'s `PubSub.execute_command` lazily calls `self.connect()` and does **not** serialize concurrent callers. When `subscribe_for_connection()` fans out three subscribes via `asyncio.gather()` on a fresh `PubSub`:

1. Three coroutines enter `PubSub.execute_command` concurrently.
2. Each sees `self.connection is None` and independently acquires a connection from the dedicated pub/sub pool.
3. The `PubSub` object's `self.connection` ends up pointing at whichever connection won the last assignment. The **other two** connections are live in the pool, hold valid `SUBSCRIBE` state on Redis, and are never drained by the listener.
4. Result: Redis reports `subscribers=3` for the three channels (because the sockets are alive), but the listener reads from only one of them. Messages on the other two channels are received by Redis, delivered on the orphaned sockets, and silently dropped client-side.

### Fix — two parts

**Part A: Add an `asyncio.Lock` around all `_pubsub` mutations.**

```python
# In __init__:
self._pubsub_lock: Optional[asyncio.Lock] = None

# New helper (lazy-init so the lock binds to the worker's event loop,
# which may not exist at module-import time under gunicorn):
def _get_lock(self) -> asyncio.Lock:
    if self._pubsub_lock is None:
        self._pubsub_lock = asyncio.Lock()
    return self._pubsub_lock
```

Wrap the full body of `subscribe()` and `unsubscribe()` in `async with self._get_lock():`. If your codebase has `_resubscribe_all()` or similar, wrap it too.

**Unsubscribe subtlety**: after adding the lock, `unsubscribe()` must re-check `self._pubsub is not None` **inside the lock**, before calling `self._pubsub.unsubscribe(channel)`. `stop()` does not take the lock (it must be able to run during shutdown regardless of state), so `_pubsub` can be nulled between the outer early-return check and the inner call.

```python
if self._pubsub is None:
    return True

async with self._get_lock():
    try:
        if channel not in self._subscriptions:
            return True
        # ...
        if not self._subscriptions[channel]:
            if self._pubsub is not None:               # re-check inside lock
                await self._pubsub.unsubscribe(channel)
            self._subscriptions.pop(channel, None)
```

**Part B: Serialize the `subscribe_for_connection()` fan-out.**

The lock in `subscribe()` already serializes these, but using sequential awaits at the call site makes the serialization contract explicit and rules out any future change that accidentally re-introduces `asyncio.gather`:

```python
# Before:
results = await asyncio.gather(
    self.subscribe(user_channel, callback, callback_id=connection_id),
    self.subscribe(org_channel, callback, callback_id=connection_id),
    self.subscribe(platform_channel, callback, callback_id=connection_id),
    return_exceptions=True,
)
success = all(r is True for r in results)

# After:
r1 = await self.subscribe(user_channel, callback, callback_id=connection_id)
r2 = await self.subscribe(org_channel, callback, callback_id=connection_id)
r3 = await self.subscribe(platform_channel, callback, callback_id=connection_id)
success = r1 and r2 and r3
```

Same change in `unsubscribe_for_connection()`.

---

## Observability bump (optional but strongly recommended)

Bump listener lifecycle logs from `DEBUG` to `INFO` so next occurrence you can confirm the listener actually started and that it's not exiting early:

```python
# In _listen():
if self._pubsub is None:
    Logger.warning("Pub/sub listener started with no pubsub — exiting")
    return
Logger.info("Pub/sub listener started")

# In the finally block at the end of _listen():
Logger.info("Pub/sub listener stopped (running=%s)", self._running)
```

Also consider bumping the per-subscribe log from `DEBUG` to `INFO` during the bake-in period to confirm the lock serializes as expected and the channel count grows monotonically.

---

## Application order

1. **Race 1 fix** (remove auto-stop + add lifespan `stop()`) — biggest behavioral win, simplest change.
2. **Race 3 fix** (add lock + serialize fan-out) — fixes the "subscribers>0 but no messages" case that Race 1 doesn't cover.
3. **Race 2 fix** (resubscribe all channels on `_pubsub` recreation) — cheap defense-in-depth; required wherever a `_reset_connection()`-style path exists.
4. **Log bumps** — apply alongside whichever of the above land first, so the next incident is diagnosable.

## Adaptation notes for downstream variants

- **If the downstream has `_reset_connection()`** (nulls `_pubsub` on publish-time connection errors): Race 2 fix is load-bearing, not optional.
- **If the downstream has `_resubscribe_all()`** (used to re-establish subscriptions after a reconnect): wrap its body under the same `_get_lock()` — otherwise it races with concurrent `subscribe()` / `unsubscribe()`.
- **If the downstream's `stop()` takes the lock**: it must use a non-blocking acquisition or a timeout, or you deadlock when a concurrent `subscribe()` holds the lock and waits on something that requires shutdown.
- **If the downstream shares the `PubSub` across modules**: audit all direct `self._pubsub.subscribe(...)` / `unsubscribe(...)` call sites and route them through the locked `subscribe()` / `unsubscribe()` methods.

## Symptom-to-cause quick reference

| Symptom | Likely race |
| --- | --- |
| Pub/sub silently dead after page refresh, ping/pong still works, process restart fixes it | Race 1 |
| Existing clients go silent after a publish-time Redis error; new clients work | Race 2 |
| Redis reports `subscribers>0` but some workers deliver nothing | Race 3 |
| All of the above, intermittent, worker-dependent | All three; apply together |
