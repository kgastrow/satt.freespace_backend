"""
Unit tests for ConnectionSender — the bounded outbound queue that keeps one
stalled client from stalling realtime delivery for everyone on the worker.

The regression these guard: the pub/sub listener is a single task per worker
that awaits each subscriber's callback in turn, and `websocket.send_json`
blocks on TCP drain. A client that stops reading therefore suspended the whole
listener. Measured on the reference implementation this is ported from, one
non-reading client turned 500 broadcasts to 20 clients from 94 ms into
39,723 ms. Under gunicorn that 39 s block also exceeds the default 30 s worker
timeout, so the arbiter kills the worker and drops every socket it holds.
"""

import asyncio

import pytest

from src.services.websocket.sender import WS_CLOSE_TRY_AGAIN_LATER, ConnectionSender


class StalledWebSocket:
    """A client that has stopped reading — `send_json` never completes."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.closed_with: int | None = None

    async def send_json(self, message: dict) -> None:
        self.started.set()
        await asyncio.Event().wait()

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


class RecordingWebSocket:
    """A healthy client that records what it received."""

    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.received.append(message)


class SlowButReadingWebSocket:
    """A HEALTHY client whose send costs real event-loop iterations.

    This is what `send_json` looks like above the transport's 64 KB high-water
    mark: `drain()` suspends, so one frame costs several turns of the loop
    rather than none. The fakes above cost ZERO iterations — `RecordingWebSocket`
    has no `await` in it at all — which is why they cannot tell a working
    backpressure mechanism from a broken one.
    """

    def __init__(self, cost: int = 3) -> None:
        self.cost = cost
        self.received: list[dict] = []
        self.closed_with: int | None = None

    async def send_json(self, message: dict) -> None:
        for _ in range(self.cost):
            await asyncio.sleep(0)
        self.received.append(message)

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


class FailingWebSocket:
    """A socket that has already gone away."""

    async def send_json(self, message: dict) -> None:
        raise RuntimeError("socket closed")


def frame(n: int) -> dict:
    return {"type": "notification", "payload": {"seq": n}}


async def _settle() -> None:
    """Yield enough for queued writer tasks to drain."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_offer_does_not_block_on_a_stalled_consumer():
    """The property the whole design exists for: offer never awaits."""
    socket = StalledWebSocket()
    sender = ConnectionSender(socket, "conn-stalled", maxsize=4)
    sender.start()

    sender.offer(frame(0))
    await _settle()
    assert socket.started.is_set(), "writer should be parked in send_json"

    # Far more frames than the queue holds, while the writer is stuck. Before
    # the fix the listener awaited send_json directly and would hang here.
    for n in range(1, 1000):
        sender.offer(frame(n))

    assert sender.overflowed
    await sender.stop()


@pytest.mark.asyncio
async def test_a_stalled_consumer_does_not_delay_a_healthy_one():
    """The actual 422x regression, in miniature."""
    stalled = ConnectionSender(StalledWebSocket(), "conn-stalled", maxsize=4)
    healthy_socket = RecordingWebSocket()
    healthy = ConnectionSender(healthy_socket, "conn-healthy", maxsize=4)
    stalled.start()
    healthy.start()

    # Mimic the listener's fan-out: hand each frame to every subscriber in turn.
    for n in range(20):
        stalled.offer(frame(n))
        healthy.offer(frame(n))
        await _settle()

    assert healthy_socket.received, "healthy client must keep receiving"
    assert healthy_socket.received[-1] == frame(19)

    await stalled.stop()
    await healthy.stop()


@pytest.mark.asyncio
async def test_overflow_closes_the_socket_instead_of_dropping_frames():
    """Nothing in this app resyncs a WebSocket stream.

    There is no sequence number, no gap detection and no refetch on reconnect,
    so a silently dropped frame corrupts a client's view permanently: a lost
    `maintenance` clear is delivered only by `useMaintenanceWebSocket`, so it
    wedges the user on the maintenance page until they reload by hand, and
    `data_export_status` is the only signal that a download is ready. Closing
    forces a reconnect, which remounts every mount-only query and rebuilds the
    view from the server.
    """
    socket = StalledWebSocket()
    sender = ConnectionSender(socket, "conn-full", maxsize=4)
    sender.start()
    await _settle()

    for n in range(100):
        sender.offer(frame(n))

    assert sender.overflowed
    assert sender.pending <= 4
    await _settle()

    # The flag is not the point — the CLOSE is. Cancelling the writer alone
    # leaves the socket open with a live receive loop and a dead data channel:
    # the client keeps getting pong replies while every broadcast is silently
    # discarded, forever, with no way for either side to notice.
    assert socket.closed_with == WS_CLOSE_TRY_AGAIN_LATER

    await sender.stop()


