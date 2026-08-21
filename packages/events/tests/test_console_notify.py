"""Console NOTIFY payloads are a closed set and fail closed on junk."""

from uuid import UUID

import pytest

from packages.events.console_notify import (
    EVENT_CHANGES,
    EVENT_INDEXING,
    EVENT_NOTIFICATIONS,
    decode_notify,
    encode_notify,
)

PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")


def test_round_trip() -> None:
    payload = encode_notify(event_type=EVENT_INDEXING, project_id=PROJECT_ID)
    assert decode_notify(payload) == (EVENT_INDEXING, PROJECT_ID)


def test_notifications_type_is_distinct() -> None:
    payload = encode_notify(event_type=EVENT_NOTIFICATIONS, project_id=PROJECT_ID)
    assert decode_notify(payload) == (EVENT_NOTIFICATIONS, PROJECT_ID)


def test_changes_type_is_distinct() -> None:
    payload = encode_notify(event_type=EVENT_CHANGES, project_id=PROJECT_ID)
    assert decode_notify(payload) == (EVENT_CHANGES, PROJECT_ID)


def test_unknown_type_is_rejected_on_encode() -> None:
    with pytest.raises(ValueError, match="unknown console notify type"):
        encode_notify(event_type="index-updated", project_id=PROJECT_ID)


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not-json",
        "{}",
        '{"type":"indexing"}',
        '{"type":"indexing","project_id":"not-a-uuid"}',
        '{"type":"index-updated","project_id":"33333333-3333-4333-8333-333333333333"}',
        "[]",
    ],
)
def test_junk_decodes_to_none(payload: str) -> None:
    assert decode_notify(payload) is None
