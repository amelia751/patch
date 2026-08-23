"""The run record, asserted against the real tables.

These run against Postgres rather than a recorder because the properties worth
testing are the ones the schema and the state machine enforce together: that a
second click cannot open a second run, that an illegal move leaves no trace
behind it, and that a claimed side effect cannot be claimed twice. A fake
connection would agree with whatever the code did.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from packages.schemas.run_state import IllegalRunStateTransitionError, RunState
from packages.state import remediation
from packages.state.corpus import write_manifest
from packages.state.pool import configure_connection
from packages.state.tests.test_corpus import manifest

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the remediation tests need Postgres with migration 0018",
)

REPO = "patchapi-test/storygen"
SHA_A = "a" * 40


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


async def seed(conn: Any) -> tuple[str, str]:
    """A project and a change event for a run to be about."""
    owner = await conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, 'Run Test') RETURNING id",
        f"run-{uuid4().hex}@example.test",
    )
    project = await conn.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id",
        owner,
        f"run-{uuid4().hex[:8]}",
    )
    change = await write_manifest(conn, manifest())
    return str(project), change.change_event_id


async def open_one(conn: Any) -> remediation.RunHandle:
    project, change = await seed(conn)
    return await remediation.open_run(
        conn, change_event_id=change, project_id=project, repository=REPO, base_sha=SHA_A
    )


async def states(conn: Any, run_id: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT to_state::text AS s FROM run_state_transitions WHERE run_id = $1 ORDER BY sequence",
        remediation._uuid(run_id),
    )
    return [row["s"] for row in rows]


async def test_opening_a_run_records_where_it_started(conn: Any) -> None:
    handle = await open_one(conn)

    assert handle.dispatch is True
    assert handle.state is RunState.RECEIVED
    assert handle.repository == REPO
    assert await states(conn, handle.run_id) == ["RECEIVED"]


async def test_a_second_click_does_not_open_a_second_run(conn: Any) -> None:
    """The property that stops one change producing two pull requests."""
    project, change = await seed(conn)
    first = await remediation.open_run(
        conn, change_event_id=change, project_id=project, repository=REPO
    )
    await remediation.advance(conn, first.run_id, RunState.SANITIZED, actor="job")

    second = await remediation.open_run(
        conn, change_event_id=change, project_id=project, repository=REPO
    )

    assert second.run_id == first.run_id
    # Already in flight, so the caller must not start a second execution.
    assert second.dispatch is False
    assert second.state is RunState.SANITIZED
    count = await conn.fetchval("SELECT count(*) FROM remediation_runs WHERE repository = $1", REPO)
    assert count == 1


async def test_a_finished_run_begins_again_on_the_same_row(conn: Any) -> None:
    project, change = await seed(conn)
    first = await remediation.open_run(
        conn, change_event_id=change, project_id=project, repository=REPO
    )
    await remediation.advance(conn, first.run_id, RunState.FAILED, actor="job", reason="build died")

    again = await remediation.open_run(
        conn, change_event_id=change, project_id=project, repository=REPO
    )

    assert again.run_id == first.run_id
    assert again.dispatch is True
    assert again.state is RunState.RECEIVED
    # The failure stays in the history rather than being erased by the retry.
    assert await states(conn, again.run_id) == ["RECEIVED", "FAILED", "RECEIVED"]
    reason = await conn.fetchval(
        "SELECT failure_reason FROM remediation_runs WHERE id = $1",
        remediation._uuid(again.run_id),
    )
    assert reason == ""


async def test_an_illegal_move_is_refused_and_leaves_nothing_behind(conn: Any) -> None:
    handle = await open_one(conn)

    with pytest.raises(IllegalRunStateTransitionError):
        await remediation.advance(conn, handle.run_id, RunState.PR_CREATED, actor="job")

    state = await conn.fetchval(
        "SELECT state::text FROM remediation_runs WHERE id = $1",
        remediation._uuid(handle.run_id),
    )
    assert state == "RECEIVED"
    assert await states(conn, handle.run_id) == ["RECEIVED"]


async def test_reaching_a_terminal_state_ends_the_run(conn: Any) -> None:
    handle = await open_one(conn)
    for state in (RunState.SANITIZED, RunState.NORMALIZED, RunState.IMPACT_SCANNING):
        await remediation.advance(conn, handle.run_id, state, actor="job")
    await remediation.advance(
        conn, handle.run_id, RunState.UNAFFECTED, actor="job", reason="no runtime usage"
    )

    row = await conn.fetchrow(
        "SELECT state::text AS state, ended_at FROM remediation_runs WHERE id = $1",
        remediation._uuid(handle.run_id),
    )
    assert row["state"] == "UNAFFECTED"
    assert row["ended_at"] is not None


async def test_an_external_action_can_only_be_claimed_once(conn: Any) -> None:
    """What stops a restarted job opening a second pull request."""
    handle = await open_one(conn)

    assert await remediation.claim(conn, handle.run_id, "open_pull_request", SHA_A) is True
    assert await remediation.claim(conn, handle.run_id, "open_pull_request", SHA_A) is False
    # A different commit is a different action, and is allowed.
    assert await remediation.claim(conn, handle.run_id, "open_pull_request", "b" * 40) is True


async def test_the_worklog_keeps_the_order_it_was_written_in(conn: Any) -> None:
    handle = await open_one(conn)
    for index, text in enumerate(("reading the notice", "found three hits", "done")):
        await remediation.append_trace(
            conn, handle.run_id, state=RunState.RECEIVED, kind="narration", body=text
        )
        assert index >= 0

    rows = await conn.fetch(
        "SELECT sequence, body FROM run_trace_events WHERE run_id = $1 ORDER BY sequence",
        remediation._uuid(handle.run_id),
    )
    assert [row["sequence"] for row in rows] == [1, 2, 3]
    assert rows[0]["body"] == "reading the notice"


async def test_policy_cannot_record_an_auto_merge(conn: Any) -> None:
    """The product's hardest promise, asserted by the schema rather than by code."""
    handle = await open_one(conn)
    await remediation.record_policy(
        conn, handle.run_id, decision="allow", auto_patch=True, auto_pr=True
    )

    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await conn.execute(
            "UPDATE policy_decisions SET auto_merge = true WHERE run_id = $1",
            remediation._uuid(handle.run_id),
        )


