"""Pub/Sub transport for the indexer worker (`repo-indexer.md` §5.6).

The handlers in `worker.py` are the state machine; this module is the wire it
sits behind, and it owns exactly three decisions:

1. **Names are derived, never typed.** A subscription is `{topic}-sub`, and the
   topic is `{prefix}-{event-type}` — the same rule `packages.events.publisher`
   publishes by and `infra/terraform/modules/eventing` provisions by. A worker
   cannot listen on a subscription nobody creates.
2. **Ack means handled.** A message is acknowledged only after its handler
   committed. Anything else — an unparseable envelope, an unreachable database,
   a failed index — nacks, so Pub/Sub redelivers and, after the subscription's
   bounded attempts, dead-letters it for a human. Handlers are idempotent by
   construction (upsert on the inventory key, idempotency keys on the events),
   which is what makes at-least-once delivery safe to lean on.
3. **The GCP client is imported lazily.** The handlers must be unit-testable
   with no `google-cloud-pubsub` installed and no broker reachable, so nothing
   at import time touches it.

`CHANGE_NORMALIZED` is deliberately not in the default subscription set even
though `worker.handle_manifest` serves it: the agent fleet consumes that same
subscription, and two different services pulling one subscription would split
the manifests between them at random. The indexer answers manifest queries
through `worker.handle_manifest` when a caller asks it to, and a deployment that
gives the indexer its own manifest subscription can pass it here explicitly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Final, Protocol

from packages.events.config import EventType
from packages.events.envelope import EventEnvelope
from packages.events.publisher import gcp_project, topic_id
from patchapi_repo_indexer import worker
from patchapi_repo_indexer.config import PUBSUB_PROJECT

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    import asyncpg

log = logging.getLogger(__name__)

# The lifecycle events this worker owns end to end. Repository membership and
# pushes have exactly one consumer — this service — so nothing competes for
# them.
SUBSCRIBED_EVENTS: Final[tuple[EventType, ...]] = (
    EventType.PROJECT_REPO_ADDED,
    EventType.PROJECT_REPO_REMOVED,
    EventType.REPO_PUSH,
)

# A full index of a large repository is a clone, a scan, and a write. The
# streaming pull manager extends the lease while a callback runs; this bound is
# the point at which the work is presumed wedged and the message is returned to
# the subscription instead of being held forever.
HANDLER_TIMEOUT_SECONDS: Final[float] = 900.0

# Each in-flight message can hold a checkout on disk, so concurrency is capped
# well below the client default of a thousand.
MAX_CONCURRENT_MESSAGES: Final[int] = 4


class PubsubMessage(Protocol):
    """The three members of `pubsub_v1.subscriber.message.Message` used here."""

    @property
    def data(self) -> bytes: ...

    def ack(self) -> None: ...

    def nack(self) -> None: ...


class SubscriberClient(Protocol):
    """The subscribe/close surface of `pubsub_v1.SubscriberClient`."""

    def subscribe(self, subscription: str, callback: Any, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


def subscription_id(event_type: EventType, env: dict[str, str] | None = None) -> str:
    """Return the pull subscription for an event type, e.g. `patchapi-dev-repo-push-sub`."""
    return f"{topic_id(event_type, env)}-sub"


def subscription_path(event_type: EventType, env: dict[str, str] | None = None) -> str:
    """Return the fully qualified subscription this worker pulls from."""
    project = gcp_project(env) or PUBSUB_PROJECT
    return f"projects/{project}/subscriptions/{subscription_id(event_type, env)}"


async def handle_message(
    pool: asyncpg.Pool,
    data: bytes,
    *,
    effects: worker.Effects = worker.DEFAULT_EFFECTS,
) -> worker.HandlerResult | worker.ManifestResult | None:
    """Decode one message and run its handler on a pooled connection.

    Raises on anything that leaves the message unhandled. The caller turns that
    into a nack; deciding here would hide a failed index behind a log line.
    """
    envelope = EventEnvelope.from_json(data.decode("utf-8"))
    async with pool.acquire() as conn:
        return await worker.dispatch(conn, envelope, effects=effects)


def _callback(
    loop: asyncio.AbstractEventLoop,
    pool: asyncpg.Pool,
    effects: worker.Effects,
) -> Any:
    """Bridge the client's callback thread to the handlers' event loop.

    The client delivers on its own threads and the handlers are async, so the
    coroutine is scheduled onto the loop and the thread blocks on its result.
    Blocking is the point: the message stays leased until the work is done, and
    the ack that follows means the transaction committed.
    """

    def on_message(message: PubsubMessage) -> None:
        task = asyncio.run_coroutine_threadsafe(
            handle_message(pool, message.data, effects=effects), loop
        )
        try:
            outcome = task.result(timeout=HANDLER_TIMEOUT_SECONDS)
        except Exception as exc:
            # Deliberately broad: a malformed envelope, an unreachable database
            # and a failed index are one fact to the transport — this message
            # was not handled, so it must not be acknowledged.
            log.warning("event not handled, returning it to the subscription: %s", exc)
            message.nack()
            return
        log.info("handled event: %s", outcome)
        message.ack()

    return on_message


def _client() -> SubscriberClient:
    from google.cloud import pubsub_v1

    return pubsub_v1.SubscriberClient()


def _flow_control() -> Any:
    from google.cloud.pubsub_v1.types import FlowControl

    return FlowControl(max_messages=MAX_CONCURRENT_MESSAGES)


async def run(
    *,
    events: tuple[EventType, ...] = SUBSCRIBED_EVENTS,
    pool: asyncpg.Pool | None = None,
    client: SubscriberClient | None = None,
    effects: worker.Effects = worker.DEFAULT_EFFECTS,
) -> None:
    """Pull the worker's subscriptions until cancelled.

    Owns the resources it opened and no others: a pool or a client passed in is
    left to its caller to close, which is what lets a test drive one iteration
    without tearing down its own fixtures.
    """
    from packages.state.pool import create_pool

    if gcp_project() is None:
        # Publishing reads the environment separately from subscribing, so a
        # worker can be pulling correctly while every `index-updated` fan-out is
        # dropped. Say so at startup rather than once per push.
        log.warning(
            "no GCP project configured for publishing; index-updated events will not be sent"
        )

    loop = asyncio.get_running_loop()
    owns_pool = pool is None
    owns_client = client is None
    pool = pool if pool is not None else await create_pool()
    subscriber = client if client is not None else _client()

    streams = []
    try:
        for event_type in events:
            path = subscription_path(event_type)
            streams.append(
                subscriber.subscribe(
                    path,
                    callback=_callback(loop, pool, effects),
                    flow_control=_flow_control(),
                )
            )
            log.info("subscribed: %s", path)
        await asyncio.Event().wait()
    finally:
        for stream in streams:
            stream.cancel()
        if owns_client:
            subscriber.close()
        if owns_pool:
            await pool.close()


def main() -> int:
    """Run the subscriber until interrupted."""
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "HANDLER_TIMEOUT_SECONDS",
    "MAX_CONCURRENT_MESSAGES",
    "SUBSCRIBED_EVENTS",
    "PubsubMessage",
    "SubscriberClient",
    "handle_message",
    "main",
    "run",
    "subscription_id",
    "subscription_path",
]
