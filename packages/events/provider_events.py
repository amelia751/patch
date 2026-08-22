"""Envelopes for the provider lifecycle (roadmap §10.4, §10.5).

Google sends no webhook when a model dies, so the boundary is polled. What the
poller must not do is *act* on what it finds: it detects a delta and publishes
`provider-change-detected`, and every reaction — recording the transition,
writing an undocumented retirement, asking Change Intelligence to explain it,
reclassifying the projects that call the identifier — is a subscriber. That is
the difference between a batch job and a pipeline, and it is what lets a second
consumer attach without touching the first.

A transition is published, never a state. "Still 404" every fifteen minutes is
not news; `resolves → not_found` is. `checked_at` is part of the identity so a
model that flaps produces two events rather than one collapsed one, while a
redelivery of the same message reduces to the same key.

Provider material is untrusted at the point it enters the system (constraint 4)
and the envelope says so, so a subscriber cannot lose track of where a claim
came from.
"""

from __future__ import annotations

from typing import Final

from packages.events.config import EventType, TrustLevel
from packages.events.envelope import EventEnvelope
from packages.events.ids import digest as _digest
from packages.events.ids import slug as _slug

_PROVIDER_TRUST: Final[TrustLevel] = TrustLevel.UNTRUSTED_PROVIDER_INPUT

# What changed about an identifier between two polls. `RETIRED` is the one that
# costs a customer money; the others exist so a subscriber can correct itself
# rather than only ever escalating.
TRANSITION_RETIRED: Final[str] = "retired"
TRANSITION_RESTORED: Final[str] = "restored"
TRANSITION_APPEARED: Final[str] = "appeared"

TRANSITIONS: Final[frozenset[str]] = frozenset(
    {TRANSITION_RETIRED, TRANSITION_RESTORED, TRANSITION_APPEARED}
)


def provider_change_detected_event(
    *,
    provider: str,
    identifier: str,
    surface: str,
    transition: str,
    previous_status: str,
    current_status: str,
    source_url: str,
    checked_at: str,
    occurred_at: str,
) -> EventEnvelope:
    """One identifier changed state on one surface.

    Published only on a transition. A poll that confirms yesterday's answer
    publishes nothing, which is what makes polling every fifteen minutes
    affordable instead of every six hours.
    """
    if transition not in TRANSITIONS:
        raise ValueError(
            f"unknown transition {transition!r}; expected one of {sorted(TRANSITIONS)}"
        )
    key = f"provider-change-detected:{provider}:{surface}:{identifier}:{transition}:{checked_at}"
    return EventEnvelope(
        event_type=EventType.PROVIDER_CHANGE_DETECTED,
        event_id=_digest(
            "provider-change-detected", provider, surface, identifier, transition, checked_at
        ),
        run_id=f"provider-{_slug(provider)}-{_slug(identifier)}-{_digest(checked_at)[:8]}",
        occurred_at=occurred_at,
        trust=_PROVIDER_TRUST,
        payload={
            "provider": provider,
            "identifier": identifier,
            "surface": surface,
            "transition": transition,
            "previous_status": previous_status,
            "current_status": current_status,
            "source_url": source_url,
            "checked_at": checked_at,
        },
    ).with_idempotency_key(key)


def change_normalized_event(
    *,
    provider: str,
    external_id: str,
    identifier: str,
    origin: str,
    occurred_at: str,
) -> EventEnvelope:
    """A change event now exists for this identifier, so projects can be rejoined.

    `origin` records which lane wrote it — the deterministic subscriber or the
    Change Intelligence agent. Both may publish: the deterministic lane sets the
    status a finding gets, the agent later adds rationale and a proposed
    replacement, and each is a legitimate reason to refresh the projects that
    call the identifier.
    """
    key = f"change-normalized:{provider}:{external_id}:{origin}"
    return EventEnvelope(
        event_type=EventType.CHANGE_NORMALIZED,
        event_id=_digest("change-normalized", provider, external_id, origin),
        run_id=f"normalized-{_slug(provider)}-{_slug(external_id)}",
        occurred_at=occurred_at,
        trust=_PROVIDER_TRUST,
        payload={
            "provider": provider,
            "external_id": external_id,
            "identifier": identifier,
            "origin": origin,
        },
    ).with_idempotency_key(key)


__all__ = [
    "TRANSITIONS",
    "TRANSITION_APPEARED",
    "TRANSITION_RESTORED",
    "TRANSITION_RETIRED",
    "change_normalized_event",
    "provider_change_detected_event",
]