async def test_attempts_are_numbered_and_counted_on_the_run(conn: Any) -> None:
    handle = await open_one(conn)

    _first, first_number = await remediation.begin_attempt(conn, handle.run_id, patch_agent="patch")
    second_id, second_number = await remediation.begin_attempt(conn, handle.run_id)
    await remediation.finish_attempt(conn, second_id, status="succeeded", build_exit_code=0)

    assert (first_number, second_number) == (1, 2)
    used = await conn.fetchval(
        "SELECT attempts_used FROM remediation_runs WHERE id = $1",
        remediation._uuid(handle.run_id),
    )
    assert used == 2


async def test_verification_records_both_agents(conn: Any) -> None:
    handle = await open_one(conn)
    await remediation.record_verification(
        conn,
        handle.run_id,
        verdict="pass",
        checks=[{"name": "clean build", "passed": True}],
        verifier_agent="verification",
        patch_agent="patch",
    )

    row = await conn.fetchrow(
        "SELECT verdict::text AS verdict, verifier_agent, patch_agent, checks "
        "FROM verification_results WHERE run_id = $1",
        remediation._uuid(handle.run_id),
    )
    assert row["verdict"] == "pass"
    assert row["verifier_agent"] != row["patch_agent"]
    assert row["checks"][0]["name"] == "clean build"


async def test_a_pull_request_may_not_claim_patchapi_merged_it(conn: Any) -> None:
    handle = await open_one(conn)
    await remediation.record_pull_request(
        conn,
        handle.run_id,
        number=7,
        url="https://github.com/patchapi-test/storygen/pull/7",
        head_branch="patchapi/imagen4",
        base_branch="main",
    )

    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await conn.execute(
            "UPDATE pull_requests SET merged_by_patchapi = true WHERE run_id = $1",
            remediation._uuid(handle.run_id),
        )
