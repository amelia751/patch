"""Notification row mapping and Need-you projection, without a database."""

from packages.state.notifications import (
    RUN_WAITING_KEY,
    RUN_WAITING_MESSAGE,
    RUN_WAITING_TITLE,
    change_dedupe_key,
    change_notification_payload,
    public_notification,
    run_waiting_payload,
)


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


def test_change_notification_uses_finding_copy() -> None:
    card = change_notification_payload(
        {
            "external_id": "imagen4-retirement-2026-08-17",
            "title": "Imagen 4 retirement",
            "summary": "Imagen 4 generate models stop resolving.",
            "kind": "deprecation",
            "product": "Imagen",
            "replacements": [{"to": "gemini-3.1-flash-image"}],
            "file_hits": 47,
            "file_count": 14,
            "repos": ["amelia751/egaki"],
        }
    )
    assert card["dedupe_key"] == change_dedupe_key("imagen4-retirement-2026-08-17")
    assert card["title"] == "Imagen 4 retirement"
    assert card["actions"][0]["action_type"] == "view_changes"
    assert card["metadata"]["kind"] == "deprecation"
    assert card["metadata"]["tags"][0]["label"] == "Needs you"
    assert card["metadata"]["tags"][1]["label"] == "Deprecation"


def test_run_waiting_notification_is_the_dual_cta() -> None:
    card = run_waiting_payload()
    assert card["dedupe_key"] == RUN_WAITING_KEY
    assert card["title"] == RUN_WAITING_TITLE
    assert card["message"] == RUN_WAITING_MESSAGE
    assert [action["action_type"] for action in card["actions"]] == [
        "connect_gcp",
        "add_secret",
    ]