@pytest.mark.asyncio
async def test_maxsize_zero_is_not_treated_as_unbounded():
    """asyncio.Queue(maxsize=0) is unbounded — the opposite of what 0 implies."""
    sender = ConnectionSender(StalledWebSocket(), "conn-zero", maxsize=0)
    sender.start()
    await _settle()

    for n in range(50):
        sender.offer(frame(n))

    assert sender.overflowed
    await sender.stop()


@pytest.mark.asyncio
async def test_stop_survives_a_writer_that_raised():
    """`stop()` is the first statement in the endpoint's finally block.

    Anything escaping it skips the unsubscribe, the registry unregister and the
    connection-manager disconnect — a permanent callback leak.
    """

    class Exploding:
        async def send_json(self, message):
            raise BaseException("not an Exception subclass")

    sender = ConnectionSender(Exploding(), "conn-boom", maxsize=4)
    sender.start()
    sender.offer(frame(1))
    await _settle()

    await sender.stop()


@pytest.mark.asyncio
async def test_writer_stops_when_the_socket_is_gone():
    """A dead socket must not spin; the endpoint's finally block cleans up."""
    sender = ConnectionSender(FailingWebSocket(), "conn-dead", maxsize=4)
    sender.start()
    sender.offer(frame(1))

    await _settle()

    assert sender._task is not None
    assert sender._task.done()

    await sender.stop()


@pytest.mark.asyncio
async def test_stop_is_safe_before_start_and_twice():
    sender = ConnectionSender(RecordingWebSocket(), "conn-idle", maxsize=4)
    await sender.stop()

    sender.start()
    await sender.stop()
    await sender.stop()


@pytest.mark.asyncio
async def test_delivers_in_order_when_the_client_keeps_up():
    socket = RecordingWebSocket()
    sender = ConnectionSender(socket, "conn-ok", maxsize=32)
    sender.start()

    for n in range(10):
        sender.offer(frame(n))
    await _settle()

    assert socket.received == [frame(n) for n in range(10)]
    assert not sender.overflowed

    await sender.stop()


async def _drive_listener_burst(socket, *, burst, maxsize, stall_grace=2.0):
    """Run the REAL `RedisPubSub._listen` loop against a pre-buffered stream.

    Returns the sender so the caller can assert on overflow and delivery. The
    pub/sub side never suspends between frames, like hiredis returning straight
    from a buffer that one socket read already filled.
    """
    import json as _json

    from src.services.websocket.redis_pubsub import RedisPubSub

    channel = "ws:test:listener"

    class BufferedPubSub:
        def __init__(self):
            self._queued = [
                {
                    "type": "message",
                    "channel": channel,
                    "data": _json.dumps({"seq": n}),
                }
                for n in range(burst)
            ]

        async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            if self._queued:
                # Deliberately no await: hiredis returns straight from its
                # buffer when one socket read produced several messages, so the
                # listener gets no suspension from here.
                return self._queued.pop(0)
            await asyncio.sleep(0)
            return None

    sender = ConnectionSender(
        socket, "conn-listener", maxsize=maxsize, stall_grace=stall_grace
    )
    sender.start()

    # The real endpoint callback path.
    from src.api.websocket import _handle_pubsub_message

    callback = await _handle_pubsub_message(sender)

    pubsub = RedisPubSub()
    pubsub._pubsub = BufferedPubSub()
    pubsub._running = True
    pubsub._subscriptions[channel] = {"conn-listener": callback}

    task = asyncio.create_task(pubsub._listen())
    try:
        # Bounded so a regression fails the test rather than hanging the suite.
        async with asyncio.timeout(5):
            while len(socket.received) < burst and not sender.overflowed:
                await asyncio.sleep(0)
    except TimeoutError:
        pass
    finally:
        pubsub._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return sender


