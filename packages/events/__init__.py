"""Durable event envelope and idempotency keys (roadmap §9, §10.4)."""

from packages.events.config import (
    ENVELOPE_VERSION,
    MAX_PAYLOAD_BYTES,
    MAX_PAYLOAD_KEYS,
    MAX_PAYLOAD_VALUE_CHARS,
    EventType,
    TrustLevel,
)
from packages.events.console_notify import (
    CHANNEL as CONSOLE_CHANNEL,
)
from packages.events.console_notify import (
    EVENT_INDEXING,
    EVENT_NOTIFICATIONS,
    decode_notify,
    encode_notify,
    notify_console,
)
from packages.events.envelope import EventEnvelope, PayloadError
from packages.events.idempotency import ActionType, idempotency_key, key_digest
from packages.events.publisher import (
    PublisherClient,
    PublishResult,
    publish,
    publish_async,
    topic_id,
    topic_path,
)
from packages.events.repo_events import (
    branch_from_ref,
    index_updated_event,
    project_repo_added_event,
    project_repo_removed_event,
    repo_push_event,
)

__all__ = [
    "CONSOLE_CHANNEL",
    "ENVELOPE_VERSION",
    "EVENT_INDEXING",
    "EVENT_NOTIFICATIONS",
    "MAX_PAYLOAD_BYTES",
    "MAX_PAYLOAD_KEYS",
    "MAX_PAYLOAD_VALUE_CHARS",
    "ActionType",
    "EventEnvelope",
    "EventType",
    "PayloadError",
    "PublishResult",
    "PublisherClient",
    "TrustLevel",
    "branch_from_ref",
    "decode_notify",
    "encode_notify",
    "idempotency_key",
    "index_updated_event",
    "key_digest",
    "notify_console",
    "project_repo_added_event",
    "project_repo_removed_event",
    "publish",
    "publish_async",
    "repo_push_event",
    "topic_id",
    "topic_path",
]
