"""The lease, asserted against Postgres.

The one property that matters here cannot be tested against a fake connection,
because it is a property of `FOR UPDATE SKIP LOCKED` and not of our code: two
workers polling at the same moment must not both be handed the same run. So these
tests open real connections and let them race.

Unlike the other run tests these cannot each live inside one rolled-back
transaction — the point is two transactions seeing each other — so the rows are
created and deleted by hand.

Every test gets its own lane. Not tidiness: the fixture writes a real RECEIVED
row into the database a running worker is polling, and before lanes existed a
local worker claimed these rows within a second and began remediating a
repository that does not exist. A unique lane is also what the production
property is: a worker takes runs addressed to it and no others.
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
    reason="DATABASE_URL is unset; the lease tests need Postgres with migration 0022",
)

REPO = "patchapi-test/leased"


async def _connect() -> Any:
    connection = await asyncpg.connect(DSN)
    await configure_connection(connection)
    return connection


@pytest.fixture
def lane() -> str:
    """A lane no other test and no running worker shares."""
    return f"test-{uuid4().hex[:12]}"


@pytest.fixture
async def owned(lane: str) -> Any:
    """One RECEIVED run in this test's lane, removed afterwards."""
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
        lane=lane,
    )
    try:
        yield connection, handle.run_id
    finally:
        # The project cascades to the run, its traces and its transitions.
        await connection.execute("DELETE FROM projects WHERE id = $1", project)
        await connection.execute("DELETE FROM users WHERE id = $1", owner)
        await connection.close()


@pytest.fixture
async def two_owned(lane: str) -> Any:
    """Two RECEIVED runs in this test's lane, on different repositories."""
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
    handles = [
        await remediation.open_run(
            connection,
            change_event_id=change.change_event_id,
            project_id=str(project),
            repository=f"{REPO}-{index}",
            base_sha="b" * 40,
            lane=lane,
        )
        for index in (1, 2)
    ]
    try:
        yield connection, [handle.run_id for handle in handles]
    finally:
        await connection.execute("DELETE FROM projects WHERE id = $1", project)
        await connection.execute("DELETE FROM users WHERE id = $1", owner)
        await connection.close()


async def _leased_by(connection: Any, run_id: str) -> str:
    return await connection.fetchval(
        "SELECT leased_by FROM remediation_runs WHERE id = $1::uuid", run_id
    )


async def test_a_claim_takes_the_run_and_records_who_has_it(owned: Any, lane: str) -> None:
    connection, run_id = owned

    claimed = await run_queue.claim(connection, "worker-a", lane=lane)

    assert claimed == run_id
    assert await _leased_by(connection, run_id) == "worker-a"


async def test_two_workers_racing_do_not_both_get_the_same_run(owned: Any, lane: str) -> None:
    """Why this module exists. A run performed twice opens two pull requests."""
    connection, run_id = owned
    rival = await _connect()
    try:
        held = connection.transaction()
        await held.start()
        first = await run_queue.claim(connection, "worker-a", lane=lane)

        # `worker-b` polls while `worker-a`'s claim is still uncommitted. Without
        # SKIP LOCKED this blocks and then claims the row `worker-a` already has.
        second = await run_queue.claim(rival, "worker-b", lane=lane)

        await held.commit()
        assert first == run_id
        assert second is None
    finally:
        await rival.close()


async def test_two_workers_take_one_run_each_when_two_are_waiting(
    two_owned: Any, lane: str
) -> None:
    """The other half of the lease: exclusion must not cost parallelism.

    Two instances is how concurrency is added — a worker performs one run at a
    time — so two waiting runs have to become two runs in progress rather than a
    queue of one behind a busy instance.
    """
    connection, run_ids = two_owned
    rival = await _connect()
    try:
        held = connection.transaction()
        await held.start()
        first = await run_queue.claim(connection, "worker-a", lane=lane)

        # Polling inside `worker-a`'s open transaction is the worst case: the row
        # it took is locked and uncommitted.
        second = await run_queue.claim(rival, "worker-b", lane=lane)

        await held.commit()
        assert {first, second} == set(run_ids)
        assert first != second
    finally:
        await rival.close()


async def test_a_run_that_is_not_received_is_not_claimable(owned: Any, lane: str) -> None:
    connection, run_id = owned
    await remediation.advance(connection, run_id, RunState.SANITIZED, actor="test")

    assert await run_queue.claim(connection, "worker-a", lane=lane) is None


async def test_a_released_run_can_be_claimed_again(owned: Any, lane: str) -> None:
    """A restart and an operator resume both come back through RECEIVED."""
    connection, run_id = owned
    await run_queue.claim(connection, "worker-a", lane=lane)

    await run_queue.release(connection, run_id, "worker-a")

    assert await _leased_by(connection, run_id) == ""
    assert await run_queue.claim(connection, "worker-b", lane=lane) == run_id


async def test_a_stale_lease_on_an_unstarted_run_is_reclaimed(owned: Any, lane: str) -> None:
    """An instance that died before the first transition must not strand the run."""
    connection, run_id = owned
    await run_queue.claim(connection, "worker-a", lane=lane)
    await connection.execute(
        "UPDATE remediation_runs SET leased_at = now() - $2::interval WHERE id = $1::uuid",
        run_id,
        timedelta(seconds=run_queue.LEASE_SECONDS + 60),
    )

    assert await run_queue.claim(connection, "worker-b", lane=lane) == run_id
    assert await _leased_by(connection, run_id) == "worker-b"


async def test_a_worker_cannot_release_a_lease_it_does_not_hold(owned: Any, lane: str) -> None:
    """Otherwise a reclaimed worker's late release frees the run under its successor."""
    connection, run_id = owned
    await run_queue.claim(connection, "worker-a", lane=lane)

    await run_queue.release(connection, run_id, "worker-b")

    assert await _leased_by(connection, run_id) == "worker-a"


async def test_a_worker_does_not_claim_another_lanes_run(owned: Any, lane: str) -> None:
    """The deployment and a laptop share one database. Neither may take the other's."""
    connection, run_id = owned

    assert await run_queue.claim(connection, "worker-b", lane="somebody-else") is None
    assert await _leased_by(connection, run_id) == ""
    assert await run_queue.claim(connection, "worker-a", lane=lane) == run_id


async def test_a_run_dispatched_to_a_push_lane_is_claimed_by_nobody(owned: Any) -> None:
    """A job execution and a local subprocess are handed a run id; nothing polls.

    So an empty lane must not be a wildcard on either side. Claiming with one is
    refused outright, and a row carrying one is invisible to every worker.
    """
    connection, run_id = owned
    await connection.execute(
        "UPDATE remediation_runs SET lane = '' WHERE id = $1::uuid", run_id
    )

    with pytest.raises(ValueError):
        await run_queue.claim(connection, "worker-a", lane="")

    assert await run_queue.claim(connection, "worker-a", lane="anything") is None
