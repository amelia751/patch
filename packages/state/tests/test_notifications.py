"""Notification row mapping, without a database."""

from packages.state.notifications import public_notification


def test_public_notification_maps_kind_to_type() -> None:
    mapped = public_notification(
        {
            "id": "5eedda7a-0007-4000-8000-000000000001",
            "project_id": "5eedda7a-0004-4000-8000-000000000001",
            "kind": "info",
            "title": "Imported",
            "message": "egaki is ready to review",
            "priority": "normal",
            "read_at": None,
            "dismissed_at": None,
            "details": None,
            "questions": None,
            "actions": [],
            "contract_ids": [],
            "source_commit": None,
            "metadata": {},
            "created_at": None,
        }
    )
    assert mapped["type"] == "info"
    assert mapped["read"] is False
    assert mapped["dismissed"] is False
    assert mapped["title"] == "Imported"