@pytest.mark.asyncio
async def test_a_slow_but_still_reading_client_is_never_closed():
    """The defect the previous version of this test could not catch.

    That test's fake `send_json` contained no `await` at all, so a send cost
    ZERO event-loop iterations and the writer kept up with any producer. It
    proved a yield existed in the listener; it did not prove the property it
    claimed.

    A real `send_json` blocks on transport drain. Above the 64 KB high-water
    mark — the slow-but-still-reading client this whole design exists for — one
    send costs several event-loop iterations. The listener's single
    `await sleep(0)` per frame hands each writer exactly ONE scheduling slot, so
    the queue then grows monotonically and a healthy connection is hard-closed
    with 1013. Measured before the fix, with a send costing three iterations:
    the client overflowed and was closed after 64 of a 200-frame burst.

    So the fake here costs real iterations, and it costs more of them than the
    listener hands out for free.
    """
    for cost in (1, 2, 3, 5):
        socket = SlowButReadingWebSocket(cost=cost)
        sender = await _drive_listener_burst(socket, burst=200, maxsize=64)

        assert not sender.overflowed, (
            f"a client that IS reading (send costs {cost} event-loop "
            "iterations) was closed as if it were dead"
        )
        assert len(socket.received) == 200
        assert socket.received[0] == {"seq": 0}
        assert socket.received[-1] == {"seq": 199}

        await sender.stop()


@pytest.mark.asyncio
async def test_a_client_that_reads_nothing_is_still_closed():
    """The other half of the property: slow must not become "never closed".

    Backpressure is bounded by the stall grace. A consumer that frees no queue
    slot at all within it is not slow, it is dead, and it still gets the 1013
    close that forces a resync.
    """
    socket = StalledWebSocket()
    sender = ConnectionSender(socket, "conn-dead-slow", maxsize=4, stall_grace=0.05)
    sender.start()
    await _settle()

    for n in range(20):
        await sender.deliver(frame(n))
        if sender.overflowed:
            break

    assert sender.overflowed
    await _settle()
    assert socket.closed_with == WS_CLOSE_TRY_AGAIN_LATER

    await sender.stop()


@pytest.mark.asyncio
async def test_deliver_does_not_wait_on_a_connection_with_no_writer():
    """A full queue with no writer can never drain.

    Waiting out the stall grace there would park the SHARED listener on a
    connection that is already finished, so `deliver` returns immediately
    instead.
    """
    socket = RecordingWebSocket()
    sender = ConnectionSender(socket, "conn-nowriter", maxsize=1, stall_grace=30.0)
    # No start(): there is no writer task at all.
    await sender.deliver(frame(0))

    await asyncio.wait_for(sender.deliver(frame(1)), timeout=0.5)
    assert not sender.overflowed
    assert sender.pending == 1

    await sender.stop()


@pytest.mark.asyncio
async def test_offer_still_closes_immediately_on_a_full_queue():
    """`offer` is the never-await path and keeps the old, harsher policy.

    A caller that cannot suspend cannot apply backpressure, so its only
    alternative to closing is dropping the frame — which this design rejects.
    The listener uses `deliver` precisely because it CAN await.
    """
    socket = StalledWebSocket()
    sender = ConnectionSender(socket, "conn-offer", maxsize=4, stall_grace=30.0)
    sender.start()
    await _settle()

    for n in range(50):
        sender.offer(frame(n))

    assert sender.overflowed
    await _settle()
    assert socket.closed_with == WS_CLOSE_TRY_AGAIN_LATER

    await sender.stop()


@pytest.mark.asyncio
async def test_stop_cancels_a_pending_closer_with_no_writer_task():
    """The guard in `stop()` was on the wrong field.

    `if self._task is None: return` sat ABOVE the `_closer` cancellation, and
    `offer()` creates a detached `_force_close` task whenever the queue fills —
    which it can do before `start()` ever ran. So `stop()` returned early and
    left that closer running detached past teardown.
    """
    socket = StalledWebSocket()
    sender = ConnectionSender(socket, "conn-leak", maxsize=1)
    # No start() — no writer task, which is exactly what the old guard keyed on.
    sender.offer(frame(0))
    sender.offer(frame(1))

    closer = sender._closer
    assert closer is not None, "overflow must spawn the closer"

    await sender.stop()

    assert sender._closer is None
    assert closer.done(), "stop() left a detached closer task running"


@pytest.mark.asyncio
async def test_endpoint_callback_never_touches_the_socket():
    """Pins the actual wiring, not just ConnectionSender in isolation.

    The one-line change in `_handle_pubsub_message` IS the fix — every other
    test here exercises the sender directly, so reverting the callback to
    `await websocket.send_json(message)` left the whole suite green.
    """
    from src.api.websocket import _handle_pubsub_message

    socket = StalledWebSocket()
    sender = ConnectionSender(socket, "conn-wiring", maxsize=32)
    sender.start()

    callback = await _handle_pubsub_message(sender)

    # A stalled socket makes send_json block forever. The callback must complete
    # regardless, because the shared pub/sub listener awaits it inline and a
    # block here stalls realtime for every connection on the worker.
    await asyncio.wait_for(callback(frame(1)), timeout=0.5)

    await sender.stop()
