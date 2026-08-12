"""The envelope every PatchAPI Pub/Sub message travels in (roadmap §10.4).

Two properties matter and both are enforced at construction rather than left to
a convention:

1. A message carries IDs and URIs, never repository source code. Payload values
   are bounded scalars, so a subscriber cannot receive a diff that skipped the
   artifact store — and an agent prompt cannot be fed source that never passed
   through policy.
2. Every message states the provenance of the material it refers to. Provider
   text is untrusted at the point it enters the system and stays labelled.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, Self

from packages.events.config import (
    ALLOWED_PAYLOAD_SCALARS,
    ENVELOPE_VERSION,
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_KEYS,
    MAX_PAYLOAD_VALUE_CHARS,
    EventType,
    TrustLevel,
)

_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {"envelope_version", "event_type", "event_id", "run_id", "occurred_at", "trust", "payload"}
)


class PayloadError(ValueError):
    """The payload carries something an event is not allowed to carry."""


def _check_value(key: str, value: Any) -> None:
    if isinstance(value, ALLOWED_PAYLOAD_SCALARS):
        if isinstance(value, str) and len(value) > MAX_PAYLOAD_VALUE_CHARS:
            raise PayloadError(
                f"payload field {key!r} is {len(value)} characters; events carry references, "
                f"not content (limit {MAX_PAYLOAD_VALUE_CHARS}). Store it and send its URI."
            )
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            if not isinstance(item, ALLOWED_PAYLOAD_SCALARS):
                raise PayloadError(
                    f"payload field {key!r} contains a {type(item).__name__}; "
                    "lists may hold scalars only"
                )
            if isinstance(item, str) and len(item) > MAX_PAYLOAD_VALUE_CHARS:
                raise PayloadError(f"payload field {key!r} contains an oversized string")
        return
    raise PayloadError(
        f"payload field {key!r} is a {type(value).__name__}; payloads are flat maps of "
        "scalars or lists of scalars"
    )


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """One durable workflow event.

    `occurred_at` is supplied by the caller rather than read from the clock
    here, so an envelope is a pure function of its inputs and a replayed run
    reconstructs the same message.
    """

    event_type: EventType
    event_id: str
    run_id: str
    occurred_at: str
    trust: TrustLevel
    payload: Mapping[str, Any]
    envelope_version: str = ENVELOPE_VERSION
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if self.envelope_version != ENVELOPE_VERSION:
            raise ValueError(
                f"envelope is pinned at version {ENVELOPE_VERSION}, got {self.envelope_version!r}"
            )
        for field_name in ("event_id", "run_id", "occurred_at"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must not be empty")
        if len(self.payload) > MAX_PAYLOAD_KEYS:
            raise PayloadError(
                f"payload has {len(self.payload)} fields; the limit is {MAX_PAYLOAD_KEYS}"
            )
        for key, value in self.payload.items():
            if not isinstance(key, str):
                raise PayloadError(f"payload keys must be strings, got {type(key).__name__}")
            _check_value(key, value)

        encoded = json.dumps(dict(self.payload), sort_keys=True).encode("utf-8")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise PayloadError(
                f"payload serializes to {len(encoded)} bytes; the limit is {MAX_PAYLOAD_BYTES}"
            )

    @property
    def is_untrusted(self) -> bool:
        """True when the referenced material came from outside the enterprise."""
        return self.trust is TrustLevel.UNTRUSTED_PROVIDER_INPUT

    def with_idempotency_key(self, key: str) -> Self:
        return replace(self, idempotency_key=key)

    def to_dict(self) -> dict[str, Any]:
        record = {
            "envelope_version": self.envelope_version,
            "event_type": self.event_type.value,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "occurred_at": self.occurred_at,
            "trust": self.trust.value,
            "payload": dict(self.payload),
        }
        if self.idempotency_key is not None:
            record["idempotency_key"] = self.idempotency_key
        return record

    def to_json(self) -> str:
        """Serialize with sorted keys so the same event is the same bytes."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> Self:
        missing = _REQUIRED_KEYS - set(record)
        if missing:
            raise ValueError(f"event is missing required fields: {sorted(missing)}")
        unknown = set(record) - _REQUIRED_KEYS - {"idempotency_key"}
        if unknown:
            # An unexpected key means a publisher and a subscriber disagree
            # about the envelope, which is an error rather than something to
            # carry along silently.
            raise ValueError(f"event carries unknown fields: {sorted(unknown)}")
        return cls(
            event_type=EventType(record["event_type"]),
            event_id=record["event_id"],
            run_id=record["run_id"],
            occurred_at=record["occurred_at"],
            trust=TrustLevel(record["trust"]),
            payload=dict(record["payload"]),
            envelope_version=record["envelope_version"],
            idempotency_key=record.get("idempotency_key"),
        )

    @classmethod
    def from_json(cls, raw: str) -> Self:
        return cls.from_dict(json.loads(raw))
