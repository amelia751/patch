"""In-process fan-out from Postgres NOTIFY to dashboard SSE clients.

Each control-plane process LISTENs on `patchapi_console`. A write in the
indexer (or a notification update) NOTIFYs with a project id; this module
re-reads the snapshot and pushes it to every EventSource subscribed to that
project. Two API processes sharing Cloud SQL both hear the same NOTIFY, so a
local dashboard and a hosted one stay in step without competing on a Pub/Sub
subscription.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.events.console_notify import (
    CHANNEL,
    EVENT_INDEXING,
    EVENT_NOTIFICATIONS,
    decode_notify,
)
from packages.state.indexing import indexing_snapshot
from packages.state.notifications import notifications_snapshot

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator

    import asyncpg

log = logging.getLogger(__name__)

KEEPALIVE_SECONDS: Final[float] = 20.0
_QUEUE_SIZE: Final[int] = 32
_NOTIFICATION_LIMIT: Final[int] = 20

# Named SSE events the dashboard hook binds to. `snapshot` is the reconnect
# payload; the others are incremental.
SSE_SNAPSHOT: Final[str] = "snapshot"
SSE_INDEXING: Final[str] = "indexing"
SSE_NOTIFICATIONS: Final[str] = "notifications"


class ConsoleHub:
    """Per-process queues keyed by project. Not a network primitive."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[tuple[str, dict[str, Any]]]]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def subscribe(self, project_id: UUID) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    def unsubscribe(
        self, project_id: UUID, queue: asyncio.Queue[tuple[str, dict[str, Any]]]
    ) -> None:
        buckets = self._subscribers.get(project_id)
        if buckets is None:
            return
        buckets.discard(queue)
        if not buckets:
            del self._subscribers[project_id]

    def subscribed(self, project_id: UUID) -> bool:
        return bool(self._subscribers.get(project_id))

    def spawn(self, coro: Any) -> None:
        """Track a fan-out task so it is not garbage-collected mid-emit."""
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def publish(self, project_id: UUID, event: str, data: dict[str, Any]) -> None:
        """Enqueue for every subscriber. Drop the oldest item if a client lags."""
        for queue in list(self._subscribers.get(project_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                continue


def sse_bytes(event: str, data: dict[str, Any]) -> bytes:
    """One named SSE event. `data` is a JSON object, never a raw string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def keepalive_bytes() -> bytes:
    """Comment-frame keepalive. EventSource ignores it; proxies should not."""
    return b": keepalive\n\n"


async def snapshot_payload(pool: asyncpg.Pool, project_id: UUID) -> dict[str, Any]:
    """Indexing rollup plus the bell list, the document a reconnect starts from."""
    indexing = await indexing_snapshot(pool, project_id)
    notifications = await notifications_snapshot(pool, project_id, limit=_NOTIFICATION_LIMIT)
    return {"indexing": indexing, "notifications": notifications}


async def emit_from_notify(pool: asyncpg.Pool, hub: ConsoleHub, payload: str) -> None:
    """Re-read and push. No-op when nobody is listening or the payload is junk."""
    parsed = decode_notify(payload)
    if parsed is None:
        return
    event_type, project_id = parsed
    if not hub.subscribed(project_id):
        return
    try:
        if event_type == EVENT_INDEXING:
            data = await indexing_snapshot(pool, project_id)
            hub.publish(project_id, SSE_INDEXING, data)
        elif event_type == EVENT_NOTIFICATIONS:
            items = await notifications_snapshot(pool, project_id, limit=_NOTIFICATION_LIMIT)
            hub.publish(project_id, SSE_NOTIFICATIONS, {"notifications": items})
    except Exception:
        log.exception("console SSE emit failed for project %s", project_id)


async def project_event_stream(
    *,
    request_is_disconnected: Any,
    pool: asyncpg.Pool,
    hub: ConsoleHub,
    project_id: UUID,
    initial: dict[str, Any],
) -> AsyncIterator[bytes]:
    """Snapshot, then queue, then keepalives until the browser drops."""
    yield sse_bytes(SSE_SNAPSHOT, initial)
    queue = hub.subscribe(project_id)
    try:
        while True:
            if await request_is_disconnected():
                break
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield keepalive_bytes()
                continue
            yield sse_bytes(event, data)
    finally:
        hub.unsubscribe(project_id, queue)


async def listen_console(pool: asyncpg.Pool, hub: ConsoleHub) -> None:
    """Hold one connection on `LISTEN patchapi_console` until cancelled.

    A missing or unreachable database must not take the HTTP server down: the
    dashboard still serves, and the EventSource hook falls back to polling.
    """
    try:
        connection = await pool.acquire()
    except Exception:
        log.exception("console LISTEN could not acquire a connection")
        return

    def _on_notify(_connection: Any, _pid: int, _channel: str, payload: str) -> None:
        hub.spawn(emit_from_notify(pool, hub, payload))

    try:
        await connection.add_listener(CHANNEL, _on_notify)
        log.info("listening on %s for console SSE fan-out", CHANNEL)
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("console LISTEN stopped")
    finally:
        try:
            await connection.remove_listener(CHANNEL, _on_notify)
        except Exception:
            log.exception("console LISTEN could not drop its listener")
        try:
            await pool.release(connection)
        except Exception:
            log.exception("console LISTEN could not release its connection")


__all__ = [
    "KEEPALIVE_SECONDS",
    "SSE_INDEXING",
    "SSE_NOTIFICATIONS",
    "SSE_SNAPSHOT",
    "ConsoleHub",
    "emit_from_notify",
    "keepalive_bytes",
    "listen_console",
    "project_event_stream",
    "snapshot_payload",
    "sse_bytes",
]
