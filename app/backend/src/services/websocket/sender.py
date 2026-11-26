"""
Per-connection outbound send queue for WebSocket fan-out.

The pub/sub listener is a single task per worker. It delivers one broadcast by
awaiting every subscribed connection's callback in turn, so anything a callback
blocks on blocks the whole worker's realtime delivery.

`websocket.send_json` blocks on TCP drain: once a client stops reading, its
socket buffer fills at the 64 KB high-water mark and the send suspends until the
client reads or the connection dies. A backgrounded mobile tab, a phone walking
out of coverage, or a paused debugger can hold that state for minutes. Measured
on the reference implementation this port comes from, one non-reading client
turned 500 broadcasts to 20 clients from 94 ms into 39,723 ms — a 422x
regression, with a single send blocked for 39.6 s.

Two things make that worse than slow delivery. Production runs gunicorn, whose
arbiter SIGKILLs any worker that has not updated its heartbeat within `--timeout`
(default 30 s); `UvicornWorker` writes that heartbeat from the event loop, so a
39 s block kills the worker and drops every socket it holds. Those clients then
all reconnect at once.

This module puts a bounded queue and a writer task between the listener and the
socket. `offer()` never blocks and never awaits, so a stalled client costs its
own queue and nothing else.

When that queue fills the socket is CLOSED rather than silently drained. Nothing
in this app resyncs a WebSocket stream: there is no sequence number, no gap
detection, and no refetch on reconnect. Several frames are the only mechanism
that exists for what they do — a `maintenance` clear is delivered solely by
`useMaintenanceWebSocket`, so dropping it strands the user on the maintenance
page until they reload by hand, and the same is true of `data_export_status`
and the in-app notification frames. Dropping any of those quietly corrupts a
client's view with no way back. Closing turns that into a visible blip: the
client reconnects, every mount-only query remounts, and the view is rebuilt
from the server.
"""

import asyncio
from typing import Any

from fastapi import WebSocket

from src.logger.logger import Logger


# TUNING PARAMETER — a fork of this template should revisit it against its own
# traffic. This template's own producers are all event-driven and low-rate
# (notifications, announcements, maintenance toggles, export completion), so a
# queue this deep is only ever filled by a genuinely stalled consumer, never by
# a legitimate burst. 64 leaves headroom for a fork that adds a chattier lane
# (live chat, telemetry, progress ticks) before the close-and-resync policy
# starts firing on healthy clients, while still bounding per-connection memory
# to roughly 32 KB at typical frame sizes. The bound is the point: the previous
# behaviour was unbounded blocking rather than unbounded buffering, but both are
# unbounded. Raise it if your frames are small and bursty; lower it if they are
# large or if you would rather force a resync sooner.
SEND_QUEUE_MAXSIZE = 64

# How long `deliver()` waits for a backlogged connection to free ONE queue slot
# before concluding the client is not reading at all.
#
# This is the line between "slow" and "dead", and it has to be drawn on writer
# PROGRESS, not on queue depth. A full queue on its own proves nothing: a client
# that reads steadily but more slowly than a burst arrives fills the queue and
# then empties it again, one slot at a time. Waiting for a slot lets that client
# through at its own pace — the listener simply runs in lock-step with the
# slowest writer for the length of the burst — while a client that is not
# reading at all never frees anything and is closed once the grace expires.
#
# The cost of the wait is head-of-line delay on the shared listener: one dying
# connection can hold up realtime delivery for everyone on this worker for up to
# this long. It is one-shot per connection (`_overflowed` short-circuits every
# later frame) and it is a delay, not a worker kill — `offer`/`deliver` suspend
# the listener task, not the event loop, so uvicorn's gunicorn heartbeat keeps
# ticking. 2 s is chosen to comfortably exceed a single TCP retransmit timeout on
# a bad mobile link (the case we must NOT misread as death) while keeping that
# worst-case pause an order of magnitude below the 30 s gunicorn worker timeout.
SEND_STALL_GRACE_SECONDS = 2.0

# Sent when a client is too far behind to keep. 1013 is "Try Again Later", which
# is what we mean: nothing is wrong with the client's credentials or request.
WS_CLOSE_TRY_AGAIN_LATER = 1013


