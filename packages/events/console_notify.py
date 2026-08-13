"""Postgres NOTIFY payloads for the dashboard console stream.

Pub/Sub stays service-to-service. The browser never holds a subscriber. Local
and hosted control-plane processes share Cloud SQL, so LISTEN/NOTIFY is how
every API instance fans the same write out to its own SSE clients. A shared
Pub/Sub subscription would be a competing consumer: one process would see
`index-updated` and the other would not.

The payload is a wake-up, not a snapshot. Receivers re-read Postgres so a
stale percentage cannot ride the notify.
"""

from __future__ import annotations

import json
from typing import Any, Final
from uuid import UUID

CHANNEL: Final[str] = "patchapi_console"
EVENT_INDEXING: Final[str] = "indexing"
EVENT_NOTIFICATIONS: Final[str] = "notifications"

_EVENT_TYPES: Final[frozenset[str]] = frozenset({EVENT_INDEXING, EVENT_NOTIFICATIONS})


def encode_notify(*, event_type: str, project_id: UUID | str) -> str:
    """Encode a wake-up. Raises if the event type is not one the console handles."""
    if event_type not in _EVENT_TYPES:
        raise ValueError(f"unknown console notify type: {event_type}")
    return json.dumps(
        {"type": event_type, "project_id": str(project_id)},
        separators=(",", ":"),
    )


def decode_notify(payload: str) -> tuple[str, UUID] | None:
    """Return `(event_type, project_id)` or `None` if the payload is not ours."""
    try:
        body = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    event_type = body.get("type")
    raw_id = body.get("project_id")
    if event_type not in _EVENT_TYPES or not isinstance(raw_id, str) or not raw_id:
        return None
    try:
        return event_type, UUID(raw_id)
    except ValueError:
        return None


async def notify_console(connection: Any, *, event_type: str, project_id: UUID | str) -> None:
    """`NOTIFY` every listener on `CHANNEL`. The caller owns the connection."""
    await connection.execute(
        "SELECT pg_notify($1, $2)",
        CHANNEL,
        encode_notify(event_type=event_type, project_id=project_id),
    )


__all__ = [
    "CHANNEL",
    "EVENT_INDEXING",
    "EVENT_NOTIFICATIONS",
    "decode_notify",
    "encode_notify",
    "notify_console",
]
