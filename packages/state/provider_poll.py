"""Detect provider-side change and announce it. Nothing more.

Google publishes no webhook for a model retirement, so the boundary has to be
polled (roadmap §10.5). The mistake to avoid is letting the poller also *do* the
work: that produces a batch job with one hardcoded consumer, and a second
consumer — the Change Intelligence agent, a notifier, an audit sink — has
nowhere to attach.

So this module checks each surface, diffs against what the last poll concluded,
and publishes one `provider-change-detected` per transition. Recording the
consequence, writing an undocumented retirement, and reclassifying affected
projects all happen in subscribers.

Publishing transitions rather than state is what makes a short interval
affordable. "Still 404" every fifteen minutes is not news and costs a message;
`resolves → not_found` is news and is rare. A steady state emits nothing and
costs two listing calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from packages.events.config import EventType
from packages.events.provider_events import (
    TRANSITION_APPEARED,
    TRANSITION_RESTORED,
    TRANSITION_RETIRED,
    provider_change_detected_event,
)
from packages.events.publisher import publish_async
from packages.providers.google.live import LiveResult, LiveStatus

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

DEFAULT_PROVIDER: Final[str] = "google"

# No stored answer yet. Distinct from `unknown`, which means we asked and the
# call failed: a first observation of `not_found` is a real retirement we have
# simply never seen before, and it has to be announced.
NO_PREVIOUS: Final[str] = "absent"

# Driven off inventory rather than off the watchlist: the point is to catch a
# model that died without anyone writing it down, which by definition is not in
# a note yet.
_INDEXED_IDENTIFIERS_SQL: Final[str] = """
SELECT DISTINCT identifier FROM provider_usages WHERE provider = $1
"""


@dataclass(frozen=True, slots=True)
class Transition:
    """One identifier changed state on one surface between two polls."""

    identifier: str
    surface: str
    previous_status: str
    current_status: str
    transition: str
    source_url: str
    checked_at: str


def classify_transition(previous: str, current: LiveStatus) -> str | None:
    """Name the transition between two answers, or `None` if nothing happened.

    `unknown` is never a transition in either direction. Arriving at it means the
    check did not run, and leaving it means the check finally ran — neither is a
    change in what the provider serves.
    """
    if current is LiveStatus.UNKNOWN:
        return None
    settled = previous in {LiveStatus.RESOLVES.value, LiveStatus.NOT_FOUND.value}
    if current is LiveStatus.NOT_FOUND:
        if previous == LiveStatus.NOT_FOUND.value:
            return None
        return TRANSITION_RETIRED
    if previous == LiveStatus.RESOLVES.value:
        return None
    return TRANSITION_RESTORED if settled else TRANSITION_APPEARED


def detect_transitions(
    previous: dict[tuple[str, str], str], results: tuple[LiveResult, ...]
) -> list[Transition]:
    """Diff this poll against the last one."""
    transitions: list[Transition] = []
    for result in results:
        was = previous.get((result.identifier, result.surface), NO_PREVIOUS)
        name = classify_transition(was, result.status)
        if name is None:
            continue
        transitions.append(
            Transition(
                identifier=result.identifier,
                surface=result.surface,
                previous_status=was,
                current_status=str(result.status),
                transition=name,
                source_url=result.source_url,
                checked_at=result.checked_at,
            )
        )
    return transitions


async def announce(
    transitions: list[Transition], *, provider: str
) -> tuple[list[str], set[tuple[str, str]]]:
    """Publish one event per transition.

    Returns the event ids that reached the topic and the `(identifier, surface)`
    pairs whose announcement did not. A publish failure is logged by the
    publisher and reported here rather than raised, because the caller has to
    know which liveness rows it must not commit yet.
    """
    occurred_at = datetime.now(UTC).isoformat(timespec="seconds")
    published: list[str] = []
    failed: set[tuple[str, str]] = set()
    for change in transitions:
        envelope = provider_change_detected_event(
            provider=provider,
            identifier=change.identifier,
            surface=change.surface,
            transition=change.transition,
            previous_status=change.previous_status,
            current_status=change.current_status,
            source_url=change.source_url,
            checked_at=change.checked_at,
            occurred_at=occurred_at,
        )
        result = await publish_async(envelope)
        if result.published:
            published.append(envelope.event_id)
            log.info(
                "published %s %s %s -> %s",
                EventType.PROVIDER_CHANGE_DETECTED.value,
                change.identifier,
                change.previous_status,
                change.current_status,
            )
        else:
            failed.add((change.identifier, change.surface))
    return published, failed


@dataclass(frozen=True, slots=True)
class PollOutcome:
    """What one poll observed and announced.

    `results` is carried so the caller can reuse the answers instead of asking
    the surface a second time.
    """

    provider: str
    results: tuple[LiveResult, ...]
    transitions: tuple[Transition, ...]
    published: tuple[str, ...]


async def poll_provider(
    connection: asyncpg.Connection, *, provider: str = DEFAULT_PROVIDER
) -> PollOutcome:
    """Check, diff, announce, then record. In that order, deliberately.

    Recording before announcing would lose events: the stored status is the only
    memory of what the last poll concluded, so committing `not_found` and then
    failing to publish leaves the next poll seeing no change at all, and the
    retirement is never announced by anyone. Publishing first makes the pipeline
    at-least-once — a message can be delivered twice, which subscribers already
    handle through the idempotency key — instead of at-most-once, which silently
    drops the one event that mattered.
    """
    from packages.providers.google.live import live_identifiers
    from packages.providers.sdk import is_sdk_identifier, live_packages
    from packages.state.findings import previous_live_statuses, record_live_results

    previous = await previous_live_statuses(connection, provider=provider)
    rows = await connection.fetch(_INDEXED_IDENTIFIERS_SQL, provider)
    identifiers = [str(row["identifier"]) for row in rows]
    if not identifiers:
        log.info("the index names no %s identifiers; nothing to poll", provider)
        return PollOutcome(provider=provider, results=(), transitions=(), published=())

    # Two surfaces, one diff. A model is asked of the publisher's listing and a
    # package of its registry, but "stopped resolving" means the same thing for
    # both, so the transition machinery downstream does not care which it was.
    models = [item for item in identifiers if not is_sdk_identifier(item)]
    sdks = [item for item in identifiers if is_sdk_identifier(item)]
    results = await live_identifiers(models) if models else ()
    results += await live_packages(sdks)
    transitions = detect_transitions(previous, results)
    for change in transitions:
        log.info(
            "%s %-9s %s -> %s",
            change.transition,
            change.surface,
            change.identifier,
            change.current_status,
        )
    if not transitions:
        log.info("no provider transitions; nothing announced")

    published, failed = await announce(transitions, provider=provider)
    for identifier, surface in sorted(failed):
        log.warning(
            "holding back the liveness row for %s on %s; the next poll retries it",
            identifier,
            surface,
        )
    recordable = tuple(
        result for result in results if (result.identifier, result.surface) not in failed
    )
    await record_live_results(connection, recordable, provider=provider)

    return PollOutcome(
        provider=provider,
        results=results,
        transitions=tuple(transitions),
        published=tuple(published),
    )


__all__ = [
    "DEFAULT_PROVIDER",
    "NO_PREVIOUS",
    "PollOutcome",
    "Transition",
    "announce",
    "classify_transition",
    "detect_transitions",
    "poll_provider",
]
