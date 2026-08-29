"""What the console is allowed to say about a run that has not started.

The lease says who is performing a run. Nothing said whether anyone was
available to perform one, so the two situations an operator most needs told
apart looked identical from the run row: queued behind a busy worker, or
stranded because none is polling.

The second one happened. A worker's pooled connections to Cloud SQL died of
idleness, the poll loop blocked in an unbounded `Pool.acquire()`, and the process
stayed alive and silent for four hours while two runs waited. The console counted
upwards and advised checking whether a worker was running — the right thing to
check, and not something it could answer.

These assert the heartbeat answers it, and that it stays diagnostic: nothing here
is consulted to decide whether a run may be claimed.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from packages.state import worker_registry
from packages.state.pool import configure_connection

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; these need Postgres with migration 0023",
)


@pytest.fixture
def lane() -> str:
    """A lane no other test and no running worker shares."""
    return f"test-{uuid4().hex[:12]}"


@pytest.fixture
async def connection(lane: str) -> Any:
    opened = await asyncpg.connect(DSN)
    await configure_connection(opened)
    try:
        yield opened
    finally:
        await opened.execute("DELETE FROM remediation_workers WHERE lane = $1", lane)
        await opened.close()


async def _age(opened: Any, worker: str, seconds: float) -> None:
    await opened.execute(
        "UPDATE remediation_workers SET last_seen_at = now() - $2::interval WHERE worker_id = $1",
        worker,
        timedelta(seconds=seconds),
    )


async def test_a_lane_nobody_serves_is_unattended(connection: Any, lane: str) -> None:
    health = await worker_registry.lane_health(connection, lane)

    assert health.unattended
    assert health.alive == 0
    # Never reported in at all, which is different from having gone quiet.
    assert health.silent_for is None


async def test_an_idle_worker_is_on_the_air_and_free(connection: Any, lane: str) -> None:
    await worker_registry.beat(connection, "worker-a", lane=lane)

    health = await worker_registry.lane_health(connection, lane)

    assert not health.unattended
    assert (health.alive, health.idle, health.busy) == (1, 1, 0)


async def test_a_worker_performing_a_run_is_on_the_air_and_busy(
    connection: Any, lane: str
) -> None:
    """The distinction the console needs: busy is queueing, absent is a fault."""
    run_id = str(uuid4())
    await worker_registry.beat(connection, "worker-a", lane=lane, run_id=run_id)

    health = await worker_registry.lane_health(connection, lane)

    assert not health.unattended
    assert (health.alive, health.idle, health.busy) == (1, 0, 1)


async def test_a_worker_that_stopped_polling_is_no_longer_on_the_air(
    connection: Any, lane: str
) -> None:
    """The four-hour silence. Alive as a process, absent as a worker."""
    await worker_registry.beat(connection, "worker-a", lane=lane)
    await _age(connection, "worker-a", worker_registry.ALIVE_SECONDS + 60)

    health = await worker_registry.lane_health(connection, lane)

    assert health.unattended
    assert health.silent_for is not None
    assert health.silent_for > worker_registry.ALIVE_SECONDS


async def test_a_beat_replaces_the_previous_one_for_that_worker(
    connection: Any, lane: str
) -> None:
    """One row per instance, so a long-lived worker does not grow the table."""
    await worker_registry.beat(connection, "worker-a", lane=lane)
    await _age(connection, "worker-a", worker_registry.ALIVE_SECONDS + 60)

    await worker_registry.beat(connection, "worker-a", lane=lane)

    rows = await connection.fetchval(
        "SELECT count(*) FROM remediation_workers WHERE lane = $1", lane
    )
    assert rows == 1
    assert not (await worker_registry.lane_health(connection, lane)).unattended


async def test_standing_down_is_not_read_as_a_fault(connection: Any, lane: str) -> None:
    """A worker stopped on purpose should leave no trace suggesting it broke."""
    await worker_registry.beat(connection, "worker-a", lane=lane)

    await worker_registry.forget(connection, "worker-a")

    health = await worker_registry.lane_health(connection, lane)
    assert health.unattended
    assert health.silent_for is None


async def test_workers_in_other_lanes_are_not_counted(connection: Any, lane: str) -> None:
    """One database serves the deployment and every laptop with the proxy open."""
    await worker_registry.beat(connection, "worker-elsewhere", lane=f"{lane}-other")
    try:
        health = await worker_registry.lane_health(connection, lane)
        assert health.unattended
    finally:
        await connection.execute(
            "DELETE FROM remediation_workers WHERE lane = $1", f"{lane}-other"
        )
