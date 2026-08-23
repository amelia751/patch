"""One repository's verdict, scoped to the commit it was read from."""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from packages.schemas.impact_report import ImpactReport
from packages.state.corpus import write_manifest
from packages.state.impact import impacts_for, write_report
from packages.state.pool import configure_connection
from packages.state.tests.test_corpus import manifest

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the impact tests need Postgres with migration 0014 applied",
)

SHA_A = "a" * 40
SHA_B = "b" * 40


@pytest.fixture
async def conn() -> Any:
    connection = await asyncpg.connect(DSN)
    await configure_connection(connection)
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def seed_project(conn: Any) -> str:
    owner = await conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, 'Impact Test') RETURNING id",
        f"impact-{uuid4().hex}@example.test",
    )
    return str(
        await conn.fetchval(
            "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id",
            owner,
            f"impact-{uuid4().hex[:8]}",
        )
    )


def report(change_id: str, **overrides: Any) -> ImpactReport:
    payload: dict[str, Any] = {
        "run_id": f"run-{uuid4().hex[:8]}",
        "change_id": change_id,
        "repo": "patchapi-test/storygen",
        "base_sha": SHA_A,
        "affected": True,
        "confidence": 0.9,
        "migration_character": "semantic",
        "required_checks": ["pytest"],
        "findings": [
            {
                "identifier": "test-model-a",
                "file": "lib/gemini.ts",
                "kind": "runtime_source",
                "line": 12,
            }
        ],
        "notes": "Three references, all string literals.",
    }
    payload.update(overrides)
    return ImpactReport.model_validate(payload)


async def test_a_report_lands_with_its_findings(conn: Any) -> None:
    project_id = await seed_project(conn)
    change = await write_manifest(conn, manifest(change_id="impact-basic"))

    written = await write_report(conn, report(change.external_id), project_id=project_id)

    assert written is not None
    assert written.findings == 1
    rows = await impacts_for(conn, project_id=project_id, external_id=change.external_id)
    assert len(rows) == 1
    assert rows[0]["notes"].startswith("Three references")
    assert rows[0]["findings"][0]["path"] == "lib/gemini.ts"


async def test_a_new_commit_is_a_new_assessment(conn: Any) -> None:
    project_id = await seed_project(conn)
    change = await write_manifest(conn, manifest(change_id="impact-sha"))

    await write_report(conn, report(change.external_id), project_id=project_id)
    await write_report(
        conn,
        report(
            change.external_id,
            base_sha=SHA_B,
            affected=False,
            findings=[],
            migration_character=None,
            required_checks=[],
        ),
        project_id=project_id,
    )

    rows = await impacts_for(conn, project_id=project_id, external_id=change.external_id)
    assert {row["base_sha"] for row in rows} == {SHA_A, SHA_B}
    # The older reading survives rather than being overwritten by a verdict
    # about a different tree.
    assert len(rows) == 2


async def test_reassessing_one_commit_replaces_its_findings(conn: Any) -> None:
    project_id = await seed_project(conn)
    change = await write_manifest(conn, manifest(change_id="impact-replace"))

    await write_report(conn, report(change.external_id), project_id=project_id)
    await write_report(
        conn,
        report(
            change.external_id,
            findings=[
                {
                    "identifier": "test-model-a",
                    "file": "app/page.tsx",
                    "kind": "runtime_source",
                    "line": 4,
                }
            ],
        ),
        project_id=project_id,
    )

    rows = await impacts_for(conn, project_id=project_id, external_id=change.external_id)
    assert len(rows) == 1
    paths = [finding["path"] for finding in rows[0]["findings"]]
    assert paths == ["app/page.tsx"]


async def test_an_assessment_of_an_unknown_change_is_dropped(conn: Any) -> None:
    """Impact explains a card. It does not conjure one."""
    project_id = await seed_project(conn)

    written = await write_report(conn, report("no-such-change"), project_id=project_id)

    assert written is None


async def test_two_projects_keep_their_own_verdicts(conn: Any) -> None:
    """The bug this schema exists to prevent, asserted directly."""
    first = await seed_project(conn)
    second = await seed_project(conn)
    change = await write_manifest(conn, manifest(change_id="impact-scope"))

    await write_report(
        conn, report(change.external_id, notes="Fourteen hits here."), project_id=first
    )
    await write_report(
        conn,
        report(
            change.external_id,
            repo="patchapi-test/other",
            affected=False,
            findings=[],
            migration_character=None,
            required_checks=[],
            notes="Nothing here uses it.",
        ),
        project_id=second,
    )

    mine = await impacts_for(conn, project_id=first, external_id=change.external_id)
    theirs = await impacts_for(conn, project_id=second, external_id=change.external_id)
    assert [row["notes"] for row in mine] == ["Fourteen hits here."]
    assert [row["notes"] for row in theirs] == ["Nothing here uses it."]
