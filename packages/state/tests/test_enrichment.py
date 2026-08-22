"""The agent may explain a release. It may not decide one."""

from __future__ import annotations

from typing import Any

import pytest

from packages.state.enrichment import (
    _ENRICH_SQL,
    apply_agent_rationale,
    enrich_from_manifest,
)

# Columns that decide whether a release reaches Need you. The whole point of the
# enrichment path is that agent output cannot reach them.
STATUS_COLUMNS = (
    "severity",
    "change_kind",
    "fail_closed",
    "false_positive",
    "effective_at",
    "announced_at",
)


class FakeConnection:
    """Records the statements enrichment issues and what it bound to them."""

    def __init__(self, *, external_id: str | None = "probe:gemini_api:imagen-4.0-generate-001"):
        self._external_id = external_id
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        if self._external_id is None:
            return None
        return {"external_id": self._external_id}

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"


def test_the_update_cannot_reach_a_status_column() -> None:
    for column in STATUS_COLUMNS:
        assert column not in _ENRICH_SQL, f"{column} must stay out of the agent's reach"
    assert "project_change_findings" not in _ENRICH_SQL
    assert _ENRICH_SQL.strip().startswith("UPDATE change_events")


async def test_rationale_and_replacement_are_bound() -> None:
    conn = FakeConnection()

    updated = await apply_agent_rationale(
        conn,  # type: ignore[arg-type]
        external_id="probe:gemini_api:imagen-4.0-generate-001",
        rationale="The Gemini API stopped listing this id; storygen still calls it.",
        replacement="gemini-3.1-flash-image",
        replaced_identifier="imagen-4.0-generate-001",
        migration="semantic",
        source_urls=["https://ai.google.dev/gemini-api/docs/deprecations"],
    )

    assert updated
    _, args = conn.executed[0]
    assert args[0] == "probe:gemini_api:imagen-4.0-generate-001"
    assert "storygen" in args[1]
    assert args[2] == [
        {
            "from": "imagen-4.0-generate-001",
            "to": "gemini-3.1-flash-image",
            "notes": "proposed by analysis",
        }
    ]
    assert args[3] == "semantic"


async def test_replacements_stay_empty_without_both_ends() -> None:
    """A replacement with nothing to replace is not a migration, it is a guess."""
    conn = FakeConnection()

    await apply_agent_rationale(
        conn,  # type: ignore[arg-type]
        external_id="probe:gemini_api:imagen-4.0-generate-001",
        rationale="No successor named.",
        replacement="gemini-3.1-flash-image",
    )

    assert conn.executed[0][1][2] == []


async def test_an_unknown_migration_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown migration kind"):
        await apply_agent_rationale(
            FakeConnection(),  # type: ignore[arg-type]
            external_id="probe:gemini_api:imagen-4.0-generate-001",
            migration="rewrite-everything",
        )


async def test_a_manifest_lands_on_the_event_the_probe_wrote() -> None:
    """The agent's change_id differs from the probe's, so identifiers match them up."""
    conn = FakeConnection(external_id="probe:gemini_api:imagen-4.0-generate-001")

    applied = await enrich_from_manifest(
        conn,  # type: ignore[arg-type]
        {
            "change_id": "google-imagen4-shutdown-2026-08-17",
            "provider": "google",
            "affected_identifiers": ["imagen-4.0-generate-001"],
            "recommended_replacement": "gemini-3.1-flash-image",
            "semantic_migration_required": True,
            "rationale": "Imagen 4 no longer resolves; native image generation replaces it.",
            "source_urls": ["https://ai.google.dev/gemini-api/docs/deprecations"],
        },
    )

    assert applied
    assert conn.executed[0][1][0] == "probe:gemini_api:imagen-4.0-generate-001"


async def test_a_manifest_for_an_unrecorded_release_writes_nothing() -> None:
    conn = FakeConnection(external_id=None)

    applied = await enrich_from_manifest(
        conn,  # type: ignore[arg-type]
        {
            "provider": "google",
            "affected_identifiers": ["some-model-nobody-indexed"],
            "rationale": "Confident prose about a release with no evidence behind it.",
        },
    )

    assert not applied
    assert conn.executed == []
