"""Normalizing a notice once, against the real tables.

The rows these assertions read are the ones the Releases tab joins against, so
the test uses Postgres rather than a fake connection: an upsert that silently
inserted a second card, or a role that made a new-identifier announcement look
like a retirement, would both pass against a recorder.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from packages.schemas.change_manifest import ChangeManifest, IdentifierReplacement
from packages.state.corpus import NORMALIZER_VERSION, write_manifest
from packages.state.pool import _configure

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the corpus tests need Postgres with migration 0014 applied",
)


@pytest.fixture
async def conn() -> Any:
    connection = await asyncpg.connect(DSN)
    # The same codecs the pool registers. Without them a jsonb argument would
    # have to be pre-serialized here and nowhere else, which is how the
    # double-encoding bug got in the first time.
    await _configure(connection)
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


def manifest(**overrides: Any) -> ChangeManifest:
    payload: dict[str, Any] = {
        "provider": "google",
        "change_id": f"test-{uuid4().hex}",
        "change_type": "model_retirement",
        "severity": "high",
        "announced_at": "2026-06-23",
        "effective_at": "2026-08-17",
        "affected_identifiers": ["test-model-a", "test-model-b"],
        "recommended_replacement": "test-model-next",
        "semantic_migration_required": True,
        "source_urls": ["https://ai.google.dev/gemini-api/docs/deprecations"],
    }
    payload.update(overrides)
    return ChangeManifest.model_validate(payload)


async def identifiers(conn: Any, event_id: str) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT identifier, role::text AS role, replacement, semantic, "
        "asserted_by::text AS asserted_by "
        "FROM change_event_identifiers WHERE change_event_id = $1",
        event_id,
    )
    return {row["identifier"]: dict(row) for row in rows}


async def test_a_notice_becomes_one_row_per_identifier(conn: Any) -> None:
    written = await write_manifest(conn, manifest(), title="Test retirement")

    assert written.identifiers == 2
    rows = await identifiers(conn, written.change_event_id)
    assert rows["test-model-a"]["role"] == "retired"
    assert rows["test-model-a"]["replacement"] == "test-model-next"
    assert rows["test-model-a"]["semantic"] is True
    assert rows["test-model-next"]["role"] == "replacement"
    assert rows["test-model-a"]["asserted_by"] == "agent"


async def test_per_identifier_overrides_the_notice_wide_answer(conn: Any) -> None:
    written = await write_manifest(
        conn,
        manifest(
            per_identifier=[
                IdentifierReplacement(
                    identifier="test-model-b",
                    replacement="test-model-other",
                    semantic_migration_required=False,
                )
            ]
        ),
    )

    rows = await identifiers(conn, written.change_event_id)
    assert rows["test-model-a"]["replacement"] == "test-model-next"
    assert rows["test-model-b"]["replacement"] == "test-model-other"
    assert rows["test-model-b"]["semantic"] is False


async def test_reading_the_same_notice_twice_corrects_one_card(conn: Any) -> None:
    first = await write_manifest(conn, manifest(change_id="test-stable"), title="First reading")
    second = await write_manifest(
        conn,
        manifest(change_id="test-stable", affected_identifiers=["test-model-a"]),
        title="Second reading",
    )

    assert first.change_event_id == second.change_event_id
    count = await conn.fetchval(
        "SELECT count(*) FROM change_events WHERE external_id = 'test-stable'"
    )
    assert count == 1
    # The dropped identifier must stop joining, or a corrected notice would go on
    # telling somebody to migrate code that is fine.
    rows = await identifiers(conn, second.change_event_id)
    assert "test-model-b" not in rows


async def test_the_providers_own_words_survive_a_re_read(conn: Any) -> None:
    written = await write_manifest(
        conn, manifest(change_id="test-summary"), summary="What Google published."
    )
    await write_manifest(
        conn,
        manifest(change_id="test-summary"),
        summary="A later, worse paraphrase.",
        rationale="The liveness check agrees the identifiers no longer resolve.",
    )

    row = await conn.fetchrow(
        "SELECT summary, rationale, normalizer_version FROM change_events WHERE id = $1",
        written.change_event_id,
    )
    assert row["summary"] == "What Google published."
    assert row["rationale"].startswith("The liveness check agrees")
    assert row["normalizer_version"] == NORMALIZER_VERSION


async def test_a_behaviour_change_does_not_retire_what_it_names(conn: Any) -> None:
    written = await write_manifest(
        conn,
        manifest(
            change_type="behavior_change",
            recommended_replacement=None,
            semantic_migration_required=False,
            effective_at=None,
        ),
    )

    rows = await identifiers(conn, written.change_event_id)
    assert {row["role"] for row in rows.values()} == {"mentioned"}


async def test_a_live_404_is_recorded_as_corroboration(conn: Any) -> None:
    identifier = f"test-gone-{uuid4().hex[:8]}"
    await conn.execute(
        "INSERT INTO identifier_liveness (identifier, surface, provider, status) "
        "VALUES ($1, 'gemini_api', 'google', 'not_found')",
        identifier,
    )

    written = await write_manifest(conn, manifest(affected_identifiers=[identifier]))

    row = await conn.fetchrow(
        "SELECT corroborated_by::text AS corroborated_by, live_status::text AS live_status "
        "FROM change_event_identifiers WHERE change_event_id = $1 AND identifier = $2",
        written.change_event_id,
        identifier,
    )
    assert row["corroborated_by"] == "live"
    assert row["live_status"] == "not_found"


async def test_corroboration_is_evidence_and_not_a_gate(conn: Any) -> None:
    """An identifier nothing has checked is still written, and still joins."""
    written = await write_manifest(conn, manifest(affected_identifiers=["test-unchecked"]))

    row = await conn.fetchrow(
        "SELECT role::text AS role, corroborated_by FROM change_event_identifiers "
        "WHERE change_event_id = $1 AND identifier = 'test-unchecked'",
        written.change_event_id,
    )
    assert row["role"] == "retired"
    assert row["corroborated_by"] is None
