"""Best-effort publication of envelopes to Pub/Sub (roadmap §10.4).

Two properties this module exists to guarantee:

1. **Topic names are derived, never typed at a call site.** One topic per
   `EventType`, named `{prefix}-{event-type}`, so a publisher cannot invent a
   topic nobody subscribes to and a deployment can namespace its topics by
   environment without editing code.
2. **A publish failure is reported, never raised.** The webhook receiver and the
   console write rows to authoritative Postgres first; Pub/Sub is how a worker
   is told to look. Losing GCP must not turn an accepted push into a 500 or roll
   back a repository the user just imported. Every failure leaves a structured
   log line naming the topic and the event, which is what an operator replays
   from.

`google-cloud-pubsub` is imported inside `publish` rather than at module import.
This package is standard-library-only by design — a sandbox publisher and the
envelope tests must not need the GCP client — and the import is the thing that
fails when the dependency is absent, which is exactly the fail-soft path below.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol

from packages.events.config import EventType

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    from packages.events.envelope import EventEnvelope

TOPIC_PREFIX_VAR: Final[str] = "PATCHAPI_PUBSUB_TOPIC_PREFIX"
DEFAULT_TOPIC_PREFIX: Final[str] = "patchapi-dev"

# Checked in order. `GCP_PROJECT` is what `.env.example` sets;
# `GOOGLE_CLOUD_PROJECT` is what the GCP client libraries and Cloud Run set.
PROJECT_VARS: Final[tuple[str, ...]] = ("GCP_PROJECT", "GOOGLE_CLOUD_PROJECT")

# A webhook has roughly ten seconds before GitHub calls the delivery failed, and
# the response is sent after this returns. Waiting longer than the caller can
# afford converts a recoverable publish failure into a redelivery storm.
PUBLISH_TIMEOUT_SECONDS: Final[float] = 5.0

log = logging.getLogger(__name__)


class PublisherClient(Protocol):
    """The one method this module uses from `pubsub_v1.PublisherClient`."""

    def publish(self, topic: str, data: bytes, **attributes: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What happened to one publish attempt.

    `published=False` is a normal outcome, not an exception in disguise: the
    caller decides whether to degrade (a webhook still returns 202) or to
    surface it, and `reason` is what it reports.
    """

    event_type: EventType
    event_id: str
    topic: str
    published: bool
    message_id: str | None = None
    reason: str | None = None


def topic_prefix(env: dict[str, str] | None = None) -> str:
    """Return the environment's topic namespace."""
    environ = os.environ if env is None else env
    return environ.get(TOPIC_PREFIX_VAR, "").strip() or DEFAULT_TOPIC_PREFIX


def topic_id(event_type: EventType, env: dict[str, str] | None = None) -> str:
    """Return the short topic name for an event type, e.g. `patchapi-dev-repo-push`."""
    return f"{topic_prefix(env)}-{EventType(event_type).value}"


def gcp_project(env: dict[str, str] | None = None) -> str | None:
    """Return the configured GCP project, or `None` when nothing names one."""
    environ = os.environ if env is None else env
    for name in PROJECT_VARS:
        value = environ.get(name, "").strip()
        if value:
            return value
    return None


def topic_path(event_type: EventType, env: dict[str, str] | None = None) -> str | None:
    """Return the fully qualified topic, or `None` if no project is configured."""
    project = gcp_project(env)
    if project is None:
        return None
    return f"projects/{project}/topics/{topic_id(event_type, env)}"


def _log_failure(result: PublishResult) -> None:
    """Emit the line an operator replays from. Payloads are never logged.

    Payload values are IDs and URIs by construction, but a log sink is a
    different trust boundary from a Pub/Sub topic, so only the routing facts
    cross it.
    """
    log.warning(
        "event publish failed: %s",
        json.dumps(
            {
                "event": "pubsub_publish_failed",
                "event_type": result.event_type.value,
                "event_id": result.event_id,
                "topic": result.topic,
                "reason": result.reason,
            },
            sort_keys=True,
        ),
    )


def _client() -> PublisherClient:
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def publish(
    envelope: EventEnvelope,
    *,
    client: PublisherClient | None = None,
    timeout: float = PUBLISH_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> PublishResult:
    """Publish one envelope, returning whether it landed. Never raises.

    Blocking: it waits for the broker to acknowledge, because "published" has to
    mean the message exists somewhere other than this process's memory. Call
    `publish_async` from an event loop.
    """
    event_type = EventType(envelope.event_type)
    target = topic_path(event_type, env)
    if target is None:
        result = PublishResult(
            event_type=event_type,
            event_id=envelope.event_id,
            topic=topic_id(event_type, env),
            published=False,
            reason=f"no GCP project configured; set one of {', '.join(PROJECT_VARS)}",
        )
        _log_failure(result)
        return result

    try:
        publisher = client if client is not None else _client()
        future = publisher.publish(target, envelope.to_json().encode("utf-8"))
        message_id = str(future.result(timeout=timeout))
    except Exception as exc:
        # Deliberately broad: an unreachable broker, a missing dependency, a
        # denied IAM binding, and an expired credential are all the same fact to
        # the caller — the message is not on the topic.
        result = PublishResult(
            event_type=event_type,
            event_id=envelope.event_id,
            topic=target,
            published=False,
            reason=f"{type(exc).__name__}: {exc}",
        )
        _log_failure(result)
        return result

    return PublishResult(
        event_type=event_type,
        event_id=envelope.event_id,
        topic=target,
        published=True,
        message_id=message_id,
    )


async def publish_async(
    envelope: EventEnvelope,
    *,
    client: PublisherClient | None = None,
    timeout: float = PUBLISH_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> PublishResult:
    """`publish` off the event loop, so an ASGI handler is not blocked by the broker."""
    return await asyncio.to_thread(publish, envelope, client=client, timeout=timeout, env=env)


__all__ = [
    "DEFAULT_TOPIC_PREFIX",
    "PROJECT_VARS",
    "PUBLISH_TIMEOUT_SECONDS",
    "TOPIC_PREFIX_VAR",
    "PublishResult",
    "PublisherClient",
    "gcp_project",
    "publish",
    "publish_async",
    "topic_id",
    "topic_path",
    "topic_prefix",
]