class ConnectionSender:
    """Owns the outbound half of one WebSocket connection."""

    def __init__(
        self,
        websocket: WebSocket,
        connection_id: str,
        *,
        maxsize: int = SEND_QUEUE_MAXSIZE,
        stall_grace: float = SEND_STALL_GRACE_SECONDS,
    ) -> None:
        self._websocket = websocket
        self._connection_id = connection_id
        # maxsize=0 means UNBOUNDED in asyncio, which is the exact opposite of
        # what a caller passing 0 would intend.
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=max(1, maxsize)
        )
        self._stall_grace = max(0.0, stall_grace)
        self._task: asyncio.Task[None] | None = None
        self._closer: asyncio.Task[None] | None = None
        self._overflowed = False

    @property
    def overflowed(self) -> bool:
        """True if this client fell far enough behind to have its socket closed."""
        return self._overflowed

    @property
    def pending(self) -> int:
        """Frames queued but not yet written."""
        return self._queue.qsize()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def offer(self, message: dict[str, Any]) -> None:
        """
        Hand a frame to this connection without ever blocking the caller.

        For callers that cannot await at all. A full queue is treated as fatal
        immediately, because a caller that cannot suspend has no way to apply
        backpressure and the only alternative left is dropping the frame — see
        the module docstring for why closing beats dropping.

        The pub/sub listener uses `deliver()` instead: it CAN await, so it can
        tell a slow reader from a dead one instead of guessing from queue depth.
        """
        if self._overflowed:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self._declare_overflow()

    async def deliver(self, message: dict[str, Any]) -> None:
        """
        Hand a frame to this connection, applying bounded backpressure.

        The fast path is `put_nowait`: while the client keeps up this does not
        suspend at all, so a healthy connection costs the shared listener
        nothing.

        A full queue is where the previous version went wrong. It closed the
        socket on the spot, which equates "this queue is full right now" with
        "this client is dead". Those are different. `send_json` blocks on
        transport drain, so above the 64 KB high-water mark a client that IS
        reading — just slower than the burst arriving — costs more than one
        event-loop iteration per frame. The listener's one `await sleep(0)` per
        frame gives each writer exactly one scheduling slot, so the queue then
        grows monotonically and a perfectly healthy connection is hard-closed
        with 1013. Measured: a client whose send costs three iterations
        overflowed and was closed after 64 of a 200-frame burst.

        So: wait for the writer to free a slot, bounded by `stall_grace`. A slow
        reader frees one as soon as its in-flight send completes and the frame
        goes in — the listener just runs in lock-step with the slowest writer
        for the length of the burst. A client that is not reading at all frees
        nothing, the wait times out, and it is closed exactly as before.
        """
        if self._overflowed:
            return
        try:
            self._queue.put_nowait(message)
            return
        except asyncio.QueueFull:
            pass

        if self._task is None or self._task.done():
            # No writer left to free a slot, so waiting would only stall the
            # shared listener for the whole grace period on a connection that
            # is already finished. The endpoint unsubscribes before it stops the
            # sender, so this is belt-and-braces for a writer that died on its
            # own (a socket that went away mid-send).
            return

        try:
            async with asyncio.timeout(self._stall_grace):
                await self._queue.put(message)
        except TimeoutError:
            self._declare_overflow()

    def _declare_overflow(self) -> None:
        """Mark this connection unrecoverable and close its socket."""
        if self._overflowed:
            return
        self._overflowed = True
        Logger.warning(
            "WebSocket consumer too far behind, closing to force resync: "
            "connection_id=%s pending=%d",
            self._connection_id,
            self._queue.qsize(),
        )
        # Closing is async and `offer()` must never await, so it runs in a
        # detached task. Cancelling the writer alone is NOT enough: it leaves
        # the socket open with a live receive loop and a dead data channel,
        # so the client keeps getting pong replies while receiving no
        # broadcasts at all — permanently, because offer()/deliver() return
        # early from here on. That is worse than the frame loss this design
        # rejects, because neither side can detect it.
        self._closer = asyncio.create_task(self._force_close())

    async def _force_close(self) -> None:
        """Cancel the writer and actually close the socket.

        `websocket.close()` makes uvicorn emit a close frame and, via its
        ws_close_timeout, drop the TCP connection even for a client that has
        stopped reading. `receive_text()` in the endpoint then raises
        WebSocketDisconnect, the receive loop breaks and the finally block runs
        the normal teardown.
        """
        if self._task is not None:
            self._task.cancel()
        try:
            await self._websocket.close(code=WS_CLOSE_TRY_AGAIN_LATER)
        except Exception as e:
            Logger.warning(
                "Failed to close overflowed WebSocket: connection_id=%s: %s",
                self._connection_id,
                str(e),
            )

    async def _run(self) -> None:
        while True:
            message = await self._queue.get()
            try:
                await self._websocket.send_json(message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # The socket is gone. Stop writing; the endpoint's finally block
                # unsubscribes and unregisters this connection.
                Logger.warning(
                    "WebSocket send failed, stopping sender: connection_id=%s: %s",
                    self._connection_id,
                    str(e),
                )
                return

    async def stop(self) -> None:
        # The closer is cancelled FIRST and unconditionally. This used to sit
        # below an `if self._task is None: return` short-circuit — a guard on
        # the wrong field: `offer()` creates a detached `_force_close` task
        # whenever the queue fills, and the queue can fill before `start()` ever
        # ran (or after the writer already died), so a `stop()` on a sender with
        # no writer returned early and left that closer task running detached
        # past teardown.
        closer, self._closer = self._closer, None
        if closer is not None:
            closer.cancel()
            try:
                await closer
            except BaseException:
                pass

        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except BaseException:
                # stop() runs from the endpoint's finally block. Anything
                # escaping here skips the registry unregister and the
                # connection-manager disconnect — a permanent leak. This
                # deliberately also swallows a CancelledError aimed at the
                # ENDPOINT task (server shutdown): finishing the teardown is
                # worth more than propagating the cancellation promptly.
                pass

        if self._overflowed:
            Logger.info(
                "WebSocket sender closed for falling behind: connection_id=%s",
                self._connection_id,
            )
