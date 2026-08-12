"""Durable event envelope and idempotency keys (roadmap §9, §10.4)."""

from packages.events.config import (
    ENVELOPE_VERSION,
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_KEYS,
    MAX_PAYLOAD_VALUE_CHARS,
    EventType,
    TrustLevel,
)
from packages.events.envelope import EventEnvelope, PayloadError
from packages.events.idempotency import ActionType, idempotency_key, key_digest

__all__ = [
    "ENVELOPE_VERSION",
    "MAX_PAYLOAD_BYTES",
    "MAX_PAYLOAD_KEYS",
    "MAX_PAYLOAD_VALUE_CHARS",
    "ActionType",
    "EventEnvelope",
    "EventType",
    "PayloadError",
    "TrustLevel",
    "idempotency_key",
    "key_digest",
]
