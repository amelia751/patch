"""Every way this lane declines, and the one way it writes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from patchapi_agent_runner import runner

from packages.events.config import EventType, TrustLevel
from packages.events.envelope import EventEnvelope
from packages.schemas.change_manifest import ChangeManifest

OCCURRED_AT = "2026-08-22T12:00:00+00:00"
EXTERNAL_ID = "imagen4-retirement-2026-08-17"
IDENTIFIER = "imagen-4.0-generate-001"


def normalized(*, external_id: str = EXTERNAL_ID, origin: str = "deterministic") -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.CHANGE_NORMALIZED,
        event_id="normalized-1",
        run_id="run-1",
        occurred_at=OCCURRED_AT,
        trust=TrustLevel.UNTRUSTED_PROVIDER_INPUT,
        payload={
            "provider": "google",
            "external_id": external_id,
            "affected_identifiers": [IDENTIFIER],
            "origin": origin,
        },
    )


class RecordingConnection:
    """Fails the test if the lane touches the database when it should not."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.rows: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        self.rows.append((query, args))
        return {"external_id": EXTERNAL_ID, "id": "00000000-0000-0000-0000-000000000001"}

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        # No project subscribes in these tests, so the impact pass has nothing
        # to assess and the corpus write is what is under examination.
        return []


@pytest.fixture
def feed(tmp_path: Path) -> Path:
    (tmp_path / "notice.json").write_text(
        json.dumps({"change_id": EXTERNAL_ID, "provider": "google"}), encoding="utf-8"
    )
    return tmp_path


def test_a_notice_is_found_by_change_id_not_by_filename(feed: Path) -> None:
    assert runner.notice_available(EXTERNAL_ID, directory=feed)
    assert not runner.notice_available("notice", directory=feed)


def test_a_missing_feed_directory_is_not_an_error(tmp_path: Path) -> None:
    assert not runner.notice_available(EXTERNAL_ID, directory=tmp_path / "absent")


async def test_an_event_naming_no_change_is_skipped() -> None:
    conn = RecordingConnection()

    outcome = await runner.run_change_intelligence(conn, normalized(external_id=""))

    assert outcome.action == "skipped"
    assert outcome.reason == "event names no change"
    assert conn.executed == []


async def test_this_lane_does_not_react_to_its_own_output() -> None:
    """Enriching our own event would loop, with a per-turn bill attached."""
    conn = RecordingConnection()

    outcome = await runner.run_change_intelligence(conn, normalized(origin="change_intelligence"))

    assert outcome.action == "skipped"
    assert outcome.reason == "this lane wrote it"
    assert conn.executed == []


async def test_a_change_with_no_notice_is_left_to_the_deterministic_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constraint 10: no notice means no invented migration."""
    monkeypatch.setattr(runner, "notice_available", lambda *_a, **_k: False)
    conn = RecordingConnection()

    outcome = await runner.run_change_intelligence(
        conn, normalized(external_id="probe:gemini_api:some-model")
    )

    assert outcome.action == "skipped"
    assert outcome.reason == "no provider notice covers this change"
    assert conn.executed == []


async def test_an_unavailable_model_does_not_nack_the_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The finding is already correct, so a retry would only cost a turn."""
    monkeypatch.setattr(runner, "notice_available", lambda *_a, **_k: True)
    monkeypatch.setattr(runner, "_environment_reason", lambda: "google-adk is not installed")
    conn = RecordingConnection()

    outcome = await runner.run_change_intelligence(conn, normalized())

    assert outcome.action == "skipped"
    assert outcome.reason == "google-adk is not installed"
    assert conn.executed == []


def a_manifest() -> ChangeManifest:
    return ChangeManifest.model_validate(
        {
            "provider": "google",
            "change_id": EXTERNAL_ID,
            "change_type": "model_retirement",
            "severity": "high",
            "effective_at": "2026-08-17",
            "affected_identifiers": [IDENTIFIER],
            "recommended_replacement": "gemini-3.1-flash-image",
            "semantic_migration_required": True,
            "source_urls": ["https://ai.google.dev/gemini-api/docs/deprecations"],
        }
    )


async def test_a_recorded_manifest_becomes_a_corpus_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_manifest(_change_id: str, *, run_id: str) -> tuple[Any, str]:
        return a_manifest(), "The probe 404s on both surfaces and the notice agrees."

    monkeypatch.setattr(runner, "notice_available", lambda *_a, **_k: True)
    monkeypatch.setattr(runner, "_environment_reason", lambda: None)
    monkeypatch.setattr(runner, "_produce_manifest", fake_manifest)
    conn = RecordingConnection()

    outcome = await runner.run_change_intelligence(conn, normalized())

    assert outcome.action == "normalized"
    assert outcome.replacement == "gemini-3.1-flash-image"
    query, args = conn.rows[0]
    assert query.strip().startswith("INSERT INTO change_events")
    assert EXTERNAL_ID in args
    assert "The probe 404s on both surfaces and the notice agrees." in args
    # One row per identifier, plus the replacement it points at.
    identifier_writes = [
        call
        for call in conn.executed
        if "change_event_identifiers" in call[0] and "INSERT" in call[0]
    ]
    assert len(identifier_writes) == 2


async def test_the_rationale_may_not_describe_a_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The corpus row is shown to every subscriber, so it holds no project claim.

    Enforced by where the sentence is stored rather than by reading it: nothing
    in this path is given a project, so there is no repository for the agent to
    describe.
    """

    async def fake_manifest(_change_id: str, *, run_id: str) -> tuple[Any, str]:
        return a_manifest(), "Both identifiers 404."

    monkeypatch.setattr(runner, "notice_available", lambda *_a, **_k: True)
    monkeypatch.setattr(runner, "_environment_reason", lambda: None)
    monkeypatch.setattr(runner, "_produce_manifest", fake_manifest)
    conn = RecordingConnection()

    await runner.run_change_intelligence(conn, normalized())

    corpus_writes = [call for call in conn.rows if "change_events" in call[0]]
    assert corpus_writes, "the notice should have produced a corpus row"
    for _query, args in corpus_writes:
        assert not any("project_id" in str(arg) for arg in args)


async def test_an_agent_that_asks_for_a_human_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_manifest(_change_id: str, *, run_id: str) -> tuple[Any | None, str]:
        return None, ""

    monkeypatch.setattr(runner, "notice_available", lambda *_a, **_k: True)
    monkeypatch.setattr(runner, "_environment_reason", lambda: None)
    monkeypatch.setattr(runner, "_produce_manifest", no_manifest)
    conn = RecordingConnection()

    outcome = await runner.run_change_intelligence(conn, normalized())

    assert outcome.action == "skipped"
    assert outcome.reason == "the agent recorded no manifest"
    assert conn.executed == []
