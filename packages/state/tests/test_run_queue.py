"""The lease, asserted against Postgres.

The one property that matters here cannot be tested against a fake connection,
because it is a property of `FOR UPDATE SKIP LOCKED` and not of our code: two
workers polling at the same moment must not both be handed the same run. So these
tests open real connections and let them race.

Unlike the other run tests these cannot each live inside one rolled-back
transaction — the point is two transactions seeing each other — so the rows are
created and deleted by hand.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from packages.schemas.run_state import RunState
from packages.state import remediation, run_queue
from packages.state.corpus import write_manifest
from packages.state.pool import configure_connection
from packages.state.tests.test_corpus import manifest

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the lease tests need Postgres with migration 0021",
)

REPO = "patchapi-test/leased"


async def _connect() -> Any:
    connection = await asyncpg.connect(DSN)
    await configure_connection(connection)
    return connection


@pytest.fixture
async def owned() -> Any:
    """One RECEIVED run, and everything it needs, removed afterwards."""
    connection = await _connect()
    owner = await connection.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, 'Lease Test') RETURNING id",
        f"lease-{uuid4().hex}@example.test",
    )
    project = await connection.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id",
        owner,
        f"lease-{uuid4().hex[:8]}",
    )
    change = await write_manifest(connection, manifest())
    handle = await remediation.open_run(
        connection,
        change_event_id=change.change_event_id,
        project_id=str(project),
        repository=REPO,
        base_sha="b" * 40,
    )
    try:
        yield connection, handle.run_id
    finally:
        # The project cascades to the run, its traces and its transitions.
        await connection.execute("DELETE FROM projects WHERE id = $1", project)
        await connection.execute("DELETE FROM users WHERE id = $1", owner)
        await connection.close()


async def _leased_by(connection: Any, run_id: str) -> str:
    return await connection.fetchval(
        "SELECT leased_by FROM remediation_runs WHERE id = $1::uuid", run_id
    )


async def test_a_claim_takes_the_run_and_records_who_has_it(owned: Any) -> None:
    connection, run_id = owned

    claimed = await run_queue.claim(connection, "worker-a")

    assert claimed == run_id
    assert await _leased_by(connection, run_id) == "worker-a"


async def test_two_workers_racing_do_not_both_get_the_same_run(owned: Any) -> None:
    """Why this module exists. A run performed twice opens two pull requests."""
    connection, run_id = owned
    rival = await _connect()
    try:
        held = connection.transaction()
        await held.start()
        first = await run_queue.claim(connection, "worker-a")

        # `worker-b` polls while `worker-a`'s claim is still uncommitted. Without
        # SKIP LOCKED this blocks and then claims the row `worker-a` already has.
        second = await run_queue.claim(rival, "worker-b")

        await held.commit()
        assert first == run_id
        assert second is None
    finally:
        await rival.close()


async def test_a_run_that_is_not_received_is_not_claimable(owned: Any) -> None:
    connection, run_id = owned
    await remediation.advance(connection, run_id, RunState.SANITIZED, actor="test")

    assert await run_queue.claim(connection, "worker-a") is None


async def test_a_released_run_can_be_claimed_again(owned: Any) -> None:
    """A restart and an operator resume both come back through RECEIVED."""
    connection, run_id = owned
    await run_queue.claim(connection, "worker-a")

    await run_queue.release(connection, run_id, "worker-a")

    assert await _leased_by(connection, run_id) == ""
    assert await run_queue.claim(connection, "worker-b") == run_id


async def test_a_stale_lease_on_an_unstarted_run_is_reclaimed(owned: Any) -> None:
    """An instance that died before the first transition must not strand the run."""
    connection, run_id = owned
    await run_queue.claim(connection, "worker-a")
    await connection.execute(
        "UPDATE remediation_runs SET leased_at = now() - $2::interval WHERE id = $1::uuid",
        run_id,
        timedelta(seconds=run_queue.LEASE_SECONDS + 60),
    )

    assert await run_queue.claim(connection, "worker-b") == run_id
    assert await _leased_by(connection, run_id) == "worker-b"


async def test_a_worker_cannot_release_a_lease_it_does_not_hold(owned: Any) -> None:
    """Otherwise a reclaimed worker's late release frees the run under its successor."""
    connection, run_id = owned
    await run_queue.claim(connection, "worker-a")

    await run_queue.release(connection, run_id, "worker-b")

    assert await _leased_by(connection, run_id) == "worker-a"
